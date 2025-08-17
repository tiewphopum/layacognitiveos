# src/layaos/pipeline/state6_action.py
from __future__ import annotations

import time
from typing import Any, Iterable

from layaos.pipeline.state_base import PipelineState
from layaos.adapters.storage import LocalEventStorage, StorageConfig
from layaos.core.contracts import ActionEvent


class State6_Action(PipelineState):
    def __init__(
        self,
        *a,
        storage: LocalEventStorage | None = None,
        ratio_thr: float = 0.01,
        **kw,
    ):
        """
        :param storage: LocalEventStorage สำหรับบันทึกเหตุการณ์แอ็กชัน (optional)
        :param ratio_thr: เกณฑ์ motion_ratio ที่จะถือว่า 'ทริกเกอร์'
        """
        super().__init__(*a, **kw)
        self.storage = storage
        self.ratio_thr = float(ratio_thr)
        if self.storage:
            # start worker thread ของ AsyncStorage ภายใน LocalEventStorage
            self.storage.start()

    def _extract_ratio(self, evt: Any) -> float:
        """
        พยายามอ่านค่า motion ratio จากรูปแบบ payload ที่เป็นไปได้:
        - dict: {"ts": ..., "det": {...}} หรือ {"motion_ratio": ...}
        - object: มีแอททริบิวต์ det / motion_ratio / ratio / cells
        - fallback: เฉลี่ยจาก cells[].ratio
        """
        # 1) ดึง det ออกมาก่อน
        det = None
        if isinstance(evt, dict):
            det = evt.get("det", evt)
        else:
            det = getattr(evt, "det", evt)

        # 2) ลองอ่านคีย์ตรง ๆ
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

        # 3) เฉลี่ยจาก cells / cell_ratios
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

    async def on_tick(self):
        if not self.cfg.topic_in:
            return

        evt = await self.bus.try_consume(self.cfg.topic_in)
        if evt is None:
            return

        ratio = self._extract_ratio(evt)

        # ทริกเกอร์เมื่อเกิน threshold
        if ratio >= self.ratio_thr and self.storage:
            ae = ActionEvent(
                ts=time.time(),
                action="alert",
                target=None,
                params={
                    "reason": "motion",
                    "motion_ratio": ratio,
                    "state": self.cfg.name,
                },
            )
            # เขียนเป็น JSON event ลงโฟลเดอร์ data/act/
            self.storage.put_json("act", ae.to_dict())
        # ไม่มี topic_out ก็จบสายตามดีไซน์