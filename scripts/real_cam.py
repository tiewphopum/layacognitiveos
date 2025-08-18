# scripts/real_cam.py
import asyncio
import time
from typing import Optional

import cv2

from layaos.core import log
from layaos.core.bus import EventBus


__all__ = ["RtspCamera", "WebcamCamera"]

lg = log.get("cam")


class _BaseCamera:
    """
    กล้องพื้นฐาน: เปิด source → อ่าน frame → publish ลง EventBus
    """
    def __init__(
        self,
        bus: EventBus,
        cam_id: str = "cam0",
        hz: Optional[float] = None,
        topic: Optional[str] = None,
    ):
        self.bus = bus
        self.cam_id = cam_id
        self.hz = hz
        self.topic = topic or f"cam/{cam_id}.frame"
        self._stop = asyncio.Event()
        self._frame_id = 0

    async def stop(self):
        self._stop.set()

    # ---- utilities ---------------------------------------------------------
    async def _sleep_to_hz(self, t0: float):
        if not self.hz or self.hz <= 0:
            return
        period = 1.0 / float(self.hz)
        dt = time.perf_counter() - t0
        remain = period - dt
        if remain > 0:
            await asyncio.sleep(remain)

    async def _publish(self, img):
        # ใส่ข้อมูลที่ปลาย pipeline ใช้ได้ทันที
        payload = {
            "cam": self.cam_id,
            "frame_id": self._frame_id,
            # ใช้ epoch seconds (float) เพื่อคำนวณ e2e latency ได้
            "ts": time.time(),
            "img": img,
            "shape": tuple(img.shape) if hasattr(img, "shape") else None,
        }
        self.bus.publish(self.topic, payload)


class WebcamCamera(_BaseCamera):
    """
    กล้องเว็บแคมในเครื่อง: device index เช่น 0, 1
    """
    def __init__(
        self,
        bus: EventBus,
        device: int = 0,
        cam_id: str = "cam0",
        hz: Optional[float] = None,
        topic: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ):
        super().__init__(bus=bus, cam_id=cam_id, hz=hz, topic=topic)
        self.device = device
        self.width = width
        self.height = height
        self._cap = None

    def _open(self):
        cap = cv2.VideoCapture(self.device)
        if self.width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not cap.isOpened():
            raise RuntimeError(f"cannot open webcam device={self.device}")
        return cap

    async def run(self):
        lg_cam = log.get("cam.webcam")
        lg_cam.info(
            "webcam start cam_id=%s device=%s hz=%s topic=%s",
            self.cam_id, self.device, self.hz, self.topic,
        )
        loop = asyncio.get_running_loop()
        self._cap = self._open()
        try:
            while not self._stop.is_set():
                t0 = time.perf_counter()
                # อ่านเฟรมใน thread เพื่อไม่ block event loop
                ok, frame = await asyncio.to_thread(self._cap.read)
                if not ok or frame is None:
                    # รอแล้วลองใหม่
                    await asyncio.sleep(0.05)
                    continue

                await self._publish(frame)
                self._frame_id += 1
                await self._sleep_to_hz(t0)
        finally:
            frames = self._frame_id
            if self._cap is not None:
                await asyncio.to_thread(self._cap.release)
            lg_cam.info("webcam stop cam_id=%s frames=%d", self.cam_id, frames)


class RtspCamera(_BaseCamera):
    """
    กล้อง RTSP: ใส่ URL rtsp://user:pass@host:port/stream
    """
    def __init__(
        self,
        bus: EventBus,
        url: str,
        cam_id: str = "cam0",
        hz: Optional[float] = None,
        topic: Optional[str] = None,
        tcp_transport: bool = True,
        open_timeout_sec: float = 10.0,
        read_retry_delay: float = 0.2,
    ):
        super().__init__(bus=bus, cam_id=cam_id, hz=hz, topic=topic)
        self.url = url
        self.tcp_transport = tcp_transport
        self.open_timeout_sec = open_timeout_sec
        self.read_retry_delay = read_retry_delay
        self._cap = None

    def _open(self):
        # บาง backend จะรับพารามิเตอร์ผ่าน URL ได้ เช่น ?tcp
        rtsp_url = self.url
        if self.tcp_transport and "rtsp_transport=tcp" not in rtsp_url:
            sep = "&" if "?" in rtsp_url else "?"
            rtsp_url = f"{rtsp_url}{sep}rtsp_transport=tcp"
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        t0 = time.time()
        while not cap.isOpened():
            if time.time() - t0 > self.open_timeout_sec:
                raise RuntimeError(f"cannot open rtsp url={self.url}")
            time.sleep(0.2)
            cap.open(rtsp_url, cv2.CAP_FFMPEG)
        return cap

    async def run(self):
        lg_cam = log.get("cam.rtsp")
        lg_cam.info(
            "rtsp start cam_id=%s url=%s hz=%s topic=%s",
            self.cam_id, self.url, self.hz, self.topic,
        )
        self._cap = await asyncio.to_thread(self._open)
        try:
            while not self._stop.is_set():
                t0 = time.perf_counter()
                ok, frame = await asyncio.to_thread(self._cap.read)
                if not ok or frame is None:
                    await asyncio.sleep(self.read_retry_delay)
                    continue
                await self._publish(frame)
                self._frame_id += 1
                await self._sleep_to_hz(t0)
        finally:
            frames = self._frame_id
            if self._cap is not None:
                await asyncio.to_thread(self._cap.release)
            lg_cam.info("rtsp stop cam_id=%s frames=%d", self.cam_id, frames)