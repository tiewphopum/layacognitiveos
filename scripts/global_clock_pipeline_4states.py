# global_clock_pipeline_4states.py
import asyncio, time, signal, os, argparse
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, List, Optional

# ───────── Config ─────────
VERBOSE = os.getenv("VERBOSE", "1") == "1"  # export VERBOSE=0 เพื่อลด log

# ───────── EventBus ─────────
class EventBus:
    def __init__(self):
        self._subs: Dict[str, List[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, topic: str, fn: Callable[[Any], None]):
        self._subs[topic].append(fn)

    def publish(self, topic: str, msg: Any):
        # เรียก handler แบบ sync แต่ handler จะ schedule async เอง
        for fn in self._subs.get(topic, []):
            fn(msg)

    # alias ให้ใช้ชื่อ emit ได้ตามที่อยาก
    emit = publish

# ───────── GlobalClock ──────
class GlobalClock:
    """
    สร้างหลายสัญญาณนาฬิกาอิสระได้ เช่น:
      add_source(loop_id=0,stride_id=0,bpm=30)  -> s0 feeder
      add_source(loop_id=1,stride_id=1,bpm=20)  -> State1
      ...
    จะ publish ไปที่ topic: clock/<loop>/<stride>
    """
    def __init__(self, bus: EventBus):
        self.bus = bus
        self._defs: List[tuple[int,int,float]] = []
        self._tasks: List[asyncio.Task] = []
        self._stopping = asyncio.Event()

    def add_source(self, loop_id: int, stride_id: int, bpm: float):
        assert bpm > 0, "bpm ต้อง > 0"
        self._defs.append((loop_id, stride_id, float(bpm)))

    def start(self):
        for loop_id, stride_id, bpm in self._defs:
            self._tasks.append(asyncio.create_task(self._run(loop_id, stride_id, bpm)))

    async def stop(self):
        self._stopping.set()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _run(self, loop_id: int, stride_id: int, bpm: float):
        topic = f"clock/{loop_id}/{stride_id}"
        period = 60.0 / bpm
        beat = 0
        t_next = time.perf_counter()
        if VERBOSE:
            print(f"[clock {loop_id}/{stride_id}] start bpm={bpm} period={period:.3f}s")
        while not self._stopping.is_set():
            now = time.perf_counter()
            if now < t_next:
                await asyncio.sleep(t_next - now)
            self.bus.emit(topic, {"loop": loop_id, "stride": stride_id, "beat": beat, "ts": time.time()})
            beat += 1
            t_next += period
        if VERBOSE:
            print(f"[clock {loop_id}/{stride_id}] stop at beat={beat}")

# ───────── Buffer ───────────
@dataclass
class Buffer:
    name: str
    cap: int
    q: Deque[Any]

    @classmethod
    def with_capacity(cls, name: str, cap: int):
        return cls(name=name, cap=cap, q=deque())

    def push(self, item: Any) -> bool:
        if len(self.q) >= self.cap:
            return False
        self.q.append(item)
        return True

    def pop(self) -> Optional[Any]:
        return self.q.popleft() if self.q else None

    def __len__(self):
        return len(self.q)

# ───────── State ────────────
class State:
    """
    State หนึ่ง ๆ:
      - subscribe clock/<loop>/<stride>
      - ใน 1 ติ๊ก สามารถ “วนรอบย่อย” (inner_loops) เพื่อเคลียร์หลายงานได้
      - ส่งไม่ได้ -> เก็บ in_hand รอส่งในติ๊กถัดไป
      - ถ้ามี source_feeder (ทางเลือก) จะ feed เข้า my_buffer ตอนต้นทิก
    """
    def __init__(self, name: str, bus: EventBus, clock_loop: int, clock_stride: int,
                 my_buffer: Buffer, next_buffer: Optional[Buffer],
                 process_ms: int = 5, inner_loops: int = 1,
                 source_feeder: Optional[Callable[[], Optional[dict]]] = None):
        self.name = name
        self.bus = bus
        self.clock_loop = clock_loop
        self.clock_stride = clock_stride
        self.my_buffer = my_buffer
        self.next_buffer = next_buffer
        self.process_ms = process_ms
        self.inner_loops = max(1, int(inner_loops))
        self.source_feeder = source_feeder

        self.in_hand: Optional[Any] = None
        self.processing_task: Optional[asyncio.Task] = None

        # metrics
        self.done_send = 0
        self.skips_empty = 0
        self.skips_busy = 0
        self.feed_drop_full = 0
        self.feed_ok = 0
        self.local_tick = 0

        self._subscribe()

    def _subscribe(self):
        topic = f"clock/{self.clock_loop}/{self.clock_stride}"
        self.bus.subscribe(topic, self._on_tick)

    def _on_tick(self, ev: Dict[str, Any]):
        # schedule งาน async ต่อทิก
        asyncio.create_task(self._tick_async(ev))

    def _maybe_feed_from_source(self, beat: int):
        if not self.source_feeder:
            return
        task = self.source_feeder()
        if task is None:
            return
        if self.my_buffer.push(task):
            self.feed_ok += 1
            if VERBOSE:
                print(f"[clock {self.clock_loop}/{self.clock_stride} beat={beat}] {self.name} FEED -> {self.my_buffer.name} q={len(self.my_buffer)}")
        else:
            self.feed_drop_full += 1
            if VERBOSE:
                print(f"[clock {self.clock_loop}/{self.clock_stride} beat={beat}] {self.name} FEED_DROP (q_full) q={len(self.my_buffer)}")

    async def _pull_and_process(self, beat: int) -> Optional[Any]:
        # กำลังประมวลผลอยู่ (รอบก่อน)
        if self.processing_task and not self.processing_task.done():
            if VERBOSE:
                print(f"[clock {self.clock_loop}/{self.clock_stride} beat={beat}] {self.name} tick={self.local_tick} busy_processing")
            return None

        item = self.my_buffer.pop()
        if item is None:
            self.skips_empty += 1
            if VERBOSE:
                print(f"[clock {self.clock_loop}/{self.clock_stride} beat={beat}] {self.name} tick={self.local_tick} empty q=0")
            return None

        # ประมวลผล (จำลองใช้เวลา)
        self.processing_task = asyncio.create_task(self._process(item))
        await self.processing_task
        return self.processing_task.result()

    async def _process(self, item: Any):
        await asyncio.sleep(self.process_ms / 1000.0)
        return {"stage": self.name, "data": item}

    def _try_send(self, payload: Any) -> bool:
        if self.next_buffer is None:
            # Sink/ปลายทาง
            self.done_send += 1
            return True
        if self.next_buffer.push(payload):
            self.done_send += 1
            return True
        return False

    async def _tick_async(self, ev: Dict[str, Any]):
        beat = ev.get("beat")
        self.local_tick += 1

        # feed ต้นทิก (ถ้ามี)
        self._maybe_feed_from_source(beat)

        loops = self.inner_loops
        for _ in range(loops):
            # 1) ส่งของค้างก่อน
            if self.in_hand is not None:
                if self._try_send(self.in_hand):
                    if VERBOSE:
                        print(f"[clock {self.clock_loop}/{self.clock_stride} beat={beat}] {self.name} tick={self.local_tick} SEND_OK (in_hand) q={len(self.my_buffer)}")
                    self.in_hand = None
                else:
                    self.skips_busy += 1
                    if VERBOSE:
                        print(f"[clock {self.clock_loop}/{self.clock_stride} beat={beat}] {self.name} tick={self.local_tick} SEND_BLOCK (downstream_full) HOLD")
                    # ยังค้างอยู่ -> จบรอบย่อย
                    break

            # 2) ดึง + ประมวลผล
            out = await self._pull_and_process(beat)
            if out is None:
                # ไม่มีงาน / ยัง busy จากรอบก่อน -> จบรอบย่อยนี้
                break

            # 3) ส่งผลลัพธ์
            if self._try_send(out):
                if VERBOSE:
                    print(f"[clock {self.clock_loop}/{self.clock_stride} beat={beat}] {self.name} tick={self.local_tick} PROC_SEND_OK q={len(self.my_buffer)}")
            else:
                self.in_hand = out
                self.skips_busy += 1
                if VERBOSE:
                    print(f"[clock {self.clock_loop}/{self.clock_stride} beat={beat}] {self.name} tick={self.local_tick} PROC_SEND_BLOCK -> HOLD")
                # ค้างไว้แล้วจบรอบย่อย
                break

# ───────── Feeder (S0) ──────
class Feeder:
    """
    ยิงงานเข้า buffer เป้าหมายตาม clock ของตัวเอง
    - items_per_tick: จำนวนงานที่ปล่อยต่อติ๊ก
    """
    def __init__(self, name: str, bus: EventBus, clock_loop: int, clock_stride: int,
                 target_buffer: Buffer, items_per_tick: int = 1):
        self.name = name
        self.bus = bus
        self.clock_loop = clock_loop
        self.clock_stride = clock_stride
        self.target_buffer = target_buffer
        self.items_per_tick = max(1, int(items_per_tick))
        self.emit_counter = 0
        self.drop_full = 0
        self.local_tick = 0
        self.bus.subscribe(f"clock/{clock_loop}/{clock_stride}", self._on_tick)

    def _on_tick(self, ev: Dict[str, Any]):
        asyncio.create_task(self._tick_async(ev))

    async def _tick_async(self, ev: Dict[str, Any]):
        beat = ev.get("beat")
        self.local_tick += 1
        produced = 0
        for _ in range(self.items_per_tick):
            item = {"id": self.emit_counter, "from": self.name}
            if self.target_buffer.push(item):
                self.emit_counter += 1
                produced += 1
            else:
                self.drop_full += 1
                break
        if VERBOSE:
            print(f"[clock {self.clock_loop}/{self.clock_stride} beat={beat}] {self.name} emit={produced} q={len(self.target_buffer)} drops={self.drop_full}")

# ───────── Demo wiring ───────
def make_parser():
    p = argparse.ArgumentParser(description="GlobalClock + 4 States pipeline demo")
    p.add_argument("--duration", type=float, default=10.0, help="seconds to run (default 10)")
    p.add_argument("--qcap", type=int, default=1500, help="queue capacity for each buffer (default 1500)")
    # BPM
    p.add_argument("--bpm_s0", type=float, default=30.0, help="feeder BPM (default 30)")
    p.add_argument("--bpm_s1", type=float, default=20.0, help="state1 BPM (default 20)")
    p.add_argument("--bpm_s2", type=float, default=28.0, help="state2 BPM (default 28)")
    p.add_argument("--bpm_s3", type=float, default=36.0, help="state3 BPM (default 36)")
    p.add_argument("--bpm_s4", type=float, default=44.0, help="state4 BPM (default 44)")
    # processing time ms
    p.add_argument("--p1", type=int, default=6, help="State1 process ms (default 6)")
    p.add_argument("--p2", type=int, default=5, help="State2 process ms (default 5)")
    p.add_argument("--p3", type=int, default=4, help="State3 process ms (default 4)")
    p.add_argument("--p4", type=int, default=3, help="State4 process ms (default 3)")
    # inner loops per tick
    p.add_argument("--i1", type=int, default=1, help="State1 inner loops per tick (default 1)")
    p.add_argument("--i2", type=int, default=1, help="State2 inner loops per tick (default 1)")
    p.add_argument("--i3", type=int, default=1, help="State3 inner loops per tick (default 1)")
    p.add_argument("--i4", type=int, default=1, help="State4 inner loops per tick (default 1)")
    # feeder items per tick
    p.add_argument("--s0_burst", type=int, default=1, help="feeder items per tick (default 1)")
    return p

async def main(args):
    bus = EventBus()

    # buffers
    q1 = Buffer.with_capacity("Q1", args.qcap)
    q2 = Buffer.with_capacity("Q2", args.qcap)
    q3 = Buffer.with_capacity("Q3", args.qcap)
    q4 = Buffer.with_capacity("Q4", args.qcap)

    # clocks
    clock = GlobalClock(bus)
    # S0 feeder clock
    clock.add_source(loop_id=0, stride_id=0, bpm=args.bpm_s0)
    # States clocks
    clock.add_source(loop_id=1, stride_id=1, bpm=args.bpm_s1)
    clock.add_source(loop_id=1, stride_id=2, bpm=args.bpm_s2)
    clock.add_source(loop_id=1, stride_id=3, bpm=args.bpm_s3)
    clock.add_source(loop_id=1, stride_id=4, bpm=args.bpm_s4)
    clock.start()

    # S0 Feeder
    s0 = Feeder("S0.feeder", bus, 0, 0, q1, items_per_tick=args.s0_burst)

    # States
    s1 = State("State1", bus, 1, 1, q1, q2, process_ms=args.p1, inner_loops=args.i1)
    s2 = State("State2", bus, 1, 2, q2, q3, process_ms=args.p2, inner_loops=args.i2)
    s3 = State("State3", bus, 1, 3, q3, q4, process_ms=args.p3, inner_loops=args.i3)
    s4 = State("State4", bus, 1, 4, q4, None, process_ms=args.p4, inner_loops=args.i4)

    stop_evt = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop_evt.set)
        except NotImplementedError:
            # บน Windows/บาง env
            pass

    print("Running… (Ctrl-C to stop)")
    try:
        await asyncio.wait_for(stop_evt.wait(), timeout=args.duration)
    except asyncio.TimeoutError:
        pass

    print("Stopping clock…")
    await clock.stop()

    def stat_state(s: State):
        return (f"{s.name}: sent={s.done_send} tick={s.local_tick} "
                f"in_hand={s.in_hand is not None} empty={s.skips_empty} busy={s.skips_busy} "
                f"feed_ok={s.feed_ok} drop_full={s.feed_drop_full}")

    print("\n=== SUMMARY ===")
    print(f"Q1={len(q1)} Q2={len(q2)} Q3={len(q3)} Q4={len(q4)}")
    print(f"S0.feeder: emitted={s0.emit_counter} drop_full={s0.drop_full} tick={s0.local_tick}")
    print(stat_state(s1))
    print(stat_state(s2))
    print(stat_state(s3))
    print(stat_state(s4))

if __name__ == "__main__":
    parser = make_parser()
    args = parser.parse_args()
    asyncio.run(main(args))