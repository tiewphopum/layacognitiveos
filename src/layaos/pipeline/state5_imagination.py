# src/layaos/pipeline/state5_imagination.py
from __future__ import annotations
from layaos.pipeline.state_base import PipelineState


class State5_Imagination(PipelineState):
    def __init__(self, cfg, bus, batch_size: int = 1, **kwargs):
        # อย่าส่ง batch_size ไปให้ super().__init__ เพื่อกัน unexpected kw
        super().__init__(cfg, bus)
        try:
            self.batch_size = max(1, int(batch_size))
        except Exception:
            self.batch_size = 1

    async def on_tick(self):
        if self.cfg.topic_in:
            evt = await self.bus.try_consume(self.cfg.topic_in)
            if evt is None:
                return
            # TODO: hypothesis/forecast/what-if (สามารถใช้ self.batch_size ในอนาคต)
            if self.cfg.topic_out:
                await self.emit(self.cfg.topic_out, evt)