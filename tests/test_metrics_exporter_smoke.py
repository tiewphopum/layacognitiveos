# tests/test_metrics_exporter_smoke.py
import time
import logging
import os
import pytest

from layaos.core.metrics import observe_hist

@pytest.mark.smoke
def test_metrics_exporter_emits_logs(caplog):
    """
    Smoke: ให้ registry มี metrics อย่างน้อย 1 ตัว แล้วรอดูว่า exporter พ่น log ออก
    ใช้ interval=1s (ตั้งใน conftest) -> รอ ~1.5-2.0s ก็น่าจะมี record
    """
    logger_name = "metrics"
    caplog.set_level(logging.INFO, logger=logger_name)

    # สร้าง metric สักตัว เพื่อให้ exporter มีอะไรให้พ่น
    observe_hist("test_latency_ms", 12.3, state="SMOKE")

    # รอมากกว่า interval นิดนึง
    time.sleep(float(os.getenv("METRICS_WAIT_SMOKE", "1.8")))

    # ตรวจว่ามี log จาก logger "metrics"
    records = [r for r in caplog.records if r.name == logger_name]
    assert len(records) > 0, "expected at least one metrics log line"

    # (ตัวเลือก) ตรวจเนื้อหาคร่าว ๆ ว่ามีชื่อ metric
    text = " ".join(r.getMessage() for r in records)
    assert "test_latency_ms" in text or '"name": "test_latency_ms"' in text