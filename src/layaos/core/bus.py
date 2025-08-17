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