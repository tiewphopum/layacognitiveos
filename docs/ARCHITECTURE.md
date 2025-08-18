# Architecture – Core Motion Pipeline

## 1. High-Level Design
The system is **event-driven** with a publish/subscribe model.

```
Camera → [S1] → [S2] → [S3: MotionDet] → Bus(topic="s3.det") → Subscriber(on_det) → Metrics
```

## 2. Components
- **Camera (cam)**  
  Frame generator at 12 Hz.

- **Pipeline States (S1–S3)**  
  - S1: raw frame → preprocessing  
  - S2: intermediate filtering  
  - S3: motion detection (produces `s3.det`)

- **Bus**  
  In-process event bus. Can be swapped to Redis/NATS/RabbitMQ if scaling out.

- **Subscriber (`on_det`)**  
  Subscribes to `s3.det`, extracts:
  - `motion_ratio`
  - `ts` (nanoseconds or seconds)
  - calculates latency (end-to-end ms)

- **Metrics**  
  - `demo_e2e_ms` histogram  
  - `demo_det_total` counter  
  - Logs summary at shutdown (det count, avg ratio, p50 latency)

## 3. Event Schema
Sample event (`s3.det`):

```json
{
  "det": {
    "ts": 1723871293000000000,
    "motion": {
      "ratio": 0.042
    }
  }
}
```

Supported keys for extraction:
- motion ratio → `motion_ratio`, `ratio`, `det.motion.ratio`
- timestamp → `ts`, `t0`, `start_ts`

## 4. Observability
- Latency measured via source ts vs. subscriber arrival time.
- Debug output shows event keys (first 3 detections).

## 5. Fault Tolerance
- Tasks are cancelled cleanly on shutdown.
- `asyncio.gather(..., return_exceptions=True)` prevents crashes from one task.
- Event payload extraction is robust (supports multiple schema variants).

## 6. Roadmap
- Add subscriber for `state3.trigger` to drain queue
- Extend pipeline (S4–S6) for advanced detection
- Integrate alert system (LINE/Slack/HTTP)
- Deploy bus backend for multi-process scaling
- Add dashboard visualization (web UI / CCTV overlay)

---


# 📊 Metrics Overview

ตารางสรุป Metrics ที่ใช้งานอยู่ใน Core Pipeline (`demo_motion.py`)

| Metric Name       | Type       | หน่วย     | ความหมาย                                                   | ใช้ตรวจสอบอะไรบ้าง |
|-------------------|------------|----------|------------------------------------------------------------|---------------------|
| `demo_e2e_ms`     | Histogram  | ms       | End-to-end latency: เวลาจาก event ถูกสร้างจนถึง consumer   | - ความเร็ว pipeline<br>- Jitter (กระจายของ latency)<br>- ใช้ดู p50/p90/p99 |
| `demo_det_total`  | Counter    | count    | จำนวน detection ที่ถูก process แล้ว (จาก `s3.det`)          | - Throughput ของระบบ<br>- ปริมาณ motion event |
| `det_count`       | Log Value  | count    | จำนวน detection ที่ process ได้จริง (สรุปตอน shutdown)      | - เช็ค consistency ว่าตรงกับ counter หรือไม่ |
| `avg_ratio`       | Log Value  | float    | ค่าเฉลี่ยของ motion ratio ที่มากกว่า 0.0                   | - ความเข้มข้น/ปริมาณ motion โดยรวม |
| `p50_e2e_ms`      | Log Value  | ms       | Median end-to-end latency (50th percentile)                 | - ความเสถียรโดยรวมของ pipeline |

---

## 📌 หมายเหตุ
- Metric ถูก export ผ่าน `start_exporter()` และสามารถต่อเข้ากับ Prometheus หรือระบบ monitoring อื่นได้ทันที
- Log summary ใช้สำหรับ **debug/demo** ไม่ได้เก็บต่อเนื่อง แต่ให้ภาพรวมตอนปิดระบบ

## 7. Metrics Reference

| Metric name        | Type       | Labels (examples)        | Unit | Meaning                                                                 | What to watch for |
|--------------------|------------|---------------------------|------|-------------------------------------------------------------------------|-------------------|
| `demo_e2e_ms`      | Histogram  | `stage="s1_to_s6"`        | ms   | End-to-end latency from source timestamp → subscriber arrival (`on_det`) | p50/p95/p99, spikes, long tail |
| `demo_det_total`   | Counter    | `topic="s3.det"`          | cnt  | Total detection events consumed by `on_det`                             | Sudden drops (missed events) or spikes (noise/threshold too low) |
| `bus_publish_total`| Counter    | `topic="s{N}.*"`          | cnt  | Messages published per topic                                            | Consistency across stages, unexpected gaps |
| `bus_deliver_total`| Counter    | `topic`, `sub`            | cnt  | Deliveries to subscribers                                               | Delivery ratio vs publish_total |
| `bus_queue_depth`  | Gauge      | `topic`                   | msgs | Queue backlog per topic                                                 | Non-zero trend = backpressure |
| `queue_depth{topic=...}` | Gauge | (embedded label)         | msgs | Internal queue depth (alias)                                           | Persistent growth indicates bottleneck |
| `bus_delivery_latency_ms` | Gauge | `topic`                 | ms   | In-bus delivery latency (publish → deliver)                             | Unexpected increases under load |
| `latency_ms{state=Si}` | Histogram | `state="S1".."S6"`     | ms   | Per-state processing latency                                            | Regression after code changes |
| `clock_loop_ms`    | Histogram  | `clock="clock"`           | ms   | Scheduler/clock tick period distribution                                | Jitter; ensure near target tick |

### Operational Tips
- Track **`demo_e2e_ms` p95/p99** over time; alert if p99 > (baseline × 2) for 5 min.
- Watch **`bus_queue_depth`** for `s3.det` and downstream topics; non-zero plateau = consumer slower than producer.
- Compare **`bus_publish_total` vs `bus_deliver_total`** to ensure no silent drops.
- Use **`latency_ms{state=Si}`** to pinpoint which stage regresses when e2e worsens.

### Suggested Next Metrics (for production hardening)
- `frame_fps` (Gauge): effective frames/sec entering S1 (per camera).
- `det_rate_hz` (Gauge): detections/sec after S3 (per camera).
- `error_total{state=Si}` (Counter): exceptions per state.
- `dedup_suppressed_total` (Counter): number of alerts suppressed by rate limiter.
- `thumbnail_encode_ms` (Histogram): cost to generate snapshot/clip for notifications.
- Resource: `cpu_percent`, `gpu_util`, `mem_bytes` (Gauges) tagged by process/pod.
