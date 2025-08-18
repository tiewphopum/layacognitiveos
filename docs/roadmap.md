# ROADMAP – จาก Core → Production

เอกสารนี้สรุปเส้นทางพัฒนาระบบจาก **Core Motion Pipeline** ที่ใช้งานได้แล้ว
ไปสู่ **Production-Ready Platform** แบบเป็นขั้นตอน พร้อมเกณฑ์ผ่าน (Acceptance Criteria),
ตัวชี้วัด (SLO/Metric) และความเสี่ยงที่ต้องเฝ้าระวัง

---

## Phase 0 — Baseline (Done)
**สถานะ:** ✅ เสร็จแล้ว  
**สาระสำคัญ:** Core pipeline + bus + subscriber + metrics + graceful shutdown

**หลักฐานผ่าน**
- รัน `python scripts/demo_motion.py` ได้ใน ~20s
- ได้ `s3.det` ต่อเนื่อง, ไม่มี exception/crash
- Metrics แสดง `demo_e2e_ms`, `demo_det_total` และ per-state latency
- Summary log: `det_count`, `avg_ratio`, `p50_e2e_ms`

---

## Phase 1 — Productize Core (สัปดาห์ที่ 1–2)

### 1.1 Event Schema & Contracts
- [ ] กำหนด schema เดียว (JSON) สำหรับ `s3.det`
- [ ] ใส่ `cam_id`, `seq`, `ts_ns`, `motion.ratio`, `frame_ref`
- [ ] เวอร์ชันสคีมา (e.g. `schema_version: 1`)
**Acceptance:** เอกสารสคีมาพร้อมตัวอย่าง, unit tests สำหรับ parser
**Risk:** producers หลายตัวส่งค่าต่างรูปแบบ → ทำ adapter แยก

### 1.2 State3 Trigger Subscriber
- [ ] เพิ่ม subscriber สำหรับ `state3.trigger` (drain queue)
- [ ] ใส่ dedup/rate-limit เบื้องต้น (เช่น suppress 30s)
**Acceptance:** queue depth ของ `state3.trigger` ไม่ค้างยาว
**Metric:** `bus_queue_depth{topic="state3.trigger"} → ~0` ภายใต้โหลดปกติ

### 1.3 LINE/Slack Notifier (MVP)
- [ ] สร้าง subscriber `notifier.line`/`notifier.slack`
- [ ] เงื่อนไข trigger: `motion.ratio >= threshold`
- [ ] แนบ snapshot/thumbnail จาก S5 (ถ้ามี)
- [ ] ตั้ง rate-limit, dedup by cam_id + window
**Acceptance:** แจ้งเตือนถูกต้อง, ไม่สแปม
**Metric:** `dedup_suppressed_total`, `thumbnail_encode_ms`

### 1.4 Persistence เบื้องต้น
- [ ] บันทึก event ลง SQLite/Postgres: `events(cam_id, ts, ratio, path)`
- [ ] Job เก็บ snapshot เฉพาะช่วง event
**Acceptance:** ค้นหา event ย้อนหลังตามเวลา/กล้องได้
**Risk:** I/O หนัก → เก็บเฉพาะ frame สำคัญและทำ retention policy

---

## Phase 2 — Scale & Reliability (สัปดาห์ที่ 3–6)

### 2.1 Split Process / Transport
- [ ] แยก S1/S2/S3 ออกเป็นโปรเซส (หรือ container) คนละส่วน
- [ ] เปลี่ยน bus backend เป็น NATS/Redis/RabbitMQ (เลือก 1)
- [ ] ใช้ reference แทนการส่งภาพทั้งก้อน (zero-copy/shared memory ภายในเครื่อง)
**Acceptance:** latency เพิ่มไม่เกิน +30% จาก baseline, throughput เท่าเดิมหรือดีกว่า
**Metric:** `demo_e2e_ms p95`, `bus_delivery_latency_ms`, `bus_publish_total ~= bus_deliver_total`

### 2.2 Backpressure & Policy
- [ ] Token bucket / bounded queue ต่อ topic สำคัญ
- [ ] Drop/skip policy (เช่น process ทุก N เฟรมตอน overload)
**Acceptance:** ไม่มี OOM/แฮงค์เมื่อโหลดพุ่ง
**Metric:** queue depth ไม่พุ่งเกิน threshold ต่อเนื่อง >5 นาที

### 2.3 Health/Discovery
- [ ] Camera registry + health-check per cam
- [ ] Auto-restart state, exponential backoff, watchdog
**Acceptance:** กล้องหาย/กลับมาแล้วระบบ recover เอง
**Metric:** MTTR < 2 นาที

---

## Phase 3 — Smart AI & UX (สัปดาห์ที่ 7–10)

### 3.1 Secondary AI (Trigger-based)
- [ ] Object/Person detection เรียกเฉพาะเมื่อมี motion
- [ ] Zone/line crossing, loitering rule engine
**Acceptance:** ลด false positive, เพิ่มความหมายของ event
**Metric:** precision/recall บนชุดทดสอบภายใน

### 3.2 Web Dashboard
- [ ] Timeline/heatmap ของ event, per-camera view
- [ ] Live preview + motion overlay (หากพร้อม)
**Acceptance:** ใช้งาน UI สำคัญได้ใน 1–2 คลิก

### 3.3 Policy & Privacy
- [ ] Masking zones, blur faces (optional)
- [ ] Retention policy: TTL ภาพ/คลิป
**Acceptance:** ผ่านแนวปฏิบัติ privacy ภายในทีม/องค์กร

---

## Phase 4 — Production Hardening (สัปดาห์ที่ 11–14)

### 4.1 Observability แบบครบวงจร
- [ ] Prometheus + Grafana dashboard
- [ ] Alert rules: p99 e2e, queue depth, error rate
- [ ] Distributed tracing (OTel) สำหรับ path สำคัญ
**Acceptance:** on-call รู้สาเหตุเบื้องต้นภายใน 5 นาทีเมื่อมี incident

### 4.2 HA/Recovery
- [ ] Multi-instance + leader election (ถ้าจำเป็น)
- [ ] Durable queue / WAL สำหรับ event สำคัญ
**Acceptance:** ไม่สูญเสีย event ภายใต้การรีสตาร์ตตามปกติ

### 4.3 Security & Secrets
- [ ] จัดเก็บ secrets อย่างปลอดภัย (env/secret manager)
- [ ] RBAC สำหรับ dashboard/API
**Acceptance:** ผ่านการทดสอบความปลอดภัยภายใน

---

## SLO เป้าหมาย (เริ่มจับตั้งแต่ Phase 1)
- **Latency (e2e):** p50 ≤ 50 ms, p95 ≤ 150 ms, p99 ≤ 300 ms
- **Availability:** 99.5%+ สำหรับบริการแจ้งเตือน
- **Loss:** deliver/publish ratio ≥ 99.9% สำหรับ topic สำคัญ
- **Recovery:** MTTR < 15 นาที (service), < 2 นาที (camera reconnect)

---

## ความเสี่ยงหลัก & วิธีบรรเทา
- **I/O หนักจากการเก็บภาพ:** เก็บเฉพาะช่วง event + ใช้ object storage
- **CPU/GPU คอขวด:** ใช้ trigger-based AI, batch/stride, pin affinity
- **Schema drift:** ใช้ schema version + adapter layer
- **Backpressure:** bounded queue + drop policy + alert
- **ความเป็นส่วนตัว:** masking/retention, RBAC

---

## Checklists รวดเร็วต่อฟีเจอร์ยอดนิยม
- LINE/Slack Alert
  - [ ] threshold + dedup
  - [ ] snapshot
  - [ ] retry/backoff
- DB Persistence
  - [ ] events table
  - [ ] retention job
  - [ ] index เวลา/กล้อง
- Multi-camera
  - [ ] แยก `cam_id` ทุก topic
  - [ ] per-cam metrics & health
  - [ ] capacity plan ต่อเครื่อง

---

## Definition of Done (Production)
- [ ] ผ่าน Phase 4 ทั้งหมด
- [ ] มี Dashboard+Alert ครบ
- [ ] มี Runbook (incident, backup, restore)
- [ ] Soak test 7–14 วัน ไม่มี error/alert ผิดปกติ

