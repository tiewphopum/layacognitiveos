import asyncio
import os
import time
from statistics import median
from typing import List

from layaos.core import log
from layaos.core.metrics import start_exporter, stop_exporter, observe_hist, inc
from layaos.pipeline.wire_minimal import build_pipeline


async def main():
    # บูต logger  metrics
    os.environ.setdefault("LOG_LEVEL", "INFO")
    os.environ.setdefault("LOG_JSON", "0")
    os.environ.setdefault("METRICS_INTERVAL", "5.0")

    log.setup()
    lg = log.get("demo.motion")

    start_exporter(
        interval_sec=float(os.getenv("METRICS_INTERVAL", "5.0")),
        json_mode=(os.getenv("LOG_JSON", "0") == "1"),
        logger=log.get("metrics"),
    )

    # สร้าง pipeline S1–S3
    bus, cam, states = build_pipeline(cam_hz=12)
    bus.start()
    
    s1_to_s6 = states

    # เก็บสถิติแบบง่าย ๆ
    det_count = 0
    motion_ratios: List[float] = []
    end2end_ms: List[float] = []

    # subscribe สรุป end-to-end จาก s3.det
    t_start = time.perf_counter()

    # วางไว้ก่อน on_det
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

    def _find_motion_ratio(ev):
        m = _to_mapping(ev)
        # try top-level first
        candidates = ["motion_ratio", "ratio", "motion.ratio",
                      "stats.motion_ratio", "metrics.motion_ratio"]
        v = _extract_from_mapping(m, candidates)
        if v is not None:
            try: return float(v)
            except Exception: pass
        # try nested motion dict
        motion = m.get("motion") if isinstance(m.get("motion"), dict) else None
        if motion and "ratio" in motion:
            try: return float(motion["ratio"])
            except Exception: pass
        # NEW: try inside 'det' payload
        det = m.get("det") if isinstance(m.get("det"), dict) else None
        if det:
            v = _extract_from_mapping(det, candidates)
            if v is not None:
                try: return float(v)
                except Exception: pass
            motion = det.get("motion") if isinstance(det.get("motion"), dict) else None
            if motion and "ratio" in motion:
                try: return float(motion["ratio"])
                except Exception: pass
        # attrs fallback
        for attr in ["motion_ratio", "ratio"]:
            if hasattr(ev, attr):
                try: return float(getattr(ev, attr))
                except Exception: pass
        return 0.0

    def _find_src_ts(ev):
        m = _to_mapping(ev)
        # top-level first
        for k in ["ts", "t0", "start_ts"]:
            if k in m:
                return m[k]
        # NEW: inside det
        det = m.get("det") if isinstance(m.get("det"), dict) else None
        if det:
            for k in ["ts", "t0", "start_ts"]:
                if k in det:
                    return det[k]
        # attrs fallback
        for attr in ["ts", "t0", "start_ts"]:
            if hasattr(ev, attr):
                return getattr(ev, attr)
        return None
    
    def on_det(ev):
        nonlocal det_count
        det_count += 1

        on_det.debug_shown = getattr(on_det, "debug_shown", 0)
        if on_det.debug_shown < 3:
            m = _to_mapping(ev)
            print("[DBG] det event keys:", sorted(list(m.keys()))[:20])
            if isinstance(m.get("det"), dict):
                print("[DBG] det payload keys:", sorted(list(m["det"].keys()))[:20])
            if isinstance(m.get("motion"), dict):
                print("[DBG] det motion keys:", list(m["motion"].keys()))
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
    

    # สปิน
    tasks = [asyncio.create_task(s.run()) for s in s1_to_s6]
    cam_task = asyncio.create_task(cam.run(n_frames=999999))  # ปล่อยไหล

    # รัน 20s
    try:
        lg.info("demo start: running ~20s")
        await asyncio.sleep(20.0)
    finally:
        cam_task.cancel()
        for t in tasks:
            t.cancel()
        await asyncio.gather(cam_task, *tasks, return_exceptions=True)

        # สรุป
        valid = [r for r in motion_ratios if r > 0.0]
        avg_ratio = (sum(valid) / len(valid)) if valid else 0.0
        p50 = median(sorted(end2end_ms)) if end2end_ms else 0.0
        # Use the actual processed events count
        processed = len(end2end_ms) or det_count
        lg.info("=== DEMO SUMMARY ===")
        lg.info("det_count=%d avg_ratio=%.4f p50_e2e_ms=%.2f", processed, avg_ratio, p50)
        bus.stop()
        stop_exporter()


if __name__ == "__main__":
    asyncio.run(main())