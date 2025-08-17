# src/layaos/synth/mock_camera.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import time
import asyncio
from typing import Optional, Tuple, Any
from layaos.core.bus import InProcEventBus

BGRFrame = np.ndarray

@dataclass
class MockCamConfig:
    width: int = 320
    height: int = 240
    rect_w: int = 40
    rect_h: int = 40
    speed_px: int = 3           # ความเร็วการเคลื่อนที่ (px ต่อเฟรม)
    bg_color: tuple = (0, 0, 0) # BGR
    fg_color: tuple = (255, 255, 255)
    hz: int = 8                 # frame rate (Hz)

class MockCamera:
    """
    กล้องจำลอง: สร้างภาพพื้นดำ มีสี่เหลี่ยมขาววิ่งซ้าย-ขวาแบบ ping-pong
    รองรับการรัน async และ publish frame event ไปยัง bus
    """
    def __init__(self, config: MockCamConfig = MockCamConfig(),
                 bus: Optional[InProcEventBus] = None,
                 topic_out: Optional[str] = None):
        self.cfg = config
        self.bus = bus
        self.topic_out = topic_out
        self.x = 0
        self.y = (self.cfg.height - self.cfg.rect_h) // 2
        self.vx = self.cfg.speed_px
        self._last_ts: Optional[float] = None

    def next_frame(self) -> Tuple[float, BGRFrame]:
        w, h = self.cfg.width, self.cfg.height
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        if self.cfg.bg_color != (0, 0, 0):
            frame[:] = self.cfg.bg_color

        # วาดสี่เหลี่ยม
        x0 = int(max(0, min(w - self.cfg.rect_w, self.x)))
        y0 = int(max(0, min(h - self.cfg.rect_h, self.y)))
        frame[y0:y0+self.cfg.rect_h, x0:x0+self.cfg.rect_w] = self.cfg.fg_color

        # อัปเดตตำแหน่งแบบ ping-pong
        self.x += self.vx
        if self.x <= 0 or self.x + self.cfg.rect_w >= w:
            self.vx = -self.vx
            self.x += self.vx

        ts = time.time()
        self._last_ts = ts
        return ts, frame

    async def run(self, n_frames: Optional[int] = None):
        """รันกล้องจำลองตาม frame rate; publish ออก bus ถ้ามี"""
        interval = 1.0 / float(self.cfg.hz)
        i = 0
        while n_frames is None or i < n_frames:
            ts, frame = self.next_frame()
            if self.bus and self.topic_out:
                self.bus.publish(self.topic_out, {"ts": ts, "frame": frame})
            await asyncio.sleep(interval)
            i += 1