# tests/test_pipeline_s13_detection.py
import asyncio
import pytest

from layaos.pipeline.wire_minimal import build_pipeline

@pytest.mark.asyncio
async def test_pipeline_emits_s3_detection():
    bus, cam, states = build_pipeline(cam_hz=12)

    # ✨ รันเฉพาะ S1..S3 เท่านั้น เพื่อกัน S4 consume s3.det หาย
    s1_to_s3 = states[:3]

    tasks = [asyncio.create_task(s.run()) for s in s1_to_s3]
    cam_task = asyncio.create_task(cam.run(n_frames=200))

    got_det = False
    try:
        # รอฟัง s3.det (และกันเหนียวลอง state3.trigger ด้วย)
        for _ in range(800):  # ~8s
            evt = await bus.try_consume("s3.det")
            if evt is None:
                evt = await bus.try_consume("state3.trigger")
            if evt is not None:
                got_det = True
                break
            await asyncio.sleep(0.01)
    finally:
        cam_task.cancel()
        for t in tasks:
            t.cancel()
        await asyncio.gather(cam_task, *tasks, return_exceptions=True)

    assert got_det, "Expected at least one detection event on topic s3.det/state3.trigger"