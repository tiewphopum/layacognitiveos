import asyncio
import os
import pytest

from layaos.core import log
from layaos.core.metrics import snapshot
from layaos.pipeline.wire_minimal import build_pipeline


@pytest.mark.asyncio
async def test_latency_metrics_smoke():
    """
    Smoke test: รัน pipeline ชั่วครู่ แล้วเช็คว่า metrics มี histogram บางตัวถูกบันทึก
    ไม่ lock budget เข้มเพื่อกัน false-negative ข้ามเครื่อง
    """
    log.setup("WARNING")

    # ให้ exporter ยิงถี่หน่อยในเทสต์ (ถ้า config อ่านค่าจาก env)
    os.environ["METRICS_INTERVAL_TEST"] = "1.0"

    bus, cam, states = build_pipeline(cam_hz=12)

    # รันเฉพาะ S1..S3 ให้เกิด det เร็ว ๆ
    s1_to_s3 = states[:3]
    tasks = [asyncio.create_task(s.run()) for s in s1_to_s3]
    cam_task = asyncio.create_task(cam.run(n_frames=200))

    try:
        # ปล่อยให้เดินสักแป๊บ
        await asyncio.sleep(2.5)
    finally:
        cam_task.cancel()
        for t in tasks:
            t.cancel()
        await asyncio.gather(cam_task, *tasks, return_exceptions=True)

    snap = snapshot()
    # รูปแบบ snapshot อาจต่างกันเล็กน้อยในโปรเจ็กต์จริง
    # แต่คาดหวังว่าจะมี histogram ถูกเก็บอย่างน้อย 1 ตัว
    # เช่น 'clock_loop_ms' หรือ 'latency_ms{state=Sx}'
    hist_names = set(snap.get("hist_names", [])) if isinstance(snap, dict) else set()

    # fallback: บางอิมพลีเมนต์อาจเก็บเป็น dict เต็ม
    if not hist_names and isinstance(snap, dict):
        # ลองเดาชื่อจาก key ที่เจอบ่อย
        for k in snap.keys():
            if "hist" in k or "latency" in k or "clock_loop_ms" in k:
                hist_names.add(k)

    assert hist_names, "Expected at least one histogram metric recorded (e.g., clock_loop_ms/latency_ms)"