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