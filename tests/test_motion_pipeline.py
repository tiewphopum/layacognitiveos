# tests/test_motion_pipeline.py
import pytest

from layaos.synth.mock_camera import MockCamConfig, MockCamera
from layaos.vision.motion_fullframe import MotionFullFrame
from layaos.vision.motion_baseline import MotionBaselineConfig

@pytest.mark.asyncio
async def test_motion_detection_from_mock_camera():
    # เพิ่ม speed และใช้เฟรมเล็กให้ object เคลื่อนที่ชัดเจน
    cfg = MockCamConfig(width=96, height=72, rect_w=16, rect_h=16, speed_px=6, hz=16)
    cam = MockCamera(cfg)

    det = MotionFullFrame(MotionBaselineConfig())

    # ---- WARM-UP ----
    for _ in range(8):
        _, frame = cam.next_frame()
        det.detect(frame)  # ไม่ตรวจอะไร เก็บเบสไลน์อย่างเดียว

    any_motion_seen = False
    bboxes_seen = False
    ratio_seen = False

    # ---- ตรวจจริง ----
    for _ in range(60):
        _, frame = cam.next_frame()
        evt = det.detect(frame)

        # shape checks
        assert hasattr(evt, "any_motion")
        assert isinstance(evt.cell_ratios, list)
        assert isinstance(evt.bboxes, list)

        if evt.any_motion:
            any_motion_seen = True
        if evt.bboxes:
            bboxes_seen = True
        if sum(evt.cell_ratios) > 0:
            ratio_seen = True

        if any_motion_seen or bboxes_seen or ratio_seen:
            break

    assert (any_motion_seen or bboxes_seen or ratio_seen), \
        "Expected motion evidence (flag, bbox, or grid ratios) from moving rectangle"