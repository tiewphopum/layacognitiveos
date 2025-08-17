# src/layaos/pipeline/wire_minimal.py
from __future__ import annotations
import asyncio
from layaos.core.bus import InProcEventBus
from layaos.pipeline.state_base import StateConfig
from layaos.pipeline.state1_sensor import State1_Sensor
from layaos.pipeline.state2_preproc import State2_PreProc
from layaos.pipeline.state3_perception import State3_Perception
from layaos.pipeline.state4_context import State4_Context
from layaos.pipeline.state5_imagination import State5_Imagination
from layaos.pipeline.state6_action import State6_Action
from layaos.vision.motion_fullframe import MotionFullFrame
from layaos.vision.motion_baseline import MotionBaselineConfig
from layaos.synth.mock_camera import MockCamConfig, MockCamera

# ★ เพิ่ม: storage สำหรับ ActionEvent
from layaos.adapters.storage import LocalEventStorage, StorageConfig


def build_pipeline(cam_hz: int = 12):
    bus = InProcEventBus(maxlen=256)

    # สร้าง storage หนึ่งตัวใช้ร่วมกันทั้งท่อ
    storage = LocalEventStorage(StorageConfig(out_dir="data", prefix="evt"))
    # หมายเหตุ: State6_Action จะ start() storage ให้เองถ้าถูกส่งเข้าไป

    # Mock camera publishes frames to cam/0.frame
    cam = MockCamera(
        MockCamConfig(hz=cam_hz, width=128, height=96, rect_w=20, rect_h=20, speed_px=4),
        bus=bus,
        topic_out="cam/0.frame",
    )

    # State wiring
    s1 = State1_Sensor(StateConfig("S1", "cam/0.frame", "s1.raw", hz=cam_hz), bus)
    s2 = State2_PreProc(StateConfig("S2", "s1.raw", "s2.pre", hz=cam_hz), bus)

    det = MotionFullFrame(MotionBaselineConfig())
    s3 = State3_Perception(StateConfig("S3", "s2.pre", "s3.det", hz=cam_hz), bus, detector=det)
    s4 = State4_Context(StateConfig("S4", "s3.det", "s4.ctx", hz=12), bus)
    s5 = State5_Imagination(StateConfig("S5", "s4.ctx", "s5.img", hz=6), bus, batch_size=16)
    s6 = State6_Action(StateConfig("S6", "s5.img", None, hz=6), bus)
    return bus, cam, [s1, s2, s3, s4, s5, s6]


async def run_pipeline(seconds: float = 2.0, cam_hz: int = 12):
    bus, cam, states = build_pipeline(cam_hz=cam_hz)
    tasks = [asyncio.create_task(s.run()) for s in states]
    cam_task = asyncio.create_task(cam.run())  # run indefinitely until cancelled
    try:
        await asyncio.sleep(seconds)
    finally:
        cam_task.cancel()
        for t in tasks:
            t.cancel()
        await asyncio.gather(cam_task, *tasks, return_exceptions=True)