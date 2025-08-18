# Production Metrics Reference

ตารางนี้สรุป **metric สำหรับ production** ของ Core Motion Pipeline โดยจัดเป็นหมวด พร้อม
ชนิด, labels, หน่วย, ความหมาย, และแนวทางการตั้ง alert คร่าว ๆ

> หมายเหตุ: ชื่อ metric เป็นตัวอย่าง ควรรักษาแนวทางการตั้งชื่อแบบสม่ำเสมอ (prefix ตามโดเมน เช่น `bus_`, `pipeline_`, `notifier_`)

---

## 1) End-to-End & Pipeline

| Metric | Type | Labels (ตัวอย่าง) | Unit | ความหมาย | Alert / SLO ไกด์ไลน์ |
|---|---|---|---|---|---|
| `pipeline_e2e_ms` | Histogram | `cam_id`, `stage="s1_to_s6"` | ms | เวลารวมจากรับเฟรมจน event ถึง subscriber | p95 > 150ms 5m, p99 > 300ms 5m |
| `state_latency_ms` | Histogram | `state="S1..S6"`, `cam_id` | ms | เวลาประมวลผลราย state | เทียบ baseline, regression > 30% |
| `frame_fps` | Gauge | `cam_id` | fps | เฟรมที่เข้า pipeline สำเร็จจริง | < target (เช่น 10fps) ต่อเนื่อง 5m |
| `det_rate_hz` | Gauge | `cam_id` | Hz | อัตรา detect ต่อวินาที | ผิดปกติเมื่อ spike สูง/ต่ำผิดธรรมชาติ |
| `processing_success_total` | Counter | `state`, `cam_id` | cnt | จำนวนงานสำเร็จต่อ state | ดูอัตราส่วนต่อ error_total |

---

## 2) Bus / Queue / Backpressure

| Metric | Type | Labels | Unit | ความหมาย | Alert / SLO ไกด์ไลน์ |
|---|---|---|---|---|---|
| `bus_publish_total` | Counter | `topic` | cnt | จำนวนข้อความที่ publish ต่อ topic | ใช้เทียบกับ deliver_total |
| `bus_deliver_total` | Counter | `topic`, `sub` | cnt | ส่งถึง subscriber สำเร็จ | deliver/publish < 99.9% 5m |
| `bus_delivery_latency_ms` | Gauge | `topic` | ms | เวลาจาก publish → deliver | > 2× baseline 5m |
| `bus_queue_depth` | Gauge | `topic` | msgs | backlog ต่อ topic | ค้าง > N messages ต่อเนื่อง 5m |
| `queue_drop_total` | Counter | `topic`, `reason` | cnt | จำนวนที่ drop เพราะ backpressure | เพิ่มผิดปกติ = ปรับ policy/ขยาย capacity |

---

## 3) Camera Health

| Metric | Type | Labels | Unit | ความหมาย | Alert / SLO ไกด์ไลน์ |
|---|---|---|---|---|---|
| `camera_heartbeat_ok` | Gauge | `cam_id` | 0/1 | สถานะการส่งสัญญาณ | 0 ต่อเนื่อง > 2m |
| `camera_reconnect_total` | Counter | `cam_id` | cnt | จำนวน reconnect | spike ภายในช่วงสั้น |
| `camera_frame_gap_ms` | Histogram | `cam_id` | ms | ระยะห่างระหว่างเฟรม | p95 > 2× period 5m |

---

## 4) Notifier / Alerting

| Metric | Type | Labels | Unit | ความหมาย | Alert / SLO ไกด์ไลน์ |
|---|---|---|---|---|---|
| `notifier_sent_total` | Counter | `channel="line|slack"`, `cam_id` | cnt | จำนวนแจ้งเตือนที่ส่งสำเร็จ | base rate ต่ำผิดปกติ |
| `notifier_fail_total` | Counter | `channel`, `reason` | cnt | ส่งไม่สำเร็จ | error ratio > 1% 5m |
| `dedup_suppressed_total` | Counter | `channel`, `cam_id` | cnt | แจ้งเตือนที่ถูก suppress | spike ผิดปกติ = threshold ต่ำ |
| `thumbnail_encode_ms` | Histogram | `channel` | ms | เวลา encode snapshot/clip | p95 > 500ms ต่อเนื่อง 5m |

---

## 5) Persistence / Storage

| Metric | Type | Labels | Unit | ความหมาย | Alert / SLO ไกด์ไลน์ |
|---|---|---|---|---|---|
| `db_write_latency_ms` | Histogram | `table` | ms | เวลาเขียน DB | p95 > 100ms 5m |
| `db_error_total` | Counter | `op`, `table` | cnt | ข้อผิดพลาด DB | > 0 ต่อเนื่อง |
| `object_storage_put_ms` | Histogram | `bucket` | ms | เวลาอัปโหลดไฟล์/รูป | p95 > 1s 5m |
| `retention_deleted_total` | Counter | `kind="image|clip"` | cnt | จำนวนลบตาม retention | ตรวจสอบแนวโน้ม (data hygiene) |
| `storage_used_bytes` | Gauge | `bucket` | bytes | ใช้พื้นที่เก็บข้อมูล | ใกล้ quota (เช่น > 80%) |

---

## 6) Reliability / Errors

| Metric | Type | Labels | Unit | ความหมาย | Alert / SLO ไกด์ไลน์ |
|---|---|---|---|---|---|
| `error_total` | Counter | `component`, `state`, `reason` | cnt | error รวมตามบริบท | spike ภายใน 5m |
| `retry_total` | Counter | `component`, `op` | cnt | จำนวน retry | พุ่งสูง = ต้นทางล้มเหลว |
| `task_restart_total` | Counter | `component` | cnt | จำนวน restart ของ task/process | เพิ่มผิดปกติ |
| `watchdog_reset_total` | Counter | `component` | cnt | จำนวนรีเซ็ตจาก watchdog | > 0 = สืบสวนทันที |

---

## 7) Resource / Capacity

| Metric | Type | Labels | Unit | ความหมาย | Alert / SLO ไกด์ไลน์ |
|---|---|---|---|---|---|
| `cpu_percent` | Gauge | `proc`, `host` | % | การใช้ CPU | > 85% ต่อเนื่อง 10m |
| `gpu_util_percent` | Gauge | `gpu_id`, `host` | % | การใช้ GPU | > 90% ต่อเนื่อง 10m |
| `mem_used_bytes` | Gauge | `proc`, `host` | bytes | หน่วยความจำที่ใช้ | ใกล้ limit/container |
| `io_read_write_bytes` | Counter | `proc`, `host`, `dir` | bytes | ปริมาณ I/O | spike ร่วมกับ latency |
| `net_bytes_{rx,tx}` | Counter | `host`, `iface` | bytes | ปริมาณเครือข่าย | ใกล้ลิมิตลิงก์ |

---

## 8) Quality / Detection Semantics

| Metric | Type | Labels | Unit | ความหมาย | Alert / SLO ไกด์ไลน์ |
|---|---|---|---|---|---|
| `motion_ratio` | Histogram | `cam_id`, `zone` | ratio | สัดส่วนการเคลื่อนไหว | ฐานค่าตามฉาก; ใช้หาความผิดปกติ |
| `det_precision` | Gauge | `model`, `dataset` | 0..1 | ความแม่นยำ (offline/AB) | < เป้า = retrain/tune |
| `det_recall` | Gauge | `model`, `dataset` | 0..1 | การครอบคลุม (offline/AB) | < เป้า = ปรับ threshold |
| `false_alert_rate` | Gauge | `channel` | % | อัตรา false positive | > เป้า = ปรับ rule/threshold |

---

## 9) Security / Access (ถ้ามี Dashboard/API)

| Metric | Type | Labels | Unit | ความหมาย | Alert / SLO ไกด์ไลน์ |
|---|---|---|---|---|---|
| `auth_fail_total` | Counter | `client`, `reason` | cnt | ล้มเหลวในการยืนยันตัวตน | spike = สืบสวน |
| `api_request_total` | Counter | `route`, `code` | cnt | ปริมาณเรียก API | 5xx ratio > 1% 5m |
| `rate_limit_trigger_total` | Counter | `client` | cnt | จำนวนที่โดน rate-limit | spike = misuse/bug |

---

## Alerting Rules ตัวอย่าง (Prometheus-style แนวคิด)
- **Latency:** `pipeline_e2e_ms{stage="s1_to_s6"}:histogram_quantile(0.99) > 0.300 for 5m`
- **Loss:** `sum(bus_deliver_total) / sum(bus_publish_total) < 0.999 for 5m`
- **Queue:** `bus_queue_depth{topic="s3.det"} > 100 for 5m`
- **Error:** `increase(error_total[5m]) > 0`
- **Camera Down:** `camera_heartbeat_ok == 0 for 2m`

---

## Dashboard แนะนำ (Grafana panels)
- Latency heatmap: `pipeline_e2e_ms` (per cam_id)
- Per-state latency (S1..S6) – row แยก state
- Throughput: `frame_fps`, `det_rate_hz`
- Bus health: publish/deliver/queue depth per topic
- Notifier success/fail + dedup suppressed
- Resource: CPU/GPU/MEM + I/O + Net
