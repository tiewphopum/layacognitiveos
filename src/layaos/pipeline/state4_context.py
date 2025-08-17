# src/layaos/pipeline/state4_context.py
from __future__ import annotations

from typing import Any, Iterable, Optional

from layaos.pipeline.state_base import PipelineState


class State4_Context(PipelineState):
    """
    - ดึงเหตุการณ์จาก S3 เป็นชุด (burst-drain) ต่อหนึ่ง tick เพื่อไม่ให้คิว s3.det ค้าง
    - คำนวณ EMA (exponential moving average) ของ motion_ratio แล้วแนบเป็น ctx ก่อนส่งออก
    """

    def __init__(
        self,
        *a,
        batch_size: int = 32,
        alpha: float = 0.2,
        **kw,
    ):
        """
        :param batch_size: จำนวนเหตุการณ์สูงสุดที่จะดึงจากคิวต่อหนึ่ง tick
        :param alpha: smoothing factor ของ EMA (0 < alpha <= 1), ค่ายิ่งสูงยิ่งไวต่อการเปลี่ยนแปลง
        """
        super().__init__(*a, **kw)
        self.batch_size = int(batch_size)
        self.alpha = float(alpha)
        self._ema: Optional[float] = None  # เก็บค่า EMA ล่าสุด

    # ---------- helpers ----------
    def _extract_ratio(self, evt: Any) -> float:
        """
        อ่านค่า motion_ratio จาก payload รูปแบบที่เป็นไปได้:
        - dict: {"ts": ..., "det": {...}} หรือ {"motion_ratio": ...}
        - object: มีแอททริบิวต์ det / motion_ratio / ratio / cells
        - fallback: เฉลี่ยจาก cells[].ratio
        """
        det = None
        if isinstance(evt, dict):
            det = evt.get("det", evt)
        else:
            det = getattr(evt, "det", evt)

        # ลองอ่านคีย์ตรง ๆ ก่อน
        for k in ("motion_ratio", "ratio"):
            v = None
            if isinstance(det, dict):
                v = det.get(k)
            else:
                v = getattr(det, k, None)
            if v is not None:
                try:
                    return float(v)
                except Exception:
                    pass

        # fallback: เฉลี่ยจาก cells / cell_ratios
        cells = []
        if isinstance(det, dict):
            cells = det.get("cells") or det.get("cell_ratios") or []
        else:
            cells = getattr(det, "cells", []) or getattr(det, "cell_ratios", [])

        vals: list[float] = []
        for c in cells:
            try:
                if isinstance(c, dict):
                    vals.append(float(c.get("ratio", 0.0)))
                else:
                    vals.append(float(getattr(c, "ratio", 0.0)))
            except Exception:
                continue
        if vals:
            return sum(vals) / len(vals)

        return 0.0

    def _update_ema(self, x: float) -> float:
        if self._ema is None:
            self._ema = x
        else:
            self._ema = self.alpha * x + (1.0 - self.alpha) * self._ema
        return self._ema

    # ---------- main ----------
    async def on_tick(self):
        if not self.cfg.topic_in:
            return

        processed = 0
        for _ in range(self.batch_size):
            evt = await self.bus.try_consume(self.cfg.topic_in)
            if evt is None:
                break

            ratio = self._extract_ratio(evt)
            ratio_ema = self._update_ema(ratio)

            # สร้างคอนเท็กซ์แล้วแนบกลับไปใน event
            ctx_payload = {
                "ts": getattr(evt, "ts", None) if not isinstance(evt, dict) else evt.get("ts"),
                "det": evt.get("det", evt) if isinstance(evt, dict) else getattr(evt, "det", evt),
                "ctx": {
                    "ratio_ema": ratio_ema,
                    "ratio_now": ratio,
                    "alpha": self.alpha,
                },
            }

            if self.cfg.topic_out:
                await self.emit(self.cfg.topic_out, ctx_payload)

            processed += 1

        # (ถ้าต้องการ) สามารถบันทึก metrics จำนวนที่ประมวลผลต่อ tick ได้ที่นี่ เช่น:
        # inc_counter("s4_batch_processed", processed)