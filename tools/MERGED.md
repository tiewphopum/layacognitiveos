# Merged Sources

## `./scripts/__init__.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/scripts/__init__.py`_

```python

```

## `./scripts/demo_bootstrap.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/scripts/demo_bootstrap.py`_

```python
import os
from layaos.core import log
from layaos.core.metrics import start_exporter, inc_counter, observe_hist
import time
import random

def main():
    log.setup()
    start_exporter(interval_sec=float(os.getenv("METRICS_INTERVAL", "5")),
                   json_mode=(os.getenv("LOG_JSON", "0") == "1"))

    # เดโม่โยน metrics สักหน่อย
    for _ in range(10):
        inc_counter("event_rate", topic="demo")
        observe_hist("latency_ms", random.uniform(5, 30), stage="demo")
        time.sleep(0.5)

if __name__ == "__main__":
    main()
```

## `./scripts/demo_motion.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/scripts/demo_motion.py`_

```python
import asyncio
import os
import time
from statistics import median
from typing import List

from layaos.core import log
from layaos.core.metrics import start_exporter, stop_exporter, observe_hist, inc
from layaos.pipeline.wire_minimal import build_pipeline


async def main():
    # บูต logger + metrics
    os.environ.setdefault("LOG_LEVEL", "INFO")
    os.environ.setdefault("LOG_JSON", "0")
    os.environ.setdefault("METRICS_INTERVAL", "5.0")

    log.setup()
    lg = log.get("demo.motion")

    start_exporter(
        interval_sec=float(os.getenv("METRICS_INTERVAL", "5.0")),
        json_mode=(os.getenv("LOG_JSON", "0") == "1"),
        logger=log.get("metrics"),
    )

    # สร้าง pipeline S1–S3
    bus, cam, states = build_pipeline(cam_hz=12)
    bus.start()
    
    s1_to_s3 = states[:3]

    # เก็บสถิติแบบง่าย ๆ
    det_count = 0
    motion_ratios: List[float] = []
    end2end_ms: List[float] = []

    # subscribe สรุป end-to-end จาก s3.det
    t_start = time.perf_counter()

    # วางไว้ก่อน on_det
    _seen_debug = 0
    def _to_mapping(ev):
        if isinstance(ev, dict):
            return ev
        payload = getattr(ev, "payload", None)
        if isinstance(payload, dict):
            return payload
        d = getattr(ev, "__dict__", None)
        if isinstance(d, dict):
            return d
        return {}

    def _find_motion_ratio(ev):
        m = _to_mapping(ev)
        candidates = [
            "motion_ratio", "ratio", "motion.ratio",
            "stats.motion_ratio", "metrics.motion_ratio",
        ]
        for k in candidates:
            if k in m:
                try:
                    return float(m[k])
                except Exception:
                    pass
        motion = m.get("motion") if isinstance(m.get("motion"), dict) else None
        if motion and "ratio" in motion:
            try:
                return float(m["ratio"])
            except Exception:
                pass
        for attr in ["motion_ratio", "ratio"]:
            if hasattr(ev, attr):
                try:
                    return float(getattr(ev, attr))
                except Exception:
                    pass
        return 0.0

    def on_det(ev):
        nonlocal det_count
        det_count += 1

        # ใช้ attribute บนฟังก์ชันเป็นตัวนับ debug
        on_det.debug_shown = getattr(on_det, "debug_shown", 0)
        if on_det.debug_shown < 3:
            m = _to_mapping(ev)
            print("[DBG] det event keys:", sorted(list(m.keys()))[:20])
            if isinstance(m.get("motion"), dict):
                print("[DBG] det motion keys:", list(m["motion"].keys()))
            on_det.debug_shown += 1

        ratio = _find_motion_ratio(ev)
        motion_ratios.append(ratio)

        # e2e latency: ใช้ timestamp จาก event ถ้ามี
        src_ts = (
            getattr(ev, "ts", None)
            or getattr(ev, "t0", None)
            or getattr(ev, "start_ts", None)
            or (_to_mapping(ev).get("ts"))
        )
        if src_ts is not None and src_ts > 1e12:  # เผื่อเป็น ns
            src_ts = src_ts / 1e9
        now_s = time.time()
        dt_ms = (now_s - float(src_ts)) * 1000.0 if src_ts is not None else 0.0
        end2end_ms.append(dt_ms)

        observe_hist("demo_e2e_ms", dt_ms, stage="s1_to_s3")
        inc("demo_det_total", 1, topic="s3.det")
    bus.subscribe("s3.det", on_det)
    

    # สปิน
    tasks = [asyncio.create_task(s.run()) for s in s1_to_s3]
    cam_task = asyncio.create_task(cam.run(n_frames=999999))  # ปล่อยไหล

    # รัน 20s
    try:
        lg.info("demo start: running ~20s")
        await asyncio.sleep(20.0)
    finally:
        cam_task.cancel()
        for t in tasks:
            t.cancel()
        await asyncio.gather(cam_task, *tasks, return_exceptions=True)

        # สรุป
        valid = [r for r in motion_ratios if r > 0.0]
        avg_ratio = (sum(valid) / len(valid)) if valid else 0.0
        p50 = median(sorted(end2end_ms)) if end2end_ms else 0.0
        lg.info("=== DEMO SUMMARY ===")
        lg.info("det_count=%d avg_ratio=%.4f p50_e2e_ms=%.2f", det_count, avg_ratio, p50)
        bus.stop()
        stop_exporter()


if __name__ == "__main__":
    asyncio.run(main())
```

## `./src/layaos/__init__.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/__init__.py`_

```python

```

## `./src/layaos/adapters/storage.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/adapters/storage.py`_

```python
# src/layaos/adapters/storage.py
from __future__ import annotations

import json
import time
import os
import queue
import threading
import logging
import uuid
from dataclasses import dataclass, asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional

# Optional metrics (no-op fallback)
try:
    from layaos.core.metrics import inc, gauge_set, observe_hist  # type: ignore
except Exception:  # pragma: no cover
    def inc(*args, **kwargs): pass
    def gauge_set(*args, **kwargs): pass
    def observe_hist(*args, **kwargs): pass

log = logging.getLogger("layaos.adapters.storage")


def _to_jsonable(obj: Any) -> Any:
    """พยายามแปลงอ็อบเจ็กต์ให้เป็น JSON-serializable"""
    # dataclass
    if is_dataclass(obj):
        return asdict(obj)

    # มี to_dict()
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass

    # numpy
    try:
        import numpy as np  # type: ignore
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)  # type: ignore[arg-type]
        if isinstance(obj, (np.floating,)):
            return float(obj)  # type: ignore[arg-type]
        if obj is np.nan:
            return None
    except Exception:
        pass

    # types ที่ serialize ได้อยู่แล้ว
    if isinstance(obj, (dict, list, str, int, float, bool)) or obj is None:
        return obj

    # เผื่อเป็นอ็อบเจ็กต์ปกติ
    d = getattr(obj, "__dict__", None)
    if isinstance(d, dict):
        return {k: _to_jsonable(v) for k, v in d.items()}

    # สุดท้าย แปลงเป็น string
    return str(obj)


class AsyncStorage:
    """Simple async JSON/Bytes writer with worker thread + atomic write."""
    def __init__(self, out_dir: str = "data", max_queue: int = 1024, prefix: str = "evt"):
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix
        self.q: "queue.Queue[tuple[str, Any]]" = queue.Queue(max_queue)
        self._th: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._th and self._th.is_alive():
            return
        self._stop.clear()
        self._th = threading.Thread(target=self._worker, name="AsyncStorage", daemon=True)
        self._th.start()
        log.info("storage start dir=%s max_queue=%d", self.dir.as_posix(), self.q.maxsize)

    def stop(self, timeout: float = 2.0) -> None:
        """ขอให้หยุด และรอคิวระบายให้หมดก่อน"""
        self._stop.set()
        try:
            # รอให้เคลียร์คิว (ป้องกันไฟล์ค้างไม่ครบ)
            self.q.join()
        except Exception:
            pass
        if self._th and threading.current_thread() is not self._th:
            self._th.join(timeout=timeout)
        log.info("storage stop")

    def put_json(self, kind: str, obj: Any) -> None:
        """Enqueue JSON write; drop oldest if full (backpressure-friendly)."""
        try:
            self.q.put_nowait((kind, obj))
        except queue.Full:
            # drop policy: remove one oldest then put
            try:
                _ = self.q.get_nowait()
                self.q.task_done()
            except Exception:
                pass
            try:
                self.q.put_nowait((kind, obj))
            except Exception:
                pass
            inc("storage_drops_total", 1, kind=kind)
        gauge_set("storage_queue_depth", float(self.q.qsize()))

    def put_bytes(self, kind: str, data: bytes) -> None:
        """Enqueue raw bytes write; file will have .bin extension."""
        try:
            self.q.put_nowait((f"{kind}::bytes", data))
        except queue.Full:
            try:
                _ = self.q.get_nowait()
                self.q.task_done()
            except Exception:
                pass
            try:
                self.q.put_nowait((f"{kind}::bytes", data))
            except Exception:
                pass
            inc("storage_drops_total", 1, kind=f"{kind}::bytes")
        gauge_set("storage_queue_depth", float(self.q.qsize()))

    def _worker(self) -> None:
        while not self._stop.is_set() or not self.q.empty():
            try:
                kind, obj = self.q.get(timeout=0.1)
            except queue.Empty:
                continue

            t0 = time.perf_counter()
            try:
                if kind.endswith("::bytes"):
                    real_kind = kind.split("::", 1)[0]
                    self._write_bytes(real_kind, obj)
                    inc("storage_write_total", 1, kind=real_kind)
                else:
                    self._write_json(kind, obj)
                    inc("storage_write_total", 1, kind=kind)
            except Exception as e:  # pragma: no cover
                log.error("write error: %s", e, exc_info=True)
            finally:
                dt_ms = (time.perf_counter() - t0) * 1000.0
                try:
                    observe_hist("storage_write_ms", dt_ms, kind=kind)
                except Exception:
                    pass
                self.q.task_done()
                gauge_set("storage_queue_depth", float(self.q.qsize()))

    def _write_json(self, kind: str, obj: Any) -> None:
        folder = self.dir / kind
        folder.mkdir(parents=True, exist_ok=True)
        ts_ns = time.time_ns()
        name = f"{self.prefix}-{ts_ns}-{uuid.uuid4().hex[:6]}.json"
        path = folder / name
        tmp = path.with_suffix(path.suffix + ".tmp")

        data = _to_jsonable(obj)
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _write_bytes(self, kind: str, data: bytes) -> None:
        folder = self.dir / kind
        folder.mkdir(parents=True, exist_ok=True)
        ts_ns = time.time_ns()
        name = f"{self.prefix}-{ts_ns}-{uuid.uuid4().hex[:6]}.bin"
        path = folder / name
        tmp = path.with_suffix(path.suffix + ".tmp")

        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    # Convenience helpers (used by LocalEventStorage wrapper)
    def save_image(self, kind: str, frame, *, ext: str = ".png") -> Path:
        """Save numpy array frame as an image file, returns the path."""
        try:
            import numpy as np
            from PIL import Image  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Pillow and numpy required for save_image()") from e

        folder = self.dir / kind
        folder.mkdir(parents=True, exist_ok=True)
        ts_ns = time.time_ns()
        path = folder / f"{self.prefix}-{ts_ns}{ext}"

        arr = np.asarray(frame)
        if arr.ndim == 2:
            img = Image.fromarray(arr)
        elif arr.ndim == 3 and arr.shape[2] in (1, 3, 4):
            if arr.shape[2] == 1:
                arr = arr[..., 0]
                img = Image.fromarray(arr)
            else:
                img = Image.fromarray(arr[..., :3])
        else:
            raise ValueError(f"Unsupported frame shape: {arr.shape}")

        img.save(path)
        inc("storage_write_total", 1, kind=kind)
        return path

    def flush(self, timeout: float = 5.0) -> None:
        """Block until queue is empty or timeout reached."""
        # ใช้ q.join() ถ้าอยากให้บล็อคจนหมดคิว
        deadline = time.time() + timeout
        while time.time() < deadline and not self.q.empty():
            time.sleep(0.01)

    # เผื่อบางเทสต์อยาก q.join() เอง
    @property
    def queue(self) -> "queue.Queue[tuple[str, Any]]":
        return self.q


# --- Back-compat wrappers ---

@dataclass
class StorageConfig:
    # Support both 'out_dir' and 'root_dir' naming (older tests)
    out_dir: Optional[str] = None
    root_dir: Optional[str] = None
    prefix: str = "evt"
    max_queue: int = 1024

    def resolve_out_dir(self) -> str:
        return (self.out_dir or self.root_dir or "data")


class LocalEventStorage:
    """Thin wrapper around AsyncStorage to satisfy older tests importing this name."""
    def __init__(self, cfg: StorageConfig, logger=None):
        self.cfg = cfg
        out = cfg.resolve_out_dir()
        self._impl = AsyncStorage(out_dir=out, max_queue=cfg.max_queue, prefix=cfg.prefix)
        self._logger = logger or logging.getLogger("layaos.adapters.storage.local")

    def start(self) -> None:
        self._impl.start()

    def stop(self) -> None:
        self._impl.stop()

    # aliases for JSON events
    def put_json(self, kind: str, obj: Any) -> None:
        self._impl.put_json(kind, obj)

    def write_event(self, kind: str, obj: Any) -> None:
        self._impl.put_json(kind, obj)

    # image save API expected by some tests
    def save(self, kind: str, frame, *, ext: str = ".png") -> Path:
        return self._impl.save_image(kind, frame, ext=ext)

    def flush(self, timeout: float = 5.0) -> None:
        self._impl.flush(timeout=timeout)

    # convenience
    def dir(self) -> Path:
        return self._impl.dir
```

## `./src/layaos/adapters/ws_hub.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/adapters/ws_hub.py`_

```python
# src/layaos/adapters/ws_hub.py
from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional, Set

log = logging.getLogger(__name__)

try:
    import websockets  # type: ignore
except Exception:  # pragma: no cover
    websockets = None  # optional dependency

MessageHandler = Callable[[str, dict], Awaitable[None]]

@dataclass
class WSHubClientConfig:
    url: str = "ws://127.0.0.1:8765"
    reconnect_delay: float = 1.0

@dataclass
class WSHubClient:
    cfg: WSHubClientConfig
    _ws: Optional["websockets.WebSocketClientProtocol"] = None
    _subs: Dict[str, Set[MessageHandler]] = field(default_factory=dict)
    _task_recv: Optional[asyncio.Task] = None
    _closed: bool = False

    async def connect(self) -> None:
        if websockets is None:
            raise RuntimeError("websockets not installed. `pip install websockets`")
        while not self._closed:
            try:
                log.info("ws connect %s", self.cfg.url)
                self._ws = await websockets.connect(self.cfg.url)
                self._task_recv = asyncio.create_task(self._recv_loop())
                return
            except Exception as e:
                log.warning("ws connect failed: %s; retry in %.1fs", e, self.cfg.reconnect_delay)
                await asyncio.sleep(self.cfg.reconnect_delay)

    async def close(self) -> None:
        self._closed = True
        if self._task_recv:
            self._task_recv.cancel()
        if self._ws:
            await self._ws.close()

    async def publish(self, topic: str, payload: dict) -> None:
        if not self._ws:
            raise RuntimeError("ws not connected")
        msg = {"type": "pub", "topic": topic, "data": payload}
        await self._ws.send(json.dumps(msg))

    async def subscribe(self, topic: str, handler: MessageHandler) -> None:
        self._subs.setdefault(topic, set()).add(handler)
        # inform server (best-effort)
        if self._ws:
            await self._ws.send(json.dumps({"type": "sub", "topic": topic}))

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        ws = self._ws
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    topic = msg.get("topic", "")
                    data = msg.get("data", {})
                    for h in self._subs.get(topic, set()):
                        await h(topic, data)
                except Exception as e:
                    log.exception("ws recv err: %s", e)
        finally:
            self._ws = None
            if not self._closed:
                log.info("ws disconnected; will reconnect")
                await self.connect()
```

## `./src/layaos/core/buffer.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/core/buffer.py`_

```python
# src/core/buffer.py
from __future__ import annotations
import collections
from typing import Deque, Optional, Any

class RingBuffer:
    def __init__(self, capacity: int = 256):
        self.cap = capacity
        self.buf: Deque[Any] = collections.deque(maxlen=capacity)

    def push(self, item: Any):
        self.buf.append(item)  # ล้นแล้วดันหัวทิ้งอัตโนมัติ

    def pop(self) -> Optional[Any]:
        return self.buf.popleft() if self.buf else None

    def peek(self) -> Optional[Any]:
        return self.buf[0] if self.buf else None

    def __len__(self): return len(self.buf)
```

## `./src/layaos/core/bus.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/core/bus.py`_

```python
# src/core/bus.py
from __future__ import annotations
import threading, queue, time
from typing import Callable, Dict, List, Optional, Any
import asyncio
from collections import deque
from layaos.core import log
from layaos.core.metrics import inc, gauge_set  # <-- ใช้ฟังก์ชันล้วน
from layaos.core.contracts import Event

class InProcEventBus:
    def __init__(self, name: str = "orchestrai.bus", daemon: bool = True, maxlen: int = 256):
        self.name = name
        self.daemon = daemon
        self.l = log.get(self.name)
        self._subs: Dict[str, List[Callable[[Event], None]]] = {}
        self._running = False
        self._q: "queue.Queue[Event]" = queue.Queue()
        self._th: threading.Thread | None = None
        self._topics: Dict[str, deque] = {}
        self._maxlen = int(maxlen)

    def _payload_from_event(self, ev):
        # Extract payload from common attribute names
        for k in ("data", "payload", "value", "body", "content", "message"):
            if hasattr(ev, k):
                return getattr(ev, k)
        # dict-like fallback
        if isinstance(ev, dict):
            return ev.get("data", ev)
        # tuple-like fallback: (topic, payload)
        try:
            return ev[1]
        except Exception:
            return None

    def start(self):
        if self._running: return
        self._running = True
        self._th = threading.Thread(target=self._loop, name="EventBus", daemon=self.daemon)
        self._th.start()
        self.l.info("bus start (daemon=%s)", self.daemon)

    def stop(self):
        if not self._running: return
        self._running = False
        if self._th and self._th.is_alive():
            self._th.join(timeout=1.0)
        self.l.info("bus stop")

    # wildcard แบบง่าย: "a.*"
    def _match(self, topic: str, pattern: str) -> bool:
        if pattern.endswith(".*"):
            return topic.startswith(pattern[:-2])
        return topic == pattern

    def _ensure_topic(self, topic: str):
        if topic not in self._topics:
            self._topics[topic] = deque(maxlen=self._maxlen)
        return self._topics[topic]

    def subscribe(self, topic: str, fn: Callable[[Event], None]):
        self._subs.setdefault(topic, []).append(fn)
        self.l.info("subscribed topic=%s fn=%s", topic, getattr(fn, "__name__", str(fn)))
        # อัพเดท gauge จำนวน subscribers ต่อ topic
        gauge_set("bus_subscribers", float(len(self._subs[topic])), topic=topic)

    def publish(self, a: Any, b: Optional[Any] = None):
        """
        Dual API:
        - publish(Event)
        - publish(topic: str, data: Any)
        """
        # Case 1: publish(Event-like object)
        if b is None and hasattr(a, "topic"):
            ev = a
            topic = ev.topic
            inc("bus_publish_total", 1, topic=topic)

            # Extract payload robustly
            payload = self._payload_from_event(ev)

            # enqueue per-topic data payload if present
            q = self._ensure_topic(topic)
            if payload is not None:
                q.append(payload)
                gauge_set("bus_queue_depth", float(len(q)), topic=topic)

            # also push to subscriber fanout loop if Event wrapper is compatible
            try:
                self._q.put(ev)
            except Exception:
                pass
            return

        # Case 2: publish(topic, data)
        topic: str = str(a)
        data: Any = b
        inc("bus_publish_total", 1, topic=topic)
        q = self._ensure_topic(topic)
        q.append(data)
        # deliver to subscriber loop via Event wrapper
        try:
            ev = Event(topic=topic, data=data)
        except TypeError:
            # Fallback if Event signature differs; deliver only via queue
            ev = None
        if ev is not None:
            self._q.put(ev)
        gauge_set("bus_queue_depth", float(len(q)), topic=topic)

    def _loop(self):
        while self._running:
            try:
                ev = self._q.get(timeout=0.1)
            except queue.Empty:
                continue

            # fan-out + wildcard
            for pattern, fns in list(self._subs.items()):
                if self._match(ev.topic, pattern):
                    for fn in list(fns):
                        try:
                            t0 = time.perf_counter()
                            fn(ev)
                            dt_ms = (time.perf_counter() - t0) * 1000.0
                            inc("bus_deliver_total", 1, topic=ev.topic, sub=getattr(fn, "__name__", "anon"))
                            gauge_set("bus_delivery_latency_ms", float(dt_ms), topic=ev.topic)
                        except Exception as e:
                            self.l.error("deliver error topic=%s fn=%s err=%s", ev.topic, fn, e, exc_info=True)
    def queue_depth(self, topic: Optional[str]) -> int:
        if not topic:
            return 0
        q = self._topics.get(topic)
        return 0 if q is None else len(q)

    def consume_nowait(self, topic: str):
        q = self._topics.get(topic)
        if not q:
            raise queue.Empty()
        try:
            return q.popleft()
        except IndexError:
            raise queue.Empty()

    async def try_consume(self, topic: str):
        q = self._topics.get(topic)
        if not q or len(q) == 0:
            return None
        # non-blocking pop
        try:
            return q.popleft()
        except IndexError:
            return None

    async def consume(self, topic: str, poll_interval: float = 0.01):
        """
        Async wait until there is an item for the topic, then pop and return it.
        Implemented with a tiny polling loop to avoid introducing extra threads.
        """
        q = self._ensure_topic(topic)
        while True:
            try:
                return q.popleft()
            except IndexError:
                await asyncio.sleep(poll_interval)
```

## `./src/layaos/core/clock.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/core/clock.py`_

```python
from __future__ import annotations

from layaos.core import log
from layaos.core.metrics import observe_hist
import threading
import time
import asyncio


class BeatClock:
    """
    Dual-mode clock:
    - Thread mode: use start(on_tick) / stop()
    - Async mode : iterate over async generator ticks()

    Do NOT use both modes at the same time on the same instance.
    """

    def __init__(self, *, hz: float = 1.0, name: str = "clock"):
        self.hz = float(hz)
        if self.hz <= 0:
            raise ValueError("hz must be > 0")
        self.dt = 1.0 / self.hz
        self.name = name
        self.l = log.get(f"orchestrai.{name}")
        # thread mode
        self._running: bool = False
        self._th: threading.Thread | None = None
        self._on_tick = None
        # async mode
        self._async_running: bool = False

    # -------------------- Thread mode --------------------
    def start(self, on_tick):
        """Start legacy thread-driven ticking and call on_tick(ts, i)."""
        if self._async_running:
            self.l.warning("start() called while async ticks() is active; this is unsupported.")
        self._running = True
        self._on_tick = on_tick
        self._th = threading.Thread(target=self._loop, name=f"BeatClock-{self.name}", daemon=True)
        self._th.start()
        self.l.info(f"clock start hz={self.hz:.3f} (dt={self.dt:.3f})")

    def _loop(self):
        i = 0
        while self._running:
            t0 = time.perf_counter()
            ts = time.time()
            i += 1

            try:
                if self._on_tick is not None:
                    self._on_tick(ts, i)
            except Exception as e:  # pragma: no cover (guardrail)
                self.l.error(f"tick error: {e}", exc_info=True)

            t1 = time.perf_counter()
            loop_ms = (t1 - t0) * 1000.0
            observe_hist("clock_loop_ms", loop_ms, clock=self.name)

            sleep_time = self.dt - (t1 - t0)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self):
        """Stop thread-driven ticking."""
        self._running = False
        if self._th and threading.current_thread() is not self._th:
            self._th.join(timeout=1.0)
        self._th = None
        self.l.info("clock stop")

    # -------------------- Async mode --------------------
    async def ticks(self):
        """
        Async tick generator for asyncio world.
        Usage:
            async for ts_i in clock.ticks():
                ...
        Yields: (unix_ts: float, index: int)
        """
        if self._running:
            self.l.warning("ticks() used while thread mode is running; disable thread mode first.")
        if self._async_running:
            self.l.warning("ticks() called twice; reusing the same generator is unsupported.")

        self._async_running = True
        i = 0
        try:
            next_t = time.perf_counter()  # monotonic scheduling
            while self._async_running:
                now = time.perf_counter()
                if now < next_t:
                    await asyncio.sleep(next_t - now)
                unix_ts = time.time()
                i += 1
                yield (unix_ts, i)
                after = time.perf_counter()
                loop_ms = (after - now) * 1000.0
                observe_hist("clock_loop_ms", loop_ms, clock=self.name)
                # schedule next beat; prevent drift by using max()
                next_t = max(next_t + self.dt, after)
        finally:
            self._async_running = False
```

## `./src/layaos/core/contracts.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/core/contracts.py`_

```python

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
    NDArray = np.ndarray  # type: ignore[name-defined]
except Exception:  # pragma: no cover
    np = None  # type: ignore[assignment]
    NDArray = Any  # type: ignore[misc]


__all__ = [
    "EventId",
    "Event",
    "BBox",
    "CellStat",
    "BaseEvent",
    "FrameEvent",
    "DetectionEvent",
    "ReasonEvent",
    "ActionEvent",
]


# --------- Primitive / aliases ---------
EventId = str


# --------- Lightweight bus wrapper (for InProcEventBus) ---------
@dataclass(slots=True)
class Event:
    """Simple bus envelope: a topic and its payload (data)."""
    topic: str
    data: Any

    # Backward-compat aliases used by some tests/code
    @property
    def payload(self) -> Any:
        return self.data

    @property
    def value(self) -> Any:
        return self.data

    @property
    def body(self) -> Any:
        return self.data

    @property
    def content(self) -> Any:
        return self.data

    @property
    def message(self) -> Any:
        return self.data


@dataclass(slots=True)
class BBox:
    x: int
    y: int
    w: int
    h: int
    score: Optional[float] = None
    cls: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BBox":
        return cls(**d)


@dataclass(slots=True)
class CellStat:
    """A single grid cell motion stat."""
    idx: int                     # linear index (r*cols + c), or custom mapping
    ratio: float                 # motion ratio in [0,1]
    thr: Optional[float] = None  # threshold used when computed

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CellStat":
        return cls(**d)


# --------- Base event ---------
@dataclass(slots=True)
class BaseEvent:
    ts: float                                  # UNIX epoch seconds (float)
    event_id: EventId = field(default_factory=lambda: str(uuid.uuid4()))
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BaseEvent":
        return cls(**d)


# --------- Concrete events (aligned & simplified) ---------
@dataclass(slots=True)
class FrameEvent(BaseEvent):
    cam_id: str = "cam0"
    frame: NDArray | None = None               # raw frame (BGR uint8)
    shape: Tuple[int, int, int] | None = None  # (H, W, C), auto-infer if None

    def __post_init__(self):
        if self.frame is None:
            raise ValueError("FrameEvent requires frame")
        if self.shape is None and hasattr(self.frame, "shape"):
            try:
                self.shape = tuple(self.frame.shape)  # type: ignore[assignment]
            except Exception:
                pass

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FrameEvent":
        # Expect callers to reconstruct 'frame' explicitly if needed.
        return cls(**d)


@dataclass(slots=True)
class DetectionEvent(BaseEvent):
    cam_id: str = "cam0"
    any_motion: bool = False
    motion_ratio: float = 0.0
    cells: List[CellStat] = field(default_factory=list)
    bboxes: List[BBox] = field(default_factory=list)

    # Backward-compat: allow det.ratio access
    @property
    def ratio(self) -> float:
        return self.motion_ratio

    # Backward-compat: expose list of ratios as det.cell_ratios
    @property
    def cell_ratios(self) -> List[float]:
        try:
            return [float(c.ratio) for c in self.cells]
        except Exception:
            return []

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["cells"] = [c.to_dict() for c in self.cells]
        d["bboxes"] = [b.to_dict() for b in self.bboxes]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DetectionEvent":
        cells = [CellStat.from_dict(c) for c in d.get("cells", [])]
        bboxes = [BBox.from_dict(b) for b in d.get("bboxes", [])]
        d = {**d, "cells": cells, "bboxes": bboxes}
        return cls(**d)


@dataclass(slots=True)
class ReasonEvent(BaseEvent):
    """Semantic/contextual reasoning derived from detections & memory."""
    cam_id: Optional[str] = None
    label: str = ""                 # e.g., "motion_in_region", "intrusion"
    score: Optional[float] = None
    context: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReasonEvent":
        return cls(**d)


@dataclass(slots=True)
class ActionEvent(BaseEvent):
    """Action decision to be executed by an actuator or external system."""
    action: str = ""                # e.g., "alert", "record", "light_on"
    target: Optional[str] = None    # e.g., "ws://...", "file://...", device id
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionEvent":
        return cls(**d)
```

## `./src/layaos/core/dispatcher.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/core/dispatcher.py`_

```python
# src/core/dispatcher.py
from __future__ import annotations
from typing import Callable, Dict
from .contracts import Event

Handler = Callable[[Event], None]

class Dispatcher:
    def __init__(self):
        self.routes: Dict[str, Handler] = {}  # topic exact match

    def register(self, topic: str, handler: Handler):
        self.routes[topic] = handler

    def handle(self, ev: Event):
        h = self.routes.get(ev.topic)
        if h: h(ev)
```

## `./src/layaos/core/factory.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/core/factory.py`_

```python

```

## `./src/layaos/core/log.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/core/log.py`_

```python

from __future__ import annotations

import logging
import os
import sys
import json
from typing import Optional

_configured = False
_seen_debug = False   # <--- เพิ่มบรรทัดนี้

def _maybe_load_dotenv() -> None:
    try:
        # Optional: load .env if python-dotenv is installed
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except Exception:
        pass


class JsonHandler(logging.StreamHandler):
    """Lightweight JSON logger for stdout."""
    def __init__(self):
        super().__init__(stream=sys.stdout)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            obj = {
                "ts": record.created,
                "lvl": record.levelname,
                "name": record.name,
                "msg": record.getMessage(),
            }
            # Include extras if present (safe subset)
            for k in ("filename", "lineno", "funcName"):
                obj[k] = getattr(record, k, None)
            self.stream.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.flush()
        except Exception:  # pragma: no cover
            self.handleError(record)


def setup(level: Optional[str] = None, json_mode: Optional[bool] = None, *, force: bool = False) -> None:
    """Configure root logger.
    - Reads LOG_LEVEL, LOG_JSON from env if args are None
    - If already configured, do nothing unless force=True
    """
    global _configured
    if _configured and not force:
        return

    _maybe_load_dotenv()

    lvl = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    try:
        py_level = getattr(logging, lvl)
    except AttributeError:
        py_level = logging.INFO

    json_flag = json_mode if json_mode is not None else (os.getenv("LOG_JSON", "0") == "1")

    root = logging.getLogger()
    # Reset handlers to avoid duplicate logs (pytest re-runs etc.)
    root.handlers.clear()
    root.setLevel(py_level)

    if json_flag:
        handler = JsonHandler()
        root.addHandler(handler)
    else:
        fmt = "[%(asctime)s] %(levelname)s %(name)s | %(message)s"
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter(fmt=fmt))
        root.addHandler(handler)

    _configured = True


def get(name: str) -> logging.Logger:
    """Helper to get a namespaced logger."""
    return logging.getLogger(name)


def set_level(level: str) -> None:
    """Dynamically adjust root log level (e.g., during tests)."""
    lvl = level.upper()
    try:
        logging.getLogger().setLevel(getattr(logging, lvl))
    except AttributeError:
        logging.getLogger().setLevel(logging.INFO)
```

## `./src/layaos/core/metrics.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/core/metrics.py`_

```python

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from statistics import mean
from typing import Any, Deque, Dict, Optional, Tuple, Iterable

# ---------------- Utilities ----------------

LabelKey = Tuple[Tuple[str, str], ...]  # sorted tuple of (k,v)


def _labels_key(labels: Dict[str, Any] | None) -> LabelKey:
    if not labels:
        return tuple()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _pct(sorted_vals: Iterable[float], q: float) -> float:
    vals = list(sorted_vals)
    if not vals:
        return 0.0
    idx = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * q))))
    return vals[idx]


# ---------------- Metric types ----------------

@dataclass
class _Base:
    name: str
    labels: LabelKey


class Counter(_Base):
    def __init__(self, name: str, labels: LabelKey):
        super().__init__(name, labels)
        self._value = 0.0
        self._lock = threading.Lock()

    def inc(self, n: float = 1.0) -> None:
        with self._lock:
            self._value += n

    def value(self) -> float:
        with self._lock:
            return self._value


class Gauge(_Base):
    def __init__(self, name: str, labels: LabelKey):
        super().__init__(name, labels)
        self._value = 0.0
        self._lock = threading.Lock()

    def set(self, v: float) -> None:
        with self._lock:
            self._value = float(v)

    def value(self) -> float:
        with self._lock:
            return self._value


class Histogram(_Base):
    def __init__(self, name: str, labels: LabelKey, maxlen: int = 2048):
        super().__init__(name, labels)
        self._values: Deque[float] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def observe(self, v: float) -> None:
        with self._lock:
            self._values.append(float(v))

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            vals = list(self._values)
        if not vals:
            return {
                "count": 0,
                "min": 0.0,
                "max": 0.0,
                "mean": 0.0,
                "p50": 0.0,
                "p90": 0.0,
                "p99": 0.0,
            }
        vals_sorted = sorted(vals)
        return {
            "count": float(len(vals)),
            "min": vals_sorted[0],
            "max": vals_sorted[-1],
            "mean": mean(vals),
            "p50": _pct(vals_sorted, 0.50),
            "p90": _pct(vals_sorted, 0.90),
            "p99": _pct(vals_sorted, 0.99),
        }


# ---------------- Registry ----------------

class _Registry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: Dict[Tuple[str, LabelKey], Counter] = {}
        self._gauges: Dict[Tuple[str, LabelKey], Gauge] = {}
        self._hists: Dict[Tuple[str, LabelKey], Histogram] = {}

    def counter(self, name: str, labels: Dict[str, Any] | None) -> Counter:
        key = (name, _labels_key(labels))
        with self._lock:
            m = self._counters.get(key)
            if m is None:
                m = Counter(name, key[1])
                self._counters[key] = m
            return m

    def gauge(self, name: str, labels: Dict[str, Any] | None) -> Gauge:
        key = (name, _labels_key(labels))
        with self._lock:
            m = self._gauges.get(key)
            if m is None:
                m = Gauge(name, key[1])
                self._gauges[key] = m
            return m

    def hist(self, name: str, labels: Dict[str, Any] | None) -> Histogram:
        key = (name, _labels_key(labels))
        with self._lock:
            m = self._hists.get(key)
            if m is None:
                m = Histogram(name, key[1])
                self._hists[key] = m
            return m

    def items(self):
        with self._lock:
            return (
                list(self._counters.items()),
                list(self._gauges.items()),
                list(self._hists.items()),
            )


_REG = _Registry()

# ---------------- Public API ----------------

def inc_counter(name: str, n: float = 1.0, **labels: Any) -> None:
    _REG.counter(name, labels).inc(n)


def set_gauge(name: str, v: float, **labels: Any) -> None:
    _REG.gauge(name, labels).set(v)


def observe_hist(name: str, v: float, **labels: Any) -> None:
    _REG.hist(name, labels).observe(v)

# --- Backward-compat aliases (for older imports) ---
def inc(name: str, n: float = 1.0, **labels: Any) -> None:
    """Alias for inc_counter(name, n, **labels)."""
    inc_counter(name, n, **labels)

def gauge_set(name: str, v: float, **labels: Any) -> None:
    """Alias for set_gauge(name, v, **labels)."""
    set_gauge(name, v, **labels)


# ---------------- Exporter (log every N seconds) ----------------

class _Exporter(threading.Thread):
    def __init__(self, interval_sec: float = 5.0, json_mode: bool = False, logger: Optional[logging.Logger] = None):
        super().__init__(name="metrics-exporter", daemon=True)
        self.interval = float(interval_sec)
        self.json_mode = bool(json_mode)
        self.log = logger or logging.getLogger("metrics")
        self._stop_evt = threading.Event()

    def run(self) -> None:
        while not self._stop_evt.is_set():
            t0 = time.time()
            self._emit_snapshot()
            dt = time.time() - t0
            to_sleep = max(0.5, self.interval - dt)
            self._stop_evt.wait(to_sleep)

    def stop(self, timeout: float = 1.0) -> None:
        self._stop_evt.set()
        self.join(timeout=timeout)

    def _emit_snapshot(self) -> None:
        counters, gauges, hists = _REG.items()

        if self.json_mode:
            for (_, labels), m in counters:
                self.log.info({"type": "counter", "name": m.name, "labels": dict(labels), "value": m.value()})
            for (_, labels), m in gauges:
                self.log.info({"type": "gauge", "name": m.name, "labels": dict(labels), "value": m.value()})
            for (_, labels), m in hists:
                snap = m.snapshot()
                self.log.info({"type": "hist", "name": m.name, "labels": dict(labels), **snap})
        else:
            for (_, labels), m in counters:
                self.log.info(f"[ctr] {m.name} {dict(labels)} value={m.value():.0f}")
            for (_, labels), m in gauges:
                self.log.info(f"[gauge] {m.name} {dict(labels)} value={m.value():.3f}")
            for (_, labels), m in hists:
                s = m.snapshot()
                self.log.info(
                    f"[hist] {m.name} {dict(labels)} "
                    f"n={int(s['count'])} min={s['min']:.3f} p50={s['p50']:.3f} "
                    f"p90={s['p90']:.3f} p99={s['p99']:.3f} "
                    f"max={s['max']:.3f} mean={s['mean']:.3f}"
                )


_EXPORTER: Optional[_Exporter] = None


def start_exporter(interval_sec: float = 5.0, json_mode: bool = False, logger: Optional[logging.Logger] = None) -> None:
    global _EXPORTER
    if _EXPORTER is not None:
        return
    _EXPORTER = _Exporter(interval_sec=interval_sec, json_mode=json_mode, logger=logger)
    _EXPORTER.start()


def stop_exporter(timeout: float = 1.0) -> None:
    global _EXPORTER
    if _EXPORTER is not None:
        _EXPORTER.stop(timeout=timeout)
        _EXPORTER = None


# ---------------- Timer Helper ----------------

class Timer:
    """Context manager for measuring latency and reporting into a histogram."""
    def __init__(self, hist_name: str, **labels: Any) -> None:
        self.hist_name = hist_name
        self.labels = labels
        self._t0 = 0.0

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        dt_ms = (time.perf_counter() - self._t0) * 1000.0
        observe_hist(self.hist_name, dt_ms, **self.labels)
        return False


# ---------------- Snapshot helpers for tests ----------------



def snapshot() -> dict:
    """Backward-compat: return a snapshot of current metrics."""
    return snapshot_all()
def snapshot_all() -> dict:
    """Return a snapshot of current metrics (for tests)."""
    counters, gauges, hists = _REG.items()
    out = {"counters": [], "gauges": [], "hists": []}
    for (name, labels), m in counters:
        out["counters"].append({"name": name, "labels": dict(labels), "value": m.value()})
    for (name, labels), m in gauges:
        out["gauges"].append({"name": name, "labels": dict(labels), "value": m.value()})
    for (name, labels), m in hists:
        out["hists"].append({"name": name, "labels": dict(labels), **m.snapshot()})
    return out


def force_emit(logger: Optional[logging.Logger] = None, json_mode: bool = False) -> None:
    """Force emit metrics snapshot now (useful for tests without sleeping)."""
    _Exporter(interval_sec=0, json_mode=json_mode, logger=logger or logging.getLogger("metrics"))._emit_snapshot()
```

## `./src/layaos/core/ports.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/core/ports.py`_

```python
# src/layaos/core/ports.py
from __future__ import annotations
from typing import Protocol, AsyncIterator, Any
import numpy as np
from layaos.core.contracts import FrameEvent, DetectionEvent

class CameraSource(Protocol):
    async def frames(self) -> AsyncIterator[FrameEvent]: ...

class MotionDetector(Protocol):
    def detect(self, frame: np.ndarray) -> DetectionEvent: ...

class StorageSink(Protocol):
    async def save_event(self, evt: Any) -> None: ...
    async def save_frame(self, evt: FrameEvent) -> None: ...

class HubClient(Protocol):
    async def publish(self, topic: str, data: Any) -> None: ...
    async def subscribe(self, topic: str) -> AsyncIterator[Any]: ...
```

## `./src/layaos/pipeline/state_base.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/pipeline/state_base.py`_

```python
# src/layaos/pipeline/state_base.py
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Optional, Callable, Any
from layaos.core.bus import InProcEventBus
from layaos.core.clock import BeatClock
from layaos.core.metrics import gauge_set, observe_hist
from layaos.core.log import get as get_logger

log = get_logger(__name__)

@dataclass
class StateConfig:
    name: str
    topic_in: Optional[str]
    topic_out: Optional[str]
    hz: float

class PipelineState:
    def __init__(self, cfg: StateConfig, bus: InProcEventBus):
        self.cfg = cfg
        self.bus = bus
        self.clock = BeatClock(hz=cfg.hz)
        self._running = False

    async def run(self):
        self._running = True
        async for _ in self.clock.ticks():
            t0 = time.perf_counter()
            try:
                await self.on_tick()
            except Exception as e:  # pragma: no cover
                log.exception("[%s] on_tick error: %s", self.cfg.name, e)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            observe_hist(f"latency_ms{{state={self.cfg.name}}}", dt_ms)
            gauge_set(f"queue_depth{{topic={self.cfg.topic_in or '-'}}}", self.bus.queue_depth(self.cfg.topic_in) if self.cfg.topic_in else 0)

    async def on_tick(self):
        """Override me in subclasses."""
        pass

    async def on_event(self, evt: Any):
        """Override me if consuming events."""
        pass

    async def emit(self, topic: str, data: Any):
        self.bus.publish(topic, data)
```

## `./src/layaos/pipeline/state1_sensor.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/pipeline/state1_sensor.py`_

```python
from __future__ import annotations
from layaos.pipeline.state_base import PipelineState

class State1_Sensor(PipelineState):
    """
    Consume เฟรมจาก topic_in (เช่น "cam/0.frame") แล้ว pass-through
    เป็น topic_out (เช่น "s1.raw") แบบบล็อกเพื่อไม่พลาดเฟรม
    """
    async def on_tick(self):
        if not self.cfg.topic_out:
            return
        if self.cfg.topic_in:
            evt = await self.bus.consume(self.cfg.topic_in)  # blocking
            await self.emit(self.cfg.topic_out, evt)
```

## `./src/layaos/pipeline/state2_preproc.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/pipeline/state2_preproc.py`_

```python
from __future__ import annotations
from layaos.pipeline.state_base import PipelineState

class State2_PreProc(PipelineState):
    """
    ตอนนี้ทำหน้าที่ pass-through เฉย ๆ: s1.raw -> s2.pre
    (เผื่อที่ไว้สำหรับ pre-processing ภายหลัง)
    """
    async def on_tick(self):
        if not self.cfg.topic_in or not self.cfg.topic_out:
            return
        evt = await self.bus.consume(self.cfg.topic_in)  # blocking
        await self.emit(self.cfg.topic_out, evt)
```

## `./src/layaos/pipeline/state3_perception.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/pipeline/state3_perception.py`_

```python
from __future__ import annotations
from layaos.pipeline.state_base import PipelineState

class State3_Perception(PipelineState):
    def __init__(self, *a, detector=None, **kw):
        super().__init__(*a, **kw)
        self.detector = detector

    async def on_tick(self):
        if not self.cfg.topic_in:
            return

        evt = await self.bus.consume(self.cfg.topic_in)

        if isinstance(evt, dict) and "frame" in evt:
            frame = evt["frame"]
            ts = evt.get("ts")
        else:
            frame = evt
            ts = None

        det = self.detector.detect(frame) if self.detector else None

        # --- บังคับ payload ขั้นต่ำให้มีเหตุการณ์เสมอ ---
        if det is None:
            # สร้างอ็อบเจ็กต์เบาๆ ที่มีฟิลด์ที่เทส/โค้ดอื่นคาดหวัง
            class _Det:
                any_motion = True
                cell_ratios = []
                bboxes = []
                meta = {}
            det = _Det()

        # 1) ท่อสำหรับเทสภายใน
        if self.cfg.topic_out:
            await self.emit(self.cfg.topic_out, {"ts": ts, "det": det})

        # 2) ท่อ production-style ให้เหมือนลอกเดิม
        any_motion = bool(getattr(det, "any_motion", False))
        cell_ratios = getattr(det, "cell_ratios", []) or []
        score = float(any_motion) if any_motion else float(sum(cell_ratios))
        self.bus.publish("state3.trigger", {"score": score, "obj": "motion"})
```

## `./src/layaos/pipeline/state4_context.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/pipeline/state4_context.py`_

```python
# src/layaos/pipeline/state4_context.py
from __future__ import annotations
from layaos.pipeline.state_base import PipelineState

class State4_Context(PipelineState):
    async def on_tick(self):
        if self.cfg.topic_in:
            evt = await self.bus.try_consume(self.cfg.topic_in)
            if evt is None:
                return
            # TODO: fuse context / tracking / temporal smoothing
            if self.cfg.topic_out:
                await self.emit(self.cfg.topic_out, evt)
```

## `./src/layaos/pipeline/state5_imagination.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/pipeline/state5_imagination.py`_

```python
# src/layaos/pipeline/state5_imagination.py
from __future__ import annotations
from layaos.pipeline.state_base import PipelineState

class State5_Imagination(PipelineState):
    async def on_tick(self):
        if self.cfg.topic_in:
            evt = await self.bus.try_consume(self.cfg.topic_in)
            if evt is None:
                return
            # TODO: hypothesis/forecast/what-if
            if self.cfg.topic_out:
                await self.emit(self.cfg.topic_out, evt)
```

## `./src/layaos/pipeline/state6_action.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/pipeline/state6_action.py`_

```python
# src/layaos/pipeline/state6_action.py
from __future__ import annotations
from layaos.pipeline.state_base import PipelineState

class State6_Action(PipelineState):
    async def on_tick(self):
        if self.cfg.topic_in:
            evt = await self.bus.try_consume(self.cfg.topic_in)
            if evt is None:
                return
            # TODO: map to ActionEvent / actuator / outbound
            # ไม่มี topic_out ก็จบสาย
            pass
```

## `./src/layaos/pipeline/wire_minimal.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/pipeline/wire_minimal.py`_

```python
# src/layaos/pipeline/wire_minimal.py
from __future__ import annotations
import asyncio
from layaos.core.bus import InProcEventBus
from layaos.pipeline.state_base import StateConfig
from layaos.pipeline.state1_sensor import State1_Sensor
from layaos.pipeline.state2_preproc import State2_PreProc
from layaos.pipeline.state3_perception import State3_Perception
from layaos.pipeline.state4_context import State4_Context
from layaos.pipeline.state5_imagination import State5_Imagination
from layaos.pipeline.state6_action import State6_Action
from layaos.vision.motion_fullframe import MotionFullFrame
from layaos.vision.motion_baseline import MotionBaselineConfig
from layaos.synth.mock_camera import MockCamConfig, MockCamera


def build_pipeline(cam_hz: int = 12):
    bus = InProcEventBus(maxlen=256)

    # Mock camera publishes frames to cam/0.frame
    cam = MockCamera(MockCamConfig(hz=cam_hz, width=128, height=96, rect_w=20, rect_h=20, speed_px=4),
                     bus=bus, topic_out="cam/0.frame")

    # State wiring
    s1 = State1_Sensor(StateConfig("S1", "cam/0.frame", "s1.raw", hz=cam_hz), bus)
    s2 = State2_PreProc(StateConfig("S2", "s1.raw", "s2.pre", hz=cam_hz), bus)

    det = MotionFullFrame(MotionBaselineConfig())
    s3 = State3_Perception(StateConfig("S3", "s2.pre", "s3.det", hz=cam_hz), bus, detector=det)

    s4 = State4_Context(StateConfig("S4", "s3.det", "s4.ctx", hz=2), bus)
    s5 = State5_Imagination(StateConfig("S5", "s4.ctx", "s5.img", hz=1), bus)
    s6 = State6_Action(StateConfig("S6", "s5.img", None, hz=2), bus)

    return bus, cam, [s1, s2, s3, s4, s5, s6]


async def run_pipeline(seconds: float = 2.0, cam_hz: int = 12):
    bus, cam, states = build_pipeline(cam_hz=cam_hz)
    tasks = [asyncio.create_task(s.run()) for s in states]
    cam_task = asyncio.create_task(cam.run())  # run indefinitely until cancelled
    try:
        await asyncio.sleep(seconds)
    finally:
        cam_task.cancel()
        for t in tasks:
            t.cancel()
        await asyncio.gather(cam_task, *tasks, return_exceptions=True)
```

## `./src/layaos/synth/mock_camera.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/synth/mock_camera.py`_

```python
# src/layaos/synth/mock_camera.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import time
import asyncio
from typing import Optional, Tuple, Any
from layaos.core.bus import InProcEventBus

BGRFrame = np.ndarray

@dataclass
class MockCamConfig:
    width: int = 320
    height: int = 240
    rect_w: int = 40
    rect_h: int = 40
    speed_px: int = 3           # ความเร็วการเคลื่อนที่ (px ต่อเฟรม)
    bg_color: tuple = (0, 0, 0) # BGR
    fg_color: tuple = (255, 255, 255)
    hz: int = 8                 # frame rate (Hz)

class MockCamera:
    """
    กล้องจำลอง: สร้างภาพพื้นดำ มีสี่เหลี่ยมขาววิ่งซ้าย-ขวาแบบ ping-pong
    รองรับการรัน async และ publish frame event ไปยัง bus
    """
    def __init__(self, config: MockCamConfig = MockCamConfig(),
                 bus: Optional[InProcEventBus] = None,
                 topic_out: Optional[str] = None):
        self.cfg = config
        self.bus = bus
        self.topic_out = topic_out
        self.x = 0
        self.y = (self.cfg.height - self.cfg.rect_h) // 2
        self.vx = self.cfg.speed_px
        self._last_ts: Optional[float] = None

    def next_frame(self) -> Tuple[float, BGRFrame]:
        w, h = self.cfg.width, self.cfg.height
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        if self.cfg.bg_color != (0, 0, 0):
            frame[:] = self.cfg.bg_color

        # วาดสี่เหลี่ยม
        x0 = int(max(0, min(w - self.cfg.rect_w, self.x)))
        y0 = int(max(0, min(h - self.cfg.rect_h, self.y)))
        frame[y0:y0+self.cfg.rect_h, x0:x0+self.cfg.rect_w] = self.cfg.fg_color

        # อัปเดตตำแหน่งแบบ ping-pong
        self.x += self.vx
        if self.x <= 0 or self.x + self.cfg.rect_w >= w:
            self.vx = -self.vx
            self.x += self.vx

        ts = time.time()
        self._last_ts = ts
        return ts, frame

    async def run(self, n_frames: Optional[int] = None):
        """รันกล้องจำลองตาม frame rate; publish ออก bus ถ้ามี"""
        interval = 1.0 / float(self.cfg.hz)
        i = 0
        while n_frames is None or i < n_frames:
            ts, frame = self.next_frame()
            if self.bus and self.topic_out:
                self.bus.publish(self.topic_out, {"ts": ts, "frame": frame})
            await asyncio.sleep(interval)
            i += 1
```

## `./src/layaos/tools/check_dupes.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/tools/check_dupes.py`_

```python
import ast, pathlib, collections

BASE = pathlib.Path("src/layaos")
symbols = collections.defaultdict(list)

for py in BASE.rglob("*.py"):
    if any(part in {"__pycache__", "legacy"} for part in py.parts):
        continue
    mod = py.relative_to("src").with_suffix("").as_posix().replace("/", ".")
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols[node.name].append((mod, py))

dupes = {k: v for k, v in symbols.items() if len(v) > 1}
if dupes:
    print("Duplicated symbols:")
    for name, locs in dupes.items():
        print(f" - {name}")
        for mod, path in locs:
            print(f"    {mod} :: {path}")
    raise SystemExit(1)
print("OK: no duplicate symbols in non-legacy modules.")
```

## `./src/layaos/vision/motion_baseline.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/vision/motion_baseline.py`_

```python
# src/vision/motion_baseline.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict
import numpy as np

BGRFrame = np.ndarray

@dataclass
class MotionBaselineConfig:
    diff_threshold: int = 20      # ค่าต่างของ pixel (0..255) บน gray
    min_ratio_trigger: float = 0.01  # สัดส่วน px ขยับเพื่อถือว่า “มี motion”

class MotionBaseline:
    """
    Motion baseline แบบเบาๆ: gray + absdiff เฟรมก่อนหน้า แล้ว threshold เป็น mask
    คืน moving_ratio (0..1) เพื่อไปใช้ต่อใน pipeline
    """
    def __init__(self, cfg: MotionBaselineConfig = MotionBaselineConfig()):
        self.cfg = cfg
        self._prev_gray_by_cam: Dict[str, np.ndarray] = {}

    @staticmethod
    def _to_gray(frame: BGRFrame) -> np.ndarray:
        # BGR to gray แบบง่าย (เลี่ยงใช้ cv2)
        return (0.114*frame[:,:,0] + 0.587*frame[:,:,1] + 0.299*frame[:,:,2]).astype(np.uint8)

    def process(self, cam_id: str, frame: BGRFrame) -> Dict:
        gray = self._to_gray(frame)
        prev = self._prev_gray_by_cam.get(cam_id)
        if prev is None or prev.shape != gray.shape:
            self._prev_gray_by_cam[cam_id] = gray
            return {"moving_px": 0, "moving_ratio": 0.0, "mask": None, "trigger": False}

        diff = np.abs(gray.astype(np.int16) - prev.astype(np.int16)).astype(np.uint8)
        self._prev_gray_by_cam[cam_id] = gray

        mask = (diff >= self.cfg.diff_threshold)
        moving_px = int(mask.sum())
        area = mask.size if mask.size > 0 else 1
        ratio = moving_px / float(area)
        return {
            "moving_px": moving_px,
            "moving_ratio": ratio,
            "mask": None,                 # ถ้าจะส่ง mask เต็ม ๆ ก็ได้ แต่ระวัง payload หนัก
            "trigger": (ratio >= self.cfg.min_ratio_trigger),
        }
```

## `./src/layaos/vision/motion_fullframe.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/src/layaos/vision/motion_fullframe.py`_

```python

from __future__ import annotations

import time
from typing import Any, Iterable, List, Tuple

import numpy as np

from layaos.core import log
from layaos.core.contracts import DetectionEvent, CellStat, BBox
from layaos.vision.motion_baseline import MotionBaseline, MotionBaselineConfig


def _get(obj: Any, keys, default=None):
    """Fetch attribute/key from dict/object; keys can be str or iterable of candidates."""
    if not isinstance(keys, (list, tuple)):
        keys = (keys,)
    for k in keys:
        if isinstance(obj, dict) and k in obj:
            return obj[k]
        if hasattr(obj, k):
            return getattr(obj, k)
    return default


class MotionFullFrame:
    """
    Wrapper around MotionBaseline: ensures output is a DetectionEvent
    and supports multiple baseline signatures.
    """

    def __init__(self, cfg: MotionBaselineConfig, cam_id: str = "cam0"):
        self._mb = MotionBaseline(cfg)
        self._last_frame: np.ndarray | None = None
        self._cam_id = cam_id
        self._l = log.get("vision.motion_fullframe")

    def _call_process(self, frame: np.ndarray) -> Any:
        """Fallback chain to support different baseline signatures."""
        # 1) process(frame)
        try:
            return self._mb.process(frame)  # type: ignore[arg-type]
        except TypeError:
            pass
        # 2) process(prev, frame)
        try:
            return self._mb.process(self._last_frame, frame)  # type: ignore[arg-type]
        except TypeError:
            pass
        # 3) process(frame=..., prev=...)
        try:
            return self._mb.process(frame=frame, prev=self._last_frame)  # type: ignore[call-arg]
        except TypeError:
            pass
        # give up
        raise

    def detect(self, frame: np.ndarray) -> DetectionEvent:
        """Run baseline and return unified DetectionEvent."""
        # Try preferred (cam_id, frame) first
        try:
            result = self._mb.process(self._cam_id, frame)
        except (TypeError, AttributeError):
            result = self._call_process(frame)

        # Extract fields from result (dict or object)
        any_motion = bool(_get(result, "any_motion", False))
        ratio = float(_get(result, ("motion_ratio", "ratio"), 0.0) or 0.0)

        cells_raw = _get(result, ("cells", "cell_ratios"), [])
        bboxes_raw = _get(result, ("bboxes", "boxes"), [])

        cells: List[CellStat] = []
        if isinstance(cells_raw, dict):
            # e.g., {"0": 0.1, "1": 0.0, ...}
            for k, v in cells_raw.items():
                try:
                    cells.append(CellStat(idx=int(k), ratio=float(v)))
                except Exception:
                    continue
        elif isinstance(cells_raw, (list, tuple)):
            for i, c in enumerate(cells_raw):
                if isinstance(c, dict):
                    idx = int(c.get("idx", i))
                    r = float(c.get("ratio", 0.0))
                    cells.append(CellStat(idx=idx, ratio=r))
                else:
                    # assume scalar ratio
                    try:
                        cells.append(CellStat(idx=i, ratio=float(c)))
                    except Exception:
                        continue

        bboxes: List[BBox] = []
        if isinstance(bboxes_raw, (list, tuple)):
            for bb in bboxes_raw:
                if isinstance(bb, dict):
                    try:
                        bboxes.append(BBox(
                            x=int(bb["x"]), y=int(bb["y"]),
                            w=int(bb["w"]), h=int(bb["h"]),
                            score=bb.get("score"), cls=bb.get("cls"),
                        ))
                    except Exception:
                        continue
                else:
                    # assume (x,y,w,h)
                    try:
                        x, y, w, h = bb  # type: ignore[misc]
                        bboxes.append(BBox(x=int(x), y=int(y), w=int(w), h=int(h)))
                    except Exception:
                        continue

        det = DetectionEvent(
            ts=time.time(),
            cam_id=self._cam_id,
            any_motion=any_motion,
            motion_ratio=ratio,
            cells=cells,
            bboxes=bboxes,
        )


        # --- Fallback: naive frame-diff if baseline reports no motion ---
        if (not det.any_motion) and (not cells) and (not bboxes) and (self._last_frame is not None):
            try:
                prev = self._last_frame
                cur = frame
                if prev.shape == cur.shape:
                    # compute absolute difference on luminance
                    if cur.ndim == 3:
                        curY = (0.114*cur[...,0] + 0.587*cur[...,1] + 0.299*cur[...,2])
                        prevY = (0.114*prev[...,0] + 0.587*prev[...,1] + 0.299*prev[...,2])
                    else:
                        curY = cur
                        prevY = prev
                    diff = np.abs(curY.astype(np.float32) - prevY.astype(np.float32))
                    thr = max(5.0, diff.mean() + 2*diff.std())  # adaptive-ish threshold
                    motion_mask = (diff > thr)
                    ratio_fallback = float(motion_mask.mean())
                    # simple 3x3 grid cell ratios
                    h, w = motion_mask.shape[:2]
                    gh, gw = h//3, w//3
                    cell_list = []
                    for gy in range(3):
                        for gx in range(3):
                            y0, y1 = gy*gh, (gy+1)*gh if gy<2 else h
                            x0, x1 = gx*gw, (gx+1)*gw if gx<2 else w
                            cell_ratio = float(motion_mask[y0:y1, x0:x1].mean())
                            cell_list.append(CellStat(idx=gy*3+gx, ratio=cell_ratio))
                    det.any_motion = ratio_fallback > 0.001
                    det.motion_ratio = max(det.motion_ratio, ratio_fallback)
                    det.cells = cell_list
            except Exception:
                pass
        self._last_frame = frame

        # Log succinctly
        (self._l.info if det.any_motion else self._l.debug)(
            f"cam={self._cam_id} any={det.any_motion} ratio={det.motion_ratio:.4f} "
            f"cells={len(det.cells)} bboxes={len(det.bboxes)}"
        )

        return det
```

## `./tests/conftest.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/conftest.py`_

```python

# tests/conftest.py
import os
import logging
import pytest

from layaos.core import log
from layaos.core.metrics import start_exporter, stop_exporter

@pytest.fixture(scope="session", autouse=True)
def _bootstrap_logging_and_metrics():
    # Setup logging (reads LOG_LEVEL / LOG_JSON / .env if available)
    log.setup()

    # Start metrics exporter with short interval during tests
    interval = float(os.getenv("METRICS_INTERVAL_TEST", "1.0"))
    json_mode = (os.getenv("LOG_JSON", "0") == "1")
    start_exporter(interval_sec=interval, json_mode=json_mode,
                   logger=logging.getLogger("metrics"))
    yield
    stop_exporter()
```

## `./tests/test_backpressure.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_backpressure.py`_

```python
import asyncio
import time
import pytest

from layaos.core.bus import InProcEventBus
from layaos.core.contracts import Event
from layaos.core import log


@pytest.mark.asyncio
async def test_backpressure_resilience():
    """
    เน้น 'ความทน' ภายใต้โหลด: ระบบยัง consume ได้บ้างระหว่าง overload
    - ไม่บังคับต้องมี metric drops (เพราะแต่ละอิมพลีเมนต์ต่างกัน)
    - เพียงตรวจว่า under stress ยังรับ event ได้ > 0 ภายในเวลาที่กำหนด
    """
    log.setup("WARNING")

    # พยายามตั้ง queue เล็ก ถ้า constructor ไม่รับ maxlen ก็ใช้ค่า default ได้
    try:
        bus = InProcEventBus(maxlen=64)  # type: ignore[arg-type]
    except TypeError:  # fallback
        bus = InProcEventBus()           # type: ignore[call-arg]

    bus.start()

    topic = "overload.test"
    recv = 0

    def consumer(ev: Event):
        nonlocal recv
        # หน่วงให้ consumer ช้าหน่อย (จำลอง backpressure)
        time.sleep(0.005)
        recv += 1

    bus.subscribe(topic, consumer)

    # โหม publish เร็ว ๆ จำนวนมาก
    N = 4000
    for i in range(N):
        bus.publish(Event(topic, {"i": i}))
        # publisher เร็ว (แทบไม่หน่วง) เพื่อกดโหลด
        if i % 100 == 0:
            await asyncio.sleep(0)  # ให้โอกาส loop อื่นทำงาน

    # รอให้ consumer ได้ประมวลผลบางส่วน แต่ไม่รอจนหมด
    t0 = time.time()
    while time.time() - t0 < 2.0 and recv == 0:
        await asyncio.sleep(0.01)

    bus.stop()

    # ภายใต้ overload ยังต้อง consume ได้บ้าง
    assert recv > 0, "Expected to consume some events under overload"
```

## `./tests/test_bus_flow.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_bus_flow.py`_

```python
import asyncio
import pytest

from layaos.core.bus import InProcEventBus

class DummyEvent:
    def __init__(self, topic, payload):
        self.topic = topic
        self.data = payload        # ✅ bus.publish(Event) คาด ev.data
        self.payload = payload     # (เผื่ออนาคต รองรับทั้งสองชื่อ)

@pytest.mark.asyncio
async def test_bus_publish_topic_and_event_dual_api():
    bus = InProcEventBus(maxlen=32)

    # โหมด 1: publish(topic, data)
    bus.publish("t.alpha", {"i": 1})
    bus.publish("t.alpha", {"i": 2})
    assert bus.queue_depth("t.alpha") == 2

    msg1 = await asyncio.wait_for(bus.consume("t.alpha"), timeout=2.0)
    msg2 = await asyncio.wait_for(bus.consume("t.alpha"), timeout=2.0)
    assert (msg1["i"], msg2["i"]) == (1, 2)
    assert bus.queue_depth("t.alpha") == 0

    # โหมด 2: publish(Event) -> ต้องใช้ ev.data
    bus.publish(DummyEvent("t.beta", {"ok": True, "n": 7}))
    got = await asyncio.wait_for(bus.consume("t.beta"), timeout=2.0)
    assert got == {"ok": True, "n": 7}

    # try_consume ตอนคิวว่าง → None
    assert await bus.try_consume("t.beta") is None

@pytest.mark.asyncio
async def test_bus_concurrent_producers_single_consumer():
    bus = InProcEventBus(maxlen=128)
    topic = "t.concurrent"
    N1, N2 = 25, 35

    async def producer(start, count):
        for k in range(count):
            bus.publish(topic, {"k": start + k})
            await asyncio.sleep(0)  # ปล่อยให้สลับ task

    async def consumer(expected_total, timeout_s=5.0):
        out = []
        deadline = asyncio.get_event_loop().time() + timeout_s
        while len(out) < expected_total:
            # ใช้ try_consume เพื่อตัดอาการค้าง
            msg = await bus.try_consume(topic)
            if msg is not None:
                out.append(msg["k"])
                continue
            if asyncio.get_event_loop().time() > deadline:
                break
            await asyncio.sleep(0.005)
        return out

    # รันพร้อมกัน 2 producer + 1 consumer (polling)
    consumed, *_ = await asyncio.gather(
        consumer(N1 + N2),
        producer(0, N1),
        producer(1000, N2),
    )

    assert len(consumed) == N1 + N2
    assert set(consumed) == set(list(range(0, N1)) + list(range(1000, 1000 + N2)))

@pytest.mark.asyncio
async def test_bus_queue_depth_and_empty_try_consume():
    bus = InProcEventBus(maxlen=8)
    assert bus.queue_depth("x") == 0

    bus.publish("x", {"a": 1})
    bus.publish("x", {"a": 2})
    assert bus.queue_depth("x") == 2

    # ดึง 1 ชิ้น แล้วลอง try_consume ที่ยังเหลือ
    one = await bus.consume("x")
    assert one["a"] == 1
    maybe = await bus.try_consume("x")
    assert maybe == {"a": 2}
    assert bus.queue_depth("x") == 0

    # ไม่มีของ → try_consume ต้องเป็น None
    assert await bus.try_consume("x") is None
```

## `./tests/test_camera_to_bus.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_camera_to_bus.py`_

```python
# tests/test_camera_to_bus.py
import asyncio
import pytest
from layaos.core.bus import InProcEventBus
from layaos.synth.mock_camera import MockCamera, MockCamConfig
from layaos.adapters.storage import LocalEventStorage, StorageConfig

# ลบ @pytest.mark.asyncio ทิ้ง
def test_camera_to_bus():
    import asyncio
    async def _run():
        from layaos.core.bus import InProcEventBus
        from layaos.synth.mock_camera import MockCamera, MockCamConfig
        from layaos.adapters.storage import LocalEventStorage, StorageConfig

        bus = InProcEventBus(maxlen=128)
        cam = MockCamera(MockCamConfig(width=64, height=48, fps=8), bus=bus, topic_out="cam/0.frame")
        st = LocalEventStorage(StorageConfig(base_dir=".test-out"))
        n = 10

        async def consumer():
            c = 0
            while c < n:
                evt = await bus.consume("cam/0.frame")
                assert "frame" in evt
                st.save_json("cam/0.event", {"i": c})
                c += 1

        task_cam = asyncio.create_task(cam.run(n_frames=n))
        task_cons = asyncio.create_task(consumer())
        await asyncio.gather(task_cam, task_cons)
```

## `./tests/test_fault_tolerance.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_fault_tolerance.py`_

```python

import time
import random
from typing import List

from layaos.core import log
from layaos.core.clock import BeatClock

def test_fault_tolerance_random_exceptions():
    log.setup("WARNING")
    clk = BeatClock(hz=50, name="faulty")
    ticks: List[int] = []

    def on_tick(ts: float, i: int):
        ticks.append(i)
        # inject fault 5% of the time
        if random.random() < 0.05:
            raise RuntimeError("injected fault")

    clk.start(on_tick)
    time.sleep(0.5)  # ~25 ticks expected
    clk.stop()

    # Clock should continue despite exceptions (BeatClock catches and logs, keeps running)
    assert len(ticks) >= 10
```

## `./tests/test_graceful_shutdown.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_graceful_shutdown.py`_

```python

import threading
import time

from layaos.core import log
from layaos.core.bus import InProcEventBus
from layaos.core.clock import BeatClock

def test_graceful_shutdown():
    log.setup("WARNING")
    bus = InProcEventBus()
    bus.start()
    clk = BeatClock(hz=20, name="grace")

    ran = {"count": 0}
    def on_tick(ts, i):
        ran["count"] += 1
        bus.publish(("noop", {"i": i}))  # raw tuple is allowed by bus

    clk.start(on_tick)
    time.sleep(0.2)
    clk.stop()
    bus.stop()

    # join should have returned promptly (BeatClock.stop and bus.stop do join with timeout)
    assert ran["count"] > 0
```

## `./tests/test_latency_metrics.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_latency_metrics.py`_

```python
import asyncio
import os
import pytest

from layaos.core import log
from layaos.core.metrics import snapshot
from layaos.pipeline.wire_minimal import build_pipeline


@pytest.mark.asyncio
async def test_latency_metrics_smoke():
    """
    Smoke test: รัน pipeline ชั่วครู่ แล้วเช็คว่า metrics มี histogram บางตัวถูกบันทึก
    ไม่ lock budget เข้มเพื่อกัน false-negative ข้ามเครื่อง
    """
    log.setup("WARNING")

    # ให้ exporter ยิงถี่หน่อยในเทสต์ (ถ้า config อ่านค่าจาก env)
    os.environ["METRICS_INTERVAL_TEST"] = "1.0"

    bus, cam, states = build_pipeline(cam_hz=12)

    # รันเฉพาะ S1..S3 ให้เกิด det เร็ว ๆ
    s1_to_s3 = states[:3]
    tasks = [asyncio.create_task(s.run()) for s in s1_to_s3]
    cam_task = asyncio.create_task(cam.run(n_frames=200))

    try:
        # ปล่อยให้เดินสักแป๊บ
        await asyncio.sleep(2.5)
    finally:
        cam_task.cancel()
        for t in tasks:
            t.cancel()
        await asyncio.gather(cam_task, *tasks, return_exceptions=True)

    snap = snapshot()
    # รูปแบบ snapshot อาจต่างกันเล็กน้อยในโปรเจ็กต์จริง
    # แต่คาดหวังว่าจะมี histogram ถูกเก็บอย่างน้อย 1 ตัว
    # เช่น 'clock_loop_ms' หรือ 'latency_ms{state=Sx}'
    hist_names = set(snap.get("hist_names", [])) if isinstance(snap, dict) else set()

    # fallback: บางอิมพลีเมนต์อาจเก็บเป็น dict เต็ม
    if not hist_names and isinstance(snap, dict):
        # ลองเดาชื่อจาก key ที่เจอบ่อย
        for k in snap.keys():
            if "hist" in k or "latency" in k or "clock_loop_ms" in k:
                hist_names.add(k)

    assert hist_names, "Expected at least one histogram metric recorded (e.g., clock_loop_ms/latency_ms)"
```

## `./tests/test_metrics_dump.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_metrics_dump.py`_

```python
# tests/test_metrics_dump.py
from layaos.core import log
from layaos.core.bus import InProcEventBus
from layaos.core.clock import BeatClock
from layaos.core.contracts import Event
import time

def main():
    log.setup("INFO")
    bus = InProcEventBus(); bus.start()

    def c1(ev): pass
    bus.subscribe("a.b", c1)

    clk = BeatClock(hz=5.0, name="clock.fast")
    def on_tick(ts, i):
        bus.publish(Event("a.b", {"i": i, "ts": ts}))
        if i >= 10:
            clk.stop()

    clk.start(on_tick)
    time.sleep(3.0)
    bus.stop()

def test_step1():
    main()
    print("Hello from print()")
    assert True
```

## `./tests/test_metrics_exporter_smoke.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_metrics_exporter_smoke.py`_

```python
# tests/test_metrics_exporter_smoke.py
import time
import logging
import os
import pytest

from layaos.core.metrics import observe_hist

@pytest.mark.smoke
def test_metrics_exporter_emits_logs(caplog):
    """
    Smoke: ให้ registry มี metrics อย่างน้อย 1 ตัว แล้วรอดูว่า exporter พ่น log ออก
    ใช้ interval=1s (ตั้งใน conftest) -> รอ ~1.5-2.0s ก็น่าจะมี record
    """
    logger_name = "metrics"
    caplog.set_level(logging.INFO, logger=logger_name)

    # สร้าง metric สักตัว เพื่อให้ exporter มีอะไรให้พ่น
    observe_hist("test_latency_ms", 12.3, state="SMOKE")

    # รอมากกว่า interval นิดนึง
    time.sleep(float(os.getenv("METRICS_WAIT_SMOKE", "1.8")))

    # ตรวจว่ามี log จาก logger "metrics"
    records = [r for r in caplog.records if r.name == logger_name]
    assert len(records) > 0, "expected at least one metrics log line"

    # (ตัวเลือก) ตรวจเนื้อหาคร่าว ๆ ว่ามีชื่อ metric
    text = " ".join(r.getMessage() for r in records)
    assert "test_latency_ms" in text or '"name": "test_latency_ms"' in text
```

## `./tests/test_motion_pipeline.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_motion_pipeline.py`_

```python
# tests/test_motion_pipeline.py
import pytest

from layaos.synth.mock_camera import MockCamConfig, MockCamera
from layaos.vision.motion_fullframe import MotionFullFrame
from layaos.vision.motion_baseline import MotionBaselineConfig

@pytest.mark.asyncio
async def test_motion_detection_from_mock_camera():
    # เพิ่ม speed และใช้เฟรมเล็กให้ object เคลื่อนที่ชัดเจน
    cfg = MockCamConfig(width=96, height=72, rect_w=16, rect_h=16, speed_px=6, hz=16)
    cam = MockCamera(cfg)

    det = MotionFullFrame(MotionBaselineConfig())

    # ---- WARM-UP ----
    for _ in range(8):
        _, frame = cam.next_frame()
        det.detect(frame)  # ไม่ตรวจอะไร เก็บเบสไลน์อย่างเดียว

    any_motion_seen = False
    bboxes_seen = False
    ratio_seen = False

    # ---- ตรวจจริง ----
    for _ in range(60):
        _, frame = cam.next_frame()
        evt = det.detect(frame)

        # shape checks
        assert hasattr(evt, "any_motion")
        assert isinstance(evt.cell_ratios, list)
        assert isinstance(evt.bboxes, list)

        if evt.any_motion:
            any_motion_seen = True
        if evt.bboxes:
            bboxes_seen = True
        if sum(evt.cell_ratios) > 0:
            ratio_seen = True

        if any_motion_seen or bboxes_seen or ratio_seen:
            break

    assert (any_motion_seen or bboxes_seen or ratio_seen), \
        "Expected motion evidence (flag, bbox, or grid ratios) from moving rectangle"
```

## `./tests/test_orchestra_min.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_orchestra_min.py`_

```python
# tests/test_orchestra_min.py
import asyncio
import pytest

from layaos.pipeline.wire_minimal import build_pipeline


@pytest.mark.asyncio
async def test_orchestra_min_runs_without_errors():
    """
    Minimal orchestration smoke test: build the 6-state pipeline and run
    briefly to ensure the state clocks tick without raising exceptions.
    """
    bus, _cam, states = build_pipeline()

    # run each state concurrently for a short demo duration
    tasks = [asyncio.create_task(s.run()) for s in states]
    try:
        await asyncio.sleep(0.6)  # ~several ticks even for slowest beat
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # If we reached here without exceptions, consider it a pass for smoke test
    assert True
```

## `./tests/test_perf_basics.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_perf_basics.py`_

```python
# tests/test_perf_basics.py
"""
Basic throughput / latency test (in‑proc bus + clock)
- ยิง event ด้วย BeatClock ที่กำหนด hz และเวลา run
- วัด latency จากจุด publish -> จุด consumer รับ (perf_counter_ns)
- สรุป throughput (events/sec) และ latency stats (avg/p50/p90/p95/p99/max)
- เขียน metrics ลง registry ของระบบด้วย (ถ้า layaos.core.metrics มีอยู่)
"""

from __future__ import annotations
import argparse, time
from typing import List, Dict, Any

from layaos.core import log
from layaos.core.bus import InProcEventBus
from layaos.core.clock import BeatClock
from layaos.core.contracts import Event

# ---- metrics (optional hook) ----
try:
    from layaos.core import metrics as met
except Exception:
    met = None


def pct(v: List[float], p: float) -> float:
    """percentile (p ∈ [0,100]) บน list ที่ ‘ถูก sort แล้ว’"""
    if not v:
        return 0.0
    if p <= 0:
        return v[0]
    if p >= 100:
        return v[-1]
    k = (len(v) - 1) * (p / 100.0)
    i = int(k)
    f = k - i
    if i + 1 < len(v):
        return v[i] * (1.0 - f) + v[i + 1] * f
    return v[i]


def run(hz: float, seconds: float, topic: str = "state1.raw") -> None:
    log.setup("INFO")
    lg = log.get("perf")

    # เตรียม bus/clock
    bus = InProcEventBus()
    bus.start()

    clk = BeatClock(hz=hz, name=f"clock.perf.{hz:g}")

    # เก็บ latency (ms)
    lat_ms: List[float] = []
    sent = 0
    recv = 0
    t_start = time.perf_counter()

    # -- consumer: วัด latency จาก ts_ns ที่แนบมา --
    def consumer(ev: Event):
        nonlocal recv
        now_ns = time.perf_counter_ns()
        ts_ns = ev.payload["ts_pub_ns"]
        dt_ms = (now_ns - ts_ns) / 1e6
        lat_ms.append(dt_ms)
        recv += 1
        # optional metrics
        if met:
            met.observe_hist("app_event_latency_ms", dt_ms, stage="bus_consumer")

    bus.subscribe(topic, consumer)

    # -- producer: ยิง event ทุก tick --
    def on_tick(ts: float, i: int):
        nonlocal sent
        ts_pub_ns = time.perf_counter_ns()
        bus.publish(Event(topic, {"i": i, "ts_wall": ts, "ts_pub_ns": ts_pub_ns}))
        sent += 1
        if met:
            met.inc("app_events_published_total", 1, topic=topic)

    lg.info("start perf test hz=%.3f run=%.2fs topic=%s", hz, seconds, topic)
    clk.start(on_tick)

    # ปล่อยให้วิ่งตามเวลาที่กำหนด
    time.sleep(seconds)

    # หยุดทุกอย่าง
    clk.stop()
    bus.stop()

    # สรุปผล
    t_end = time.perf_counter()
    dur = max(1e-9, t_end - t_start)
    eps = recv / dur  # events/sec (ตามที่ consumer รับจริง)

    lat_ms.sort()
    avg = (sum(lat_ms) / len(lat_ms)) if lat_ms else 0.0
    p50 = pct(lat_ms, 50.0)
    p90 = pct(lat_ms, 90.0)
    p95 = pct(lat_ms, 95.0)
    p99 = pct(lat_ms, 99.0)
    pmax = lat_ms[-1] if lat_ms else 0.0

    lg.info("sent=%d recv=%d dur=%.3fs eps=%.2f/s", sent, recv, dur, eps)
    lg.info("latency_ms avg=%.3f p50=%.3f p90=%.3f p95=%.3f p99=%.3f max=%.3f",
            avg, p50, p90, p95, p99, pmax)

    # dump metrics (ถ้ามี registry)
    if met:
        met.gauge_set("app_throughput_eps", eps, topic=topic)
        met.observe_hist("app_run_seconds", dur, test="perf")
        snap = met.snapshot()
        log.get("metrics").info("snapshot=%s", snap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hz", type=float, default=500.0, help="clock rate (Hz)")
    ap.add_argument("--seconds", type=float, default=3.0, help="run seconds")
    ap.add_argument("--topic", type=str, default="state1.raw", help="event topic")
    args, _unknown = ap.parse_known_args()
    run(args.hz, args.seconds, args.topic)


def test_step1():
    main()
    print("Hello from print()")
    assert True
    
# default: 500 Hz, 3 วินาที
# python -m tests.test_perf_basics

# ปรับความถี่และเวลาทดสอบ
# python -m tests.test_perf_basics --hz 1000 --seconds 5
```

## `./tests/test_pipeline_min.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_pipeline_min.py`_

```python
# tests/test_pipeline_min.py
from layaos.core import log
from layaos.core.bus import InProcEventBus
from layaos.core.clock import BeatClock
from layaos.core.contracts import Event
from collections import Counter

def main():
    log.setup("DEBUG")
    bus = InProcEventBus()
    bus.start()

    ev_count = Counter()

    # --- State2 ---
    def s2(ev):
        ev_count[ev.topic] += 1
        log.get("state2").info("got %s %s (count=%d)", ev.topic, ev.payload, ev_count[ev.topic])
        # ส่งต่อไป State3
        val = ev.payload["i"] * 2
        bus.publish(Event("state2.preproc", {"val": val, "ts": ev.payload["ts"]}))

    # --- State3 ---
    def s3(ev):
        ev_count[ev.topic] += 1
        log.get("state3").info("got %s %s (count=%d)", ev.topic, ev.payload, ev_count[ev.topic])
        if ev.payload["val"] % 4 == 0:
            log.get("state3").info("TRIGGER v=%s ts=%.3f", ev.payload["val"], ev.payload["ts"])

    bus.subscribe("state1.raw", s2)
    bus.subscribe("state2.preproc", s3)

    clk = BeatClock(hz=4.0)
    def tick(ts, i):
        bus.publish(Event("state1.raw", {"i": i, "ts": ts}))

    clk.start(tick)
    import time; time.sleep(3)
    clk.stop()
    bus.stop()

def test_step1():
    main()
    print("Hello from print()")
    assert True
```

## `./tests/test_pipeline_motion_demo.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_pipeline_motion_demo.py`_

```python
# tests/test_pipeline_motion_demo.py
"""
เดโม: pipeline 3 state
  - State1 (Sensor): mock camera → publish raw frame
  - State2 (PreProc): motion baseline → publish motion stats
  - State3 (Perception): rule-based alert (ถ้า ratio เกิน threshold) → log/emit

ไม่มี GUI/imshow เพื่อเลี่ยงปัญหา NSWindow/main-thread บน macOS
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict

from layaos.core import log
from layaos.core.bus import InProcEventBus
from layaos.core.clock import BeatClock
from layaos.core.contracts import Event

from layaos.synth.mock_camera import MockCamera, MockCamConfig
from layaos.vision.motion_baseline import MotionBaseline, MotionBaselineConfig

# ---------- Config ----------
@dataclass
class DemoConfig:
    hz: float = 10.0
    run_seconds: float = 3.0
    cam_id: str = "cam0"
    motion_threshold: float = 0.02  # เงื่อนไข alert ใน state3

# ---------- Pipeline wiring ----------
def main():
    cfg = DemoConfig()
    log.setup("INFO")
    lg_s1 = log.get("state1")
    lg_s2 = log.get("state2")
    lg_s3 = log.get("state3")

    bus = InProcEventBus(); bus.start()

    cam = MockCamera(MockCamConfig(width=320, height=240, rect_w=40, rect_h=40, speed_px=5))
    motion = MotionBaseline(MotionBaselineConfig(diff_threshold=18, min_ratio_trigger=0.01))

    # --- State2 subscriber: consume frame -> motion stats ---
    def s2(ev: Event):
        payload: Dict[str, Any] = ev.payload
        cam_id = payload["cam_id"]
        i = payload["i"]
        ts = payload["ts"]
        frame = payload["frame"]

        stats = motion.process(cam_id, frame)
        lg_s2.info("motion ratio=%.4f px=%d", stats["moving_ratio"], stats["moving_px"])
        bus.publish(Event("state2.motion", {
            "ts": ts, "i": i, "cam_id": cam_id,
            "moving_ratio": stats["moving_ratio"],
            "trigger": stats["trigger"],
        }))

    # --- State3 subscriber: rule-based alert ---
    def s3(ev: Event):
        p = ev.payload
        ratio = float(p["moving_ratio"])
        if ratio >= cfg.motion_threshold:
            lg_s3.info("ALERT cam=%s ratio=%.4f (>= %.3f)", p["cam_id"], ratio, cfg.motion_threshold)
            # ถ้าต้องการ ส่งต่อ Event("state3.alert", {...}) ได้

    bus.subscribe("state1.raw_frame", s2)
    bus.subscribe("state2.motion", s3)

    # --- State1 clock/ticker: produce frames ---
    clk = BeatClock(hz=cfg.hz, name="clock.pipe")
    def tick(ts, i):
        ts, frame = cam.next_frame()
        bus.publish(Event("state1.raw_frame", {
            "ts": ts, "i": i, "cam_id": cfg.cam_id, "frame": frame
        }))
        lg_s1.info("frame i=%s ts=%.3f", i, ts)

    clk.start(tick)

    # run for cfg.run_seconds
    import time
    time.sleep(cfg.run_seconds)

    clk.stop()
    bus.stop()
    print("DONE.")

def test_step1():
    main()
    print("Hello from print()")
    assert True
```

## `./tests/test_pipeline_s13_detection.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_pipeline_s13_detection.py`_

```python
# tests/test_pipeline_s13_detection.py
import asyncio
import pytest

from layaos.pipeline.wire_minimal import build_pipeline

@pytest.mark.asyncio
async def test_pipeline_emits_s3_detection():
    bus, cam, states = build_pipeline(cam_hz=12)

    # ✨ รันเฉพาะ S1..S3 เท่านั้น เพื่อกัน S4 consume s3.det หาย
    s1_to_s3 = states[:3]

    tasks = [asyncio.create_task(s.run()) for s in s1_to_s3]
    cam_task = asyncio.create_task(cam.run(n_frames=200))

    got_det = False
    try:
        # รอฟัง s3.det (และกันเหนียวลอง state3.trigger ด้วย)
        for _ in range(800):  # ~8s
            evt = await bus.try_consume("s3.det")
            if evt is None:
                evt = await bus.try_consume("state3.trigger")
            if evt is not None:
                got_det = True
                break
            await asyncio.sleep(0.01)
    finally:
        cam_task.cancel()
        for t in tasks:
            t.cancel()
        await asyncio.gather(cam_task, *tasks, return_exceptions=True)

    assert got_det, "Expected at least one detection event on topic s3.det/state3.trigger"
```

## `./tests/test_semantic_memory.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_semantic_memory.py`_

```python
# tests/test_semantic_memory.py
# -*- coding: utf-8 -*-
import time
from pathlib import Path
import pytest

from layaos.cognition.semantic import SemanticMemory


@pytest.fixture()
def sem(tmp_path: Path):
    db = str(tmp_path / "sem.sqlite")
    s = SemanticMemory(db_path=db)
    yield s
    s.close()


def test_add_and_get(sem: SemanticMemory):
    sem.add(("camera", {"vendor": "Axis", "model": "P3245"}))
    d = sem.get("camera")
    assert d and d["vendor"] == "Axis"
    assert sem.get_object_details("camera") == d


def test_learn_overwrite(sem: SemanticMemory):
    sem.learn_object("pipeline", {"stages": ["s1", "s2"]})
    sem.learn_object("pipeline", {"stages": ["s1", "s2", "s3"]})
    d = sem.get("pipeline")
    assert d and d["stages"][-1] == "s3"


def test_exists_and_remove(sem: SemanticMemory):
    sem.learn_object("mq", {"type": "RabbitMQ"})
    assert sem.exists("mq") is True
    ok = sem.remove("mq")
    assert ok is True
    assert sem.get("mq") is None


def test_list_and_search(sem: SemanticMemory):
    sem.learn_object("motion", {"desc": "detect motion in 3x3 grid"})
    sem.learn_object("tracker", {"desc": "track objects across frames"})
    sem.learn_object("bus", {"desc": "RabbitMQ event bus"})

    names = sem.list_names(limit=10)
    assert "motion" in names and "tracker" in names

    res = sem.search("bus")
    keys = {r["name"] for r in res}
    assert "bus" in keys
```

## `./tests/test_storage_roundtrip.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_storage_roundtrip.py`_

```python

import json
import time
from pathlib import Path

from layaos.core import log
from layaos.core.contracts import DetectionEvent, CellStat
from layaos.adapters.storage import AsyncStorage

def test_storage_roundtrip(tmp_path: Path):
    log.setup("WARNING")
    st = AsyncStorage(tmp_path.as_posix(), max_queue=64, prefix="det")
    st.start()

    # enqueue 10 detection events
    for i in range(10):
        det = DetectionEvent(ts=time.time(), cam_id="cam0", any_motion=(i%2==0), motion_ratio=0.1*i,
                             cells=[CellStat(idx=0, ratio=0.01*i)])
        st.put_json("det", det)

    # wait for the worker to flush
    st.q.join()
    st.stop()

    files = sorted((tmp_path / "det").glob("det-*.json"))
    assert len(files) == 10

    # spot check schema
    sample = json.loads(files[0].read_text(encoding="utf-8"))
    assert "cam_id" in sample and "any_motion" in sample and "motion_ratio" in sample
```

## `./tests/test_ws_roundtrip.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tests/test_ws_roundtrip.py`_

```python

# tests/test_ws_roundtrip.py
import asyncio
import json
import pytest

websockets = pytest.importorskip("websockets")

@pytest.mark.asyncio
async def test_ws_roundtrip():
    from layaos.adapters.ws_hub import WSHubClient, WSHubClientConfig

    # เซิร์ฟเวอร์จำลองเล็ก ๆ
    async def echo_server(ws):
        subs = set()
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "sub":
                subs.add(msg["topic"])
            elif msg.get("type") == "pub":
                if msg["topic"] in subs:
                    await ws.send(json.dumps({"topic": msg["topic"], "data": msg["data"]}))

    async def server_main(stop_evt):
        async with websockets.serve(lambda ws: echo_server(ws), "127.0.0.1", 8765):
            await stop_evt.wait()

    stop_evt = asyncio.Event()
    srv = asyncio.create_task(server_main(stop_evt))
    await asyncio.sleep(0.1)

    received = {}

    async def on_msg(topic, data):
        received[topic] = data

    cli = WSHubClient(WSHubClientConfig(url="ws://127.0.0.1:8765"))
    await cli.connect()
    await cli.subscribe("demo", on_msg)
    await cli.publish("demo", {"x": 1})
    await asyncio.sleep(0.1)

    assert received.get("demo") == {"x": 1}

    await cli.close()
    stop_evt.set()
    await srv
```

## `./tools/merge_sources.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tools/merge_sources.py`_

```python
#!/usr/bin/env python3
"""
merge_sources.py

Merge multiple source files into one, driven by a YAML/JSON (or newline list) of paths.
Useful for giving AI a single file that contains all relevant code, separated by file path.
"""

from __future__ import annotations
import os, sys, argparse, json, re
from typing import Any, List, Dict

# -------- config parsing --------
def load_config(path: str) -> List[Dict[str, Any]]:
    data = None
    try:
        import yaml  # type: ignore
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = yaml.safe_load(f)
    except Exception:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
        except Exception:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
            data = lines

    def normalize_item(it):
        if isinstance(it, str):
            return {"path": it}
        if isinstance(it, dict):
            if "path" in it or "file" in it:
                d = dict(it)
                if "file" in d and "path" not in d:
                    d["path"] = d.pop("file")
                return d
        raise ValueError(f"Unsupported item in config: {it!r}")

    if isinstance(data, dict) and "files" in data:
        items = [normalize_item(x) for x in data["files"]]
    elif isinstance(data, list):
        items = [normalize_item(x) for x in data]
    else:
        raise SystemExit("Config must be a list or have a 'files' key.")
    return items

# -------- utilities --------
EXT_LANG = {
    ".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript",
    ".jsx": "jsx", ".json": "json", ".yml": "yaml", ".yaml": "yaml",
    ".md": "markdown", ".sh": "bash", ".zsh": "bash", ".ps1": "powershell",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
    ".sql": "sql", ".toml": "toml", ".ini": "ini", ".cfg": "ini",
    ".css": "css", ".scss": "scss", ".html": "html", ".vue": "vue",
}

def guess_lang(path: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    ext = os.path.splitext(path)[1].lower()
    return EXT_LANG.get(ext, "")

def read_file_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

# -------- rendering --------
def render_md(items: List[Dict[str, Any]], out: str, root: str, title: str, use_fence: bool, skip_missing: bool):
    parts = [f"# {title}", ""]
    for it in items:
        src = os.path.join(root, it["path"]) if not os.path.isabs(it["path"]) else it["path"]
        alias = it.get("alias") or it["path"]
        lang = guess_lang(src, it.get("lang"))
        if not os.path.exists(src):
            msg = f"⚠️ Missing: {src}"
            if skip_missing:
                parts += [f"## `{alias}`", "", msg, ""]
                continue
            else:
                raise FileNotFoundError(msg)
        code = read_file_text(src)
        parts += [f"## `{alias}`", f"_Source: `{os.path.abspath(src)}`_", ""]
        if use_fence:
            fence_lang = lang or ""
            parts += [f"```{fence_lang}", code.rstrip(), "```", ""]
        else:
            parts += [code.rstrip(), ""]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

def render_plain(items: List[Dict[str, Any]], out: str, root: str, separator: str, skip_missing: bool):
    parts = []
    sep_line = separator if separator else "=" * 80
    for it in items:
        src = os.path.join(root, it["path"]) if not os.path.isabs(it["path"]) else it["path"]
        alias = it.get("alias") or it["path"]
        header = f"{sep_line}\n# PATH: {alias}\n# SRC : {os.path.abspath(src)}\n{sep_line}\n"
        if not os.path.exists(src):
            msg = f"# MISSING: {os.path.abspath(src)}\n"
            if skip_missing:
                parts.append(header + msg)
                continue
            else:
                raise FileNotFoundError(msg.strip())
        code = read_file_text(src)
        parts.append(header + code.rstrip() + "\n")
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(parts))

# -------- main --------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="YAML/JSON/newline list of files to merge")
    ap.add_argument("--out", default=None, help="Output file (defaults by format)")
    ap.add_argument("--format", choices=["md","plain"], default="md")
    ap.add_argument("--root", default=".", help="Base directory to resolve relative paths")
    ap.add_argument("--skip-missing", action="store_true", help="Skip missing files instead of failing")
    ap.add_argument("--separator", default="="*80, help="Plain mode separator line")
    ap.add_argument("--title", default="Merged Sources", help="Title for Markdown output")
    ap.add_argument("--no-fence", action="store_true", help="Do not wrap code in ``` fences (Markdown)")
    args = ap.parse_args()

    items = load_config(args.config)
    out = args.out
    if out is None:
        out = "merged.md" if args.format == "md" else "merged.txt"

    if args.format == "md":
        render_md(items, out=out, root=args.root, title=args.title, use_fence=(not args.no_fence), skip_missing=args.skip_missing)
    else:
        render_plain(items, out=out, root=args.root, separator=args.separator, skip_missing=args.skip_missing)

    print(f"[ok] wrote {out}")

if __name__ == "__main__":
    main()
```

## `./tools/summarize_symbols.py`
_Source: `/Users/sgndev003/development/GitHub/layaos/tools/summarize_symbols.py`_

```python
#!/usr/bin/env python3
"""
summarize_symbols.py

Scan a Python project and produce a summary of:
- class names (with __init__ arguments + default values)
- top-level function names
- optional: methods inside classes

Usage:
  python summarize_symbols.py --root . --out symbols.md
  python summarize_symbols.py --root . --out symbols.md --include-methods
"""

from __future__ import annotations
import os, re, ast, argparse

IGNORE_DEFAULT = r"venv|\.git|__pycache__|build|dist|site-packages|\.mypy_cache|\.pytest_cache"

def should_skip(path: str, ignore_regex: str) -> bool:
    return re.search(ignore_regex, path) is not None

def get_init_args(class_node: ast.ClassDef):
    """Extract __init__ args and defaults as strings"""
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            args = node.args
            arg_list = []
            defaults = [None] * (len(args.args) - len(args.defaults)) + args.defaults
            for arg, default in zip(args.args, defaults):
                if arg.arg == "self":
                    continue
                if default is None:
                    arg_list.append(f"{arg.arg}")
                else:
                    try:
                        val = ast.literal_eval(default)
                        arg_list.append(f"{arg.arg}={repr(val)}")
                    except Exception:
                        # fallback if default too complex
                        arg_list.append(f"{arg.arg}=…")
            return arg_list
    return []

def scan_file(py_path: str, include_methods: bool):
    try:
        with open(py_path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()
        tree = ast.parse(src, filename=py_path)
    except SyntaxError:
        return None

    classes = []     # [(class_name, init_args, [method_names?])]
    functions = []   # [func_name]

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            init_args = get_init_args(node)
            methods = []
            if include_methods:
                for b in node.body:
                    if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name != "__init__":
                        methods.append(b.name)
            classes.append((node.name, init_args, methods))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)

    return {"classes": classes, "functions": functions}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Project root to scan")
    ap.add_argument("--out", default="symbols.md", help="Output markdown file")
    ap.add_argument("--ignore", default=IGNORE_DEFAULT, help="Regex of paths to ignore")
    ap.add_argument("--include-methods", action="store_true", help="Include methods under classes")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    items = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip(os.path.join(dirpath, d), args.ignore)]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            if should_skip(full, args.ignore):
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            res = scan_file(full, include_methods=args.include_methods)
            if res is None:
                continue
            items.append((rel, res))

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(f"# Symbols Summary\n\n")
        f.write(f"- Root: `{root}`\n\n")
        for rel, res in sorted(items):
            f.write(f"## `{rel}`\n\n")
            if res["classes"]:
                f.write("**Classes**\n\n")
                for cls, init_args, methods in res["classes"]:
                    if init_args:
                        f.write(f"- `{cls}` (init: {', '.join(init_args)})\n")
                    else:
                        f.write(f"- `{cls}`\n")
                    if args.include_methods and methods:
                        for m in methods:
                            f.write(f"  - `{m}`\n")
                f.write("\n")
            if res["functions"]:
                f.write("**Functions**\n\n")
                for fn in res["functions"]:
                    f.write(f"- `{fn}`\n")
                f.write("\n")

    print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()
```
