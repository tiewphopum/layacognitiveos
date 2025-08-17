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
