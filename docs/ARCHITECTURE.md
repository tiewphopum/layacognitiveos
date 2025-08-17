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
