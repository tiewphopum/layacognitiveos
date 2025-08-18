# demo_s0_to_s6.py
import asyncio, time, random, argparse, os
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

VERBOSE = os.getenv("VERBOSE", "1") == "1"

# -----------------------------
# In-proc EventBus (pub/sub)
# -----------------------------
class EventBus:
    def __init__(self):
        self._subs: Dict[str, List[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, topic: str, fn: Callable[[Any], None]):
        self._subs[topic].append(fn)

    def publish(self, topic: str, event: Any):
        # synchronous fan-out
        for fn in list(self._subs.get(topic, [])):
            try:
                fn(event)
            except Exception as e:
                print(f"[bus] subscriber error on {topic}: {e}")

    # alias
    emit = publish


# -----------------------------
# Optional Global clock (for monitoring/demo)
# -----------------------------
class GlobalClock:
    def __init__(self, bus: EventBus, bpm: float = 60.0, topic: str = "clock/beat"):
        self.bus = bus
        self.bpm = bpm
        self.period = 60.0 / bpm
        self.topic = topic
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def start(self):
        if self._task: return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try: await self._task
            except: pass
            self._task = None

    async def _run(self):
        beat = 0
        t_next = time.perf_counter()
        while self._running:
            now = time.perf_counter()
            if now >= t_next:
                self.bus.emit(self.topic, {"beat": beat, "ts": time.time()})
                beat += 1
                t_next += self.period
            else:
                await asyncio.sleep(max(0, t_next - now))


# -----------------------------
# Bounded buffer per state
# -----------------------------
class QueueBuffer:
    def __init__(self, capacity: int = 1500):
        self._q: Deque[Any] = deque()
        self._cap = capacity

    def push(self, item: Any) -> bool:
        if len(self._q) >= self._cap:
            return False
        self._q.append(item)
        return True

    def pop(self) -> Optional[Any]:
        if self._q:
            return self._q.popleft()
        return None

    def __len__(self):
        return len(self._q)


# -----------------------------
# State definition (configurable inner_loops)
# -----------------------------
@dataclass
class State:
    name: str
    bus: EventBus
    in_topic: str
    out_topic: Optional[str]
    buffer: QueueBuffer
    bpm: float = 60.0                 # รอบของตัวเอง (ครั้ง/นาที)
    inner_loops: int = 1              # จำนวนงานสูงสุดที่จะพยายามเคลียร์ต่อ 1 tick
    proc_ms_min: float = 1.0          # เวลาประมวลผลจำลอง (ms)
    proc_ms_max: float = 3.0
    metrics: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _task: Optional[asyncio.Task] = None
    _running: bool = False

    def start(self):
        self.bus.subscribe(self.in_topic, self._on_event)
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try: await self._task
            except: pass
            self._task = None

    def _on_event(self, ev: Any):
        if self.buffer.push(ev):
            self.metrics["recv_ok"] += 1
        else:
            self.metrics["recv_drop_full"] += 1  # คิวเต็ม

    async def _run(self):
        period = 60.0 / self.bpm if self.bpm > 0 else 0.0
        local_tick = 0
        while self._running:
            tick_start = time.perf_counter()
            local_tick += 1

            # ทำได้หลายงานต่อ tick ตาม inner_loops
            loops = max(1, int(self.inner_loops))
            for _ in range(loops):
                item = self.buffer.pop()
                if item is None:
                    self.metrics["idle"] += 1
                    break

                # process
                work_ms = random.uniform(self.proc_ms_min, self.proc_ms_max)
                await asyncio.sleep(work_ms / 1000.0)

                # ส่งต่อหรือ sink
                if self.out_topic:
                    self.bus.emit(self.out_topic, {
                        "from": self.name,
                        "payload": item["payload"],
                        "hop": item.get("hop", 0) + 1,
                        "t0": item.get("t0"),
                    })
                    self.metrics["send_ok"] += 1
                else:
                    self.metrics["sink_ok"] += 1

            # รักษาจังหวะรอบตัวเอง
            if period > 0:
                elapsed = time.perf_counter() - tick_start
                remain = period - elapsed
                if remain > 0:
                    await asyncio.sleep(remain)
            else:
                await asyncio.sleep(0)


# -----------------------------
# Injector (s0) : ยิงเข้า s1
# -----------------------------
class Injector:
    def __init__(self, bus: EventBus, out_topic: str, bpm: float = 120.0, burst: int = 1):
        self.bus = bus
        self.out_topic = out_topic
        self.period = 60.0 / bpm
        self.burst = max(1, int(burst))
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.sent = 0
        self.drops = 0  # (ไม่ได้ใช้ถ้าส่งตรง topic, เก็บไว้เผื่ออนาคตเปลี่ยนเป็น buffer)

    def start(self):
        if self._task: return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try: await self._task
            except: pass
            self._task = None

    async def _run(self):
        while self._running:
            t0 = time.time()
            produced = 0
            for _ in range(self.burst):
                ev = {"payload": {"seq": self.sent}, "t0": t0, "hop": 0}
                self.bus.emit(self.out_topic, ev)
                self.sent += 1
                produced += 1
            if VERBOSE:
                print(f"[inject] emit={produced} total={self.sent}")
            await asyncio.sleep(self.period)


# -----------------------------
# CLI & run
# -----------------------------
def make_parser():
    p = argparse.ArgumentParser(description="S0->S6 pipeline with per-state BPM & inner_loops")
    p.add_argument("--duration", type=float, default=15.0, help="seconds to run")
    p.add_argument("--qcap", type=int, default=1500, help="buffer capacity for each state")

    # injector
    p.add_argument("--inj_bpm", type=float, default=90.0, help="injector BPM")
    p.add_argument("--inj_burst", type=int, default=1, help="items per injector tick")

    # states bpm
    p.add_argument("--bpm1", type=float, default=60.0)
    p.add_argument("--bpm2", type=float, default=120.0)
    p.add_argument("--bpm3", type=float, default=180.0)
    p.add_argument("--bpm4", type=float, default=240.0)
    p.add_argument("--bpm5", type=float, default=300.0)
    p.add_argument("--bpm6", type=float, default=360.0)

    # inner loops
    p.add_argument("--i1", type=int, default=1)
    p.add_argument("--i2", type=int, default=1)
    p.add_argument("--i3", type=int, default=1)
    p.add_argument("--i4", type=int, default=1)
    p.add_argument("--i5", type=int, default=1)
    p.add_argument("--i6", type=int, default=1)

    # proc time (ms) min/max for ALL (ง่ายสุด)
    p.add_argument("--proc_min", type=float, default=1.0)
    p.add_argument("--proc_max", type=float, default=3.0)

    # optional demo clock
    p.add_argument("--clock_bpm", type=float, default=0.0, help="0 = disable demo clock")
    return p


async def main(args):
    bus = EventBus()

    # buffers
    qcap = args.qcap
    q1 = QueueBuffer(qcap); q2 = QueueBuffer(qcap); q3 = QueueBuffer(qcap)
    q4 = QueueBuffer(qcap); q5 = QueueBuffer(qcap); q6 = QueueBuffer(qcap)

    # states
    s1 = State("s1", bus, "s1.in", "s2.in", q1, bpm=args.bpm1, inner_loops=args.i1,
               proc_ms_min=args.proc_min, proc_ms_max=args.proc_max)
    s2 = State("s2", bus, "s2.in", "s3.in", q2, bpm=args.bpm2, inner_loops=args.i2,
               proc_ms_min=args.proc_min, proc_ms_max=args.proc_max)
    s3 = State("s3", bus, "s3.in", "s4.in", q3, bpm=args.bpm3, inner_loops=args.i3,
               proc_ms_min=args.proc_min, proc_ms_max=args.proc_max)
    s4 = State("s4", bus, "s4.in", "s5.in", q4, bpm=args.bpm4, inner_loops=args.i4,
               proc_ms_min=args.proc_min, proc_ms_max=args.proc_max)
    s5 = State("s5", bus, "s5.in", "s6.in", q5, bpm=args.bpm5, inner_loops=args.i5,
               proc_ms_min=args.proc_min, proc_ms_max=args.proc_max)
    s6 = State("s6", bus, "s6.in", None,    q6, bpm=args.bpm6, inner_loops=args.i6,
               proc_ms_min=args.proc_min, proc_ms_max=args.proc_max)

    for s in (s1, s2, s3, s4, s5, s6):
        s.start()

    # injector
    inj = Injector(bus, out_topic="s1.in", bpm=args.inj_bpm, burst=args.inj_burst)
    inj.start()

    # optional demo clock
    clock = None
    if args.clock_bpm > 0:
        clock = GlobalClock(bus, bpm=args.clock_bpm, topic="clock/beat")
        clock.start()

    t0 = time.time()
    try:
        while time.time() - t0 < args.duration:
            await asyncio.sleep(1.0)
            lens = (len(q1), len(q2), len(q3), len(q4), len(q5), len(q6))
            print(
                f"[t={time.time()-t0:4.1f}s] "
                f"buf={lens} | sent={inj.sent} | sink={s6.metrics.get('sink_ok',0)} | "
                f"recv_drop={sum(s.metrics.get('recv_drop_full',0) for s in (s1,s2,s3,s4,s5,s6))}"
            )
    finally:
        await inj.stop()
        c = 0
        if clock: await clock.stop()
        for s in (s1, s2, s3, s4, s5, s6):         
            await s.stop()

        print("\n=== SUMMARY ===")
        for s in (s1, s2, s3, s4, s5, s6):
            m = s.metrics
            print(
                f"{s.name}: recv_ok={m['recv_ok']} drop_full={m['recv_drop_full']} "
                f"send_ok={m.get('send_ok',0)} sink_ok={m.get('sink_ok',0)} idle={m['idle']}"
            )
        print(f"Injector: sent={inj.sent}")

if __name__ == "__main__":
    parser = make_parser()
    args = parser.parse_args()
    asyncio.run(main(args))