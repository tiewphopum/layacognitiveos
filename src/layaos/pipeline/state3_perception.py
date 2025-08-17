from __future__ import annotations
from layaos.pipeline.state_base import PipelineState

class State3_Perception(PipelineState):
    def __init__(self, *a, detector=None, **kw):
        super().__init__(*a, **kw)
        self.detector = detector
        # ตัวนับสำหรับ downsample การส่ง event ออก เพื่อกันคิว s4.ctx ล้น
        self._emit_counter = 0

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
                any_motion = False
                cell_ratios = []
                bboxes = []
                meta = {}
            det = _Det()

        # 1) ท่อสำหรับเทสภายใน
        # เติม motion_ratio ให้อยู่ระดับ top-level เพื่อให้ consumer อ่านง่าย
        motion_ratio = 0.0
        try:
            if isinstance(det, dict):
                if "motion_ratio" in det:
                    motion_ratio = float(det["motion_ratio"])
                else:
                    motion = det.get("motion") if isinstance(det.get("motion"), dict) else None
                    if motion and "ratio" in motion:
                        motion_ratio = float(motion["ratio"])
            else:
                if hasattr(det, "motion_ratio"):
                    motion_ratio = float(getattr(det, "motion_ratio"))
                elif hasattr(det, "cell_ratios"):
                    cr = getattr(det, "cell_ratios") or []
                    if isinstance(cr, (list, tuple)) and len(cr) > 0:
                        motion_ratio = float(sum(cr) / len(cr))
        except Exception:
            pass

        # downsample การ emit เพื่อลด backlog ที่ s4.ctx (ตั้งค่าได้ผ่าน cfg.every_n)
        every_n = int(getattr(self.cfg, "every_n", 3) or 3)
        self._emit_counter = (self._emit_counter + 1) % every_n
        should_emit = (self._emit_counter == 0)
        if self.cfg.topic_out and should_emit:
            await self.emit(
                self.cfg.topic_out,
                {"ts": ts, "det": det, "motion_ratio": motion_ratio},
            )

        # 2) ท่อ production-style: ยึด motion_ratio เป็นตัวชี้วัดเดียว
        score = float(motion_ratio)
        if should_emit:
            self.bus.publish("state3.trigger", {"score": score, "obj": "motion"})