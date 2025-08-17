# tests/test_perf_basics.py
"""
Basic throughput / latency test (in‑proc bus + clock)
- ยิง event ด้วย BeatClock ที่กำหนด hz และเวลา run
- วัด latency จากจุด publish -> จุด consumer รับ (perf_counter_ns)
- สรุป throughput (events/sec) และ latency stats (avg/p50/p90/p95/p99/max)
- เขียน metrics ลง registry ของระบบด้วย (ถ้า layaos.core.metrics มีอยู่)
"""

from __future__ import annotations
import argparse, time
from typing import List, Dict, Any

from layaos.core import log
from layaos.core.bus import InProcEventBus
from layaos.core.clock import BeatClock
from layaos.core.contracts import Event

# ---- metrics (optional hook) ----
try:
    from layaos.core import metrics as met
except Exception:
    met = None


def pct(v: List[float], p: float) -> float:
    """percentile (p ∈ [0,100]) บน list ที่ ‘ถูก sort แล้ว’"""
    if not v:
        return 0.0
    if p <= 0:
        return v[0]
    if p >= 100:
        return v[-1]
    k = (len(v) - 1) * (p / 100.0)
    i = int(k)
    f = k - i
    if i + 1 < len(v):
        return v[i] * (1.0 - f) + v[i + 1] * f
    return v[i]


def run(hz: float, seconds: float, topic: str = "state1.raw") -> None:
    log.setup("INFO")
    lg = log.get("perf")

    # เตรียม bus/clock
    bus = InProcEventBus()
    bus.start()

    clk = BeatClock(hz=hz, name=f"clock.perf.{hz:g}")

    # เก็บ latency (ms)
    lat_ms: List[float] = []
    sent = 0
    recv = 0
    t_start = time.perf_counter()

    # -- consumer: วัด latency จาก ts_ns ที่แนบมา --
    def consumer(ev: Event):
        nonlocal recv
        now_ns = time.perf_counter_ns()
        ts_ns = ev.payload["ts_pub_ns"]
        dt_ms = (now_ns - ts_ns) / 1e6
        lat_ms.append(dt_ms)
        recv += 1
        # optional metrics
        if met:
            met.observe_hist("app_event_latency_ms", dt_ms, stage="bus_consumer")

    bus.subscribe(topic, consumer)

    # -- producer: ยิง event ทุก tick --
    def on_tick(ts: float, i: int):
        nonlocal sent
        ts_pub_ns = time.perf_counter_ns()
        bus.publish(Event(topic, {"i": i, "ts_wall": ts, "ts_pub_ns": ts_pub_ns}))
        sent += 1
        if met:
            met.inc("app_events_published_total", 1, topic=topic)

    lg.info("start perf test hz=%.3f run=%.2fs topic=%s", hz, seconds, topic)
    clk.start(on_tick)

    # ปล่อยให้วิ่งตามเวลาที่กำหนด
    time.sleep(seconds)

    # หยุดทุกอย่าง
    clk.stop()
    bus.stop()

    # สรุปผล
    t_end = time.perf_counter()
    dur = max(1e-9, t_end - t_start)
    eps = recv / dur  # events/sec (ตามที่ consumer รับจริง)

    lat_ms.sort()
    avg = (sum(lat_ms) / len(lat_ms)) if lat_ms else 0.0
    p50 = pct(lat_ms, 50.0)
    p90 = pct(lat_ms, 90.0)
    p95 = pct(lat_ms, 95.0)
    p99 = pct(lat_ms, 99.0)
    pmax = lat_ms[-1] if lat_ms else 0.0

    lg.info("sent=%d recv=%d dur=%.3fs eps=%.2f/s", sent, recv, dur, eps)
    lg.info("latency_ms avg=%.3f p50=%.3f p90=%.3f p95=%.3f p99=%.3f max=%.3f",
            avg, p50, p90, p95, p99, pmax)

    # dump metrics (ถ้ามี registry)
    if met:
        met.gauge_set("app_throughput_eps", eps, topic=topic)
        met.observe_hist("app_run_seconds", dur, test="perf")
        snap = met.snapshot()
        log.get("metrics").info("snapshot=%s", snap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hz", type=float, default=500.0, help="clock rate (Hz)")
    ap.add_argument("--seconds", type=float, default=3.0, help="run seconds")
    ap.add_argument("--topic", type=str, default="state1.raw", help="event topic")
    args, _unknown = ap.parse_known_args()
    run(args.hz, args.seconds, args.topic)


def test_step1():
    main()
    print("Hello from print()")
    assert True
    
# default: 500 Hz, 3 วินาที
# python -m tests.test_perf_basics

# ปรับความถี่และเวลาทดสอบ
# python -m tests.test_perf_basics --hz 1000 --seconds 5