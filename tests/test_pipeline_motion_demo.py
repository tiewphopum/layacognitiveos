# tests/test_pipeline_motion_demo.py
"""
เดโม: pipeline 3 state
  - State1 (Sensor): mock camera → publish raw frame
  - State2 (PreProc): motion baseline → publish motion stats
  - State3 (Perception): rule-based alert (ถ้า ratio เกิน threshold) → log/emit

ไม่มี GUI/imshow เพื่อเลี่ยงปัญหา NSWindow/main-thread บน macOS
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict

from layaos.core import log
from layaos.core.bus import EventBus
from layaos.core.clock import BeatClock
from layaos.core.contracts import Event

from layaos.synth.mock_camera import MockCamera, MockCamConfig
from layaos.vision.motion_baseline import MotionBaseline, MotionBaselineConfig

# ---------- Config ----------
@dataclass
class DemoConfig:
    hz: float = 10.0
    run_seconds: float = 3.0
    cam_id: str = "cam0"
    motion_threshold: float = 0.02  # เงื่อนไข alert ใน state3

# ---------- Pipeline wiring ----------
def main():
    cfg = DemoConfig()
    log.setup("INFO")
    lg_s1 = log.get("state1")
    lg_s2 = log.get("state2")
    lg_s3 = log.get("state3")

    bus = EventBus(); bus.start()

    cam = MockCamera(MockCamConfig(width=320, height=240, rect_w=40, rect_h=40, speed_px=5))
    motion = MotionBaseline(MotionBaselineConfig(diff_threshold=18, min_ratio_trigger=0.01))

    # --- State2 subscriber: consume frame -> motion stats ---
    def s2(ev: Event):
        payload: Dict[str, Any] = ev.payload
        cam_id = payload["cam_id"]
        i = payload["i"]
        ts = payload["ts"]
        frame = payload["frame"]

        stats = motion.process(cam_id, frame)
        lg_s2.info("motion ratio=%.4f px=%d", stats["moving_ratio"], stats["moving_px"])
        bus.publish(Event("state2.motion", {
            "ts": ts, "i": i, "cam_id": cam_id,
            "moving_ratio": stats["moving_ratio"],
            "trigger": stats["trigger"],
        }))

    # --- State3 subscriber: rule-based alert ---
    def s3(ev: Event):
        p = ev.payload
        ratio = float(p["moving_ratio"])
        if ratio >= cfg.motion_threshold:
            lg_s3.info("ALERT cam=%s ratio=%.4f (>= %.3f)", p["cam_id"], ratio, cfg.motion_threshold)
            # ถ้าต้องการ ส่งต่อ Event("state3.alert", {...}) ได้

    bus.subscribe("state1.raw_frame", s2)
    bus.subscribe("state2.motion", s3)

    # --- State1 clock/ticker: produce frames ---
    clk = BeatClock(hz=cfg.hz, name="clock.pipe")
    def tick(ts, i):
        ts, frame = cam.next_frame()
        bus.publish(Event("state1.raw_frame", {
            "ts": ts, "i": i, "cam_id": cfg.cam_id, "frame": frame
        }))
        lg_s1.info("frame i=%s ts=%.3f", i, ts)

    clk.start(tick)

    # run for cfg.run_seconds
    import time
    time.sleep(cfg.run_seconds)

    clk.stop()
    bus.stop()
    print("DONE.")

def test_step1():
    main()
    print("Hello from print()")
    assert True