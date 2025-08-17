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