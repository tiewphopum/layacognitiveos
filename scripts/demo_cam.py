# scripts/demo_cam.py
import os
import time
import signal
import asyncio
import argparse
from statistics import median
from typing import List, Optional

from layaos.core import log
from layaos.core.metrics import (
    start_exporter, stop_exporter,
    observe_hist, inc,
)
from layaos.pipeline.wire_minimal import build_pipeline

# ใช้กล้องจริง (RTSP/Webcam)
from scripts.real_cam import RtspCamera, WebcamCamera


def _to_mapping(ev):
    if isinstance(ev, dict):
        return ev
    payload = getattr(ev, "payload", None)
    if isinstance(payload, dict):
        return payload
    d = getattr(ev, "__dict__", None)
    if isinstance(d, dict):
        return d
    return {}


def _extract_from_mapping(m, keys):
    for k in keys:
        if k in m:
            return m[k]
    return None


def _find_motion_ratio(ev) -> float:
    m = _to_mapping(ev)
    candidates = ["motion_ratio", "ratio", "motion.ratio",
                  "stats.motion_ratio", "metrics.motion_ratio"]
    v = _extract_from_mapping(m, candidates)
    if v is not None:
        try:
            return float(v)
        except Exception:
            pass
    motion = m.get("motion") if isinstance(m.get("motion"), dict) else None
    if motion and "ratio" in motion:
        try:
            return float(motion["ratio"])
        except Exception:
            pass
    det = m.get("det") if isinstance(m.get("det"), dict) else None
    if det:
        v = _extract_from_mapping(det, candidates)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
        motion = det.get("motion") if isinstance(det.get("motion"), dict) else None
        if motion and "ratio" in motion:
            try:
                return float(motion["ratio"])
            except Exception:
                pass
    for attr in ["motion_ratio", "ratio"]:
        if hasattr(ev, attr):
            try:
                return float(getattr(ev, attr))
            except Exception:
                pass
    return 0.0


def _find_src_ts(ev) -> Optional[float]:
    m = _to_mapping(ev)
    for k in ["ts", "t0", "start_ts"]:
        if k in m:
            return m[k]
    det = m.get("det") if isinstance(m.get("det"), dict) else None
    if det:
        for k in ["ts", "t0", "start_ts"]:
            if k in det:
                return det[k]
    for attr in ["ts", "t0", "start_ts"]:
        if hasattr(ev, attr):
            return getattr(ev, attr)
    return None


async def amain():
    # -------- args --------
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtsp", default=os.getenv("RTSP_URL"), help="RTSP url (override by env RTSP_URL)")
    ap.add_argument("--device", type=int, default=None, help="Webcam device index (mac usually 0)")
    ap.add_argument("--hz", type=float, default=12.0, help="Camera FPS for webcam (ignored for RTSP)")
    ap.add_argument("--duration", type=float, default=20.0, help="Run seconds (Ctrl+C to stop earlier)")
    ap.add_argument("--log-json", action="store_true", help="Log in JSON")
    args = ap.parse_args()

    # -------- logging / metrics --------
    os.environ.setdefault("LOG_LEVEL", "INFO")
    os.environ["LOG_JSON"] = "1" if args.log_json else os.environ.get("LOG_JSON", "0")
    os.environ.setdefault("METRICS_INTERVAL", "5.0")

    log.setup()
    lg = log.get("demo.real_cam")

    start_exporter(
        interval_sec=float(os.getenv("METRICS_INTERVAL", "5.0")),
        json_mode=(os.getenv("LOG_JSON", "0") == "1"),
        logger=log.get("metrics"),
    )

    # -------- build pipeline --------
    bus, _cam_stub, states = build_pipeline(cam_hz=args.hz)
    bus.start()

    # สตาร์ททุก state (สำคัญ!)
    state_tasks = [asyncio.create_task(s.run()) for s in states]

    # หา topic ขาเข้าของ S1 แบบไดนามิก
    s1 = states[0] if states else None
    s1_topic = (
        getattr(s1, "in_topic", None)
        or getattr(s1, "topic_in", None)
        or "s1.img"
    )

    # -------- สรุปผลแบบง่าย --------
    det_count = 0
    motion_ratios: List[float] = []
    end2end_ms: List[float] = []

    def on_det(ev):
        nonlocal det_count
        det_count += 1
        # debug ชั่วคราวให้เห็น payload 2 ครั้งแรก
        on_det.debug_shown = getattr(on_det, "debug_shown", 0)
        if on_det.debug_shown < 2:
            m = _to_mapping(ev)
            print("[DBG] det event keys:", sorted(list(m.keys()))[:20])
            if isinstance(m.get("det"), dict):
                print("[DBG] det payload keys:", sorted(list(m["det"].keys()))[:20])
            if isinstance(m.get("motion"), dict):
                print("[DBG] motion keys:", list(m["motion"].keys()))
            on_det.debug_shown += 1

        ratio = _find_motion_ratio(ev)
        motion_ratios.append(ratio)

        src_ts = _find_src_ts(ev)
        if src_ts is not None and src_ts > 1e12:  # ns -> s
            src_ts = src_ts / 1e9
        now_s = time.time()
        dt_ms = (now_s - float(src_ts)) * 1000.0 if src_ts is not None else 0.0
        end2end_ms.append(dt_ms)

        observe_hist("demo_e2e_ms", dt_ms, stage="s1_to_s6")
        inc("demo_det_total", 1, topic="s3.det")

    bus.subscribe("s3.det", on_det)

    # รีเลย์เฟรมจาก topic กล้อง → S1 (อย่าฮาร์ดโค้ดผิด)
    CAM_TOPIC = "cam/cam0.frame"

    def _relay_to_s1(ev):
        bus.publish(s1_topic, ev)

    bus.subscribe(CAM_TOPIC, _relay_to_s1)

    # debug: จำนวน subscribers
    try:
        cnt_cam = bus.count_subscribers(CAM_TOPIC)  # อาจไม่มี method นี้ในบาง impl
    except Exception:
        cnt_cam = None
    try:
        cnt_s1 = bus.count_subscribers(s1_topic)
    except Exception:
        cnt_s1 = None

    if cnt_cam is not None:
        lg.info("subscribers(%s)=%s", CAM_TOPIC, cnt_cam)
    if cnt_s1 is not None:
        lg.info("subscribers(%s)=%s", s1_topic, cnt_s1)

    # -------- เลือกกล้อง --------
    cam_task = None
    if args.rtsp:
        cam = RtspCamera(bus, url=args.rtsp, cam_id="cam0", hz=None)  # ปล่อยตาม stream
        cam_task = asyncio.create_task(cam.run())
    elif args.device is not None:
        cam = WebcamCamera(bus, device=args.device, cam_id="cam0", hz=args.hz, topic=CAM_TOPIC)
        cam_task = asyncio.create_task(cam.run())
    else:
        lg.error("no camera specified. Use --rtsp or --device")
        return

    # -------- graceful shutdown (Ctrl+C) --------
    stop_event = asyncio.Event()

    def _signal_handler():
        if not stop_event.is_set():
            stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # บางแพลตฟอร์ม (Windows) ไม่รองรับ add_signal_handler
            pass

    lg.info("real_cam demo start (%ss)", args.duration)
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=args.duration)
    except asyncio.TimeoutError:
        pass
    finally:
        # ปิดงาน
        if cam_task:
            cam_task.cancel()
        for t in state_tasks:
            t.cancel()
        await asyncio.gather(*(state_tasks + ([cam_task] if cam_task else [])), return_exceptions=True)

        # สรุป
        valid = [r for r in motion_ratios if r > 0.0]
        avg_ratio = (sum(valid) / len(valid)) if valid else 0.0
        p50 = median(sorted(end2end_ms)) if end2end_ms else 0.0
        processed = len(end2end_ms) or det_count

        lg.info("=== REAL CAM SUMMARY ===")
        lg.info("det_count=%d avg_ratio=%.4f p50_e2e_ms=%.2f", processed, avg_ratio, p50)

        bus.stop()
        stop_exporter()


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()