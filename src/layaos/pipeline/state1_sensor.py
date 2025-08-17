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