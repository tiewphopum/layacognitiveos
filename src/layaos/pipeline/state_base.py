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
        