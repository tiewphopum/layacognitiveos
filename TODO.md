# TODO — LayaOS Motion Pipeline (S1–S6)

> แผนงานปัจจุบันโฟกัส: เติม Logic S4–S6 → เชื่อม Storage/WS → ทำ Testing/Observability → ปรับให้ Config‑driven

---

## 0) Quick Start / Smoke Test
- [ ] รัน demo พื้นฐานเพื่อเช็คว่า environment พร้อม
  - [ ] `python scripts/demo_bootstrap.py` (ทดสอบ metrics exporter + counter/hist) 【8†source】
  - [ ] `python scripts/demo_motion.py` (กล้องจำลอง + S1–S3 + สรุป metrics) 【8†source】
- [ ] ตรวจ log ว่ามี `demo start: running ~20s` และสรุป `DEMO SUMMARY` แสดง `det_count`, `avg_ratio`, `p50_e2e_ms` 【8†source】

## 1) เติม Logic ให้ States
### S4_Context (`src/layaos/pipeline/state4_context.py`)
- [ ] เพิ่ม temporal smoothing ของ motion_ratio (เช่น EMA/median over N)
- [ ] รวม context จากหลายแหล่ง (เช่น grid/cells, time-of-day)
- [ ] ออกแบบ schema ของ event context (เช่น `{"ctx":{"ratio_ema":..,"active_cells":[..]}}`)
- [ ] ส่งต่อ topic_out (`s4.ctx`) พร้อม metadata ที่เพิ่มแล้ว 【8†source】

### S5_Imagination (`src/layaos/pipeline/state5_imagination.py`)
- [ ] เพิ่ม heuristic short-horizon forecast (เช่น โมเดล 1–2 สเต็ป ahead ของ ratio/cell)
- [ ] ระบุ confidence และ scenario label (e.g., `forecast_up`, `stable`)
- [ ] ป้อนผลสู่ `s5.img` 【8†source】

### S6_Action (`src/layaos/pipeline/state6_action.py`)
- [ ] สร้าง mapping จากเหตุผล/บริบท → ActionEvent (เช่น `alert`, `record`, `ws_publish`)
- [ ] รองรับหลาย sink: (a) Local storage, (b) WebSocket Hub
- [ ] แปลงเหตุการณ์เป็น payload เบา ๆ พร้อม timestamp และ correlation id
- [ ] (ทางเลือก) Debounce/Rate‑limit เพื่อลด spam event 【8†source】

## 2) Integrations
### Storage (LocalEventStorage / AsyncStorage)
- [ ] เลือก/ประกาศ output directory และ prefix
- [ ] บันทึก JSON ของเหตุการณ์สำคัญ (เช่น `det/`, `ctx/`, `act/`)
- [ ] (ถ้าต้องการ) บันทึกภาพสำคัญด้วย `save_image()` เมื่อ trigger สูง
- [ ] เพิ่ม metrics: `storage_write_total`, `storage_queue_depth`, `storage_write_ms` ที่มีอยู่แล้วให้ครอบคลุม use‑case 【8†source】

### WebSocket Hub (`src/layaos/adapters/ws_hub.py`)
- [ ] เชื่อมต่อกับ Hub; เพิ่มการ publish action ไปยัง topic กลาง (เช่น `events/action`)
- [ ] รองรับ reconnect (มีในคลาสอยู่แล้ว) และ retry policy
- [ ] นิยามสัญญา payload (ไอดี, ชนิดเหตุการณ์, กล้อง, เวลา, ค่าประเมิน) 【8†source】

## 3) Observability / Metrics
- [ ] กำหนด metric schema: `frame_rate`, `motion_ratio`, `demo_e2e_ms`, `bus_*`, `clock_loop_ms`
- [ ] ใช้ `start_exporter()` ใน main เพื่อ emit snapshot ทุก N วินาที
- [ ] ตรวจวัด latency ราย state: ใช้ `observe_hist("latency_ms{state=...}", ...)` ในแต่ละสเตตแล้วสรุป p50/p90/p99 【8†source】

## 4) Bus/Clock/Core ตรวจสอบพื้นฐาน
- [ ] EventBus: ทดสอบ publish ทั้งแบบ Event และ `(topic, data)`; wildcard `a.*`; queue_depth ต่อ topic 【8†source】
- [ ] BeatClock: ทดสอบ `ticks()` async ให้คาบเวลา ~ 1/hz และไม่ drift มาก 【8†source】
- [ ] Dispatcher: route exact match และกรณีไม่พบ handler 【8†source】
- [ ] RingBuffer: push/pop/peek และ capacity overflow 【8†source】

## 5) Testing Strategy
- [ ] **Unit tests**
  - [ ] vision: `MotionBaseline.process()` threshold และ ratio ถูกต้อง
  - [ ] vision wrapper: `MotionFullFrame.detect()` คืน `DetectionEvent` พร้อม `any_motion`, `motion_ratio`, `cells`, `bboxes` 【8†source】
  - [ ] storage: เขียน/flush/atomic replace สำเร็จ; drop policy เมื่อ queue เต็ม 【8†source】
  - [ ] ws_hub: mock websockets; subscribe/publish/auto‑reconnect 【8†source】
- [ ] **Integration tests**
  - [ ] `wire_minimal.run_pipeline(seconds=2)` แล้วมี event ไหล `cam/0.frame → s1.raw → s2.pre → s3.det → s4.ctx → s5.img` 【8†source】
  - [ ] S6 ทำงานจริง: เขียนไฟล์/ส่ง WS ได้
- [ ] **Tooling**
  - [ ] run `python -m layaos.tools.check_dupes` ใน CI เพื่อตรวจ symbol ซ้ำ 【8†source】

## 6) Config‑Driven Pipeline
- [ ] แยก config YAML/JSON แทนการ hardcode ใน `wire_minimal.build_pipeline()`
- [ ] ออกแบบ schema (ตัวอย่าง)
  ```yaml
  camera:
    type: mock
    hz: 12
    width: 128
    height: 96
  states:
    - name: S1
      in: cam/0.frame
      out: s1.raw
      hz: 12
    - name: S2
      in: s1.raw
      out: s2.pre
      hz: 12
    - name: S3
      in: s2.pre
      out: s3.det
      hz: 12
      detector: motion_fullframe
    - name: S4
      in: s3.det
      out: s4.ctx
      hz: 2
    - name: S5
      in: s4.ctx
      out: s5.img
      hz: 1
    - name: S6
      in: s5.img
      out: null
      hz: 2
  sinks:
    - type: storage
      out_dir: data
    - type: ws
      url: ws://127.0.0.1:8765
  ```
- [ ] เพิ่ม factory: อ่าน config → สร้างกล้อง/สเตต/ดีเทคเตอร์ตามชื่อ

## 7) Real Camera (ภายหลัง Mock)
- [ ] เพิ่ม OpenCV/RTSP source เป็น `CameraSource` ที่เข้ากับโปรโตคอลใน `ports.py` 【8†source】
- [ ] ปรับ MotionBaseline ให้รองรับหลายกล้อง (มี map `prev_gray_by_cam` แล้ว) 【8†source】

## 8) Documentation
- [ ] วาด sequence/mermaid ของ pipeline S1–S6
- [ ] อธิบาย Topic contract ต่อ state
- [ ] README: วิธีรัน demo, วิธีเปิด metrics, วิธีต่อ WS/Storage

## 9) Acceptance Criteria (รอบนี้)
- [ ] รัน `python scripts/demo_motion.py` ผ่านโดยไม่มี error และสรุปสถิติมีค่า > 0
- [ ] Integration test แรกผ่าน: event ไหลครบ S1→S6 ภายใน 2 วินาที
- [ ] เมื่อ motion สูงกว่า threshold: เกิด ActionEvent 1 รายการ ถูกส่งไป storage/WS อย่างน้อย 1 ช่องทาง
- [ ] มี metrics p50/p90/p99 ของแต่ละ state ใน log snapshot
- [ ] ไม่มี duplicated symbols (`check_dupes.py` ผ่าน) 【8†source】

---

## ภาคผนวก — ตำแหน่งไฟล์อ้างอิง
- `scripts/demo_bootstrap.py`, `scripts/demo_motion.py` — เดโม่/เมตริกส์ 【8†source】
- `src/layaos/pipeline/*.py` — S1–S6 states & wiring (`wire_minimal.py`) 【8†source】
- `src/layaos/vision/*` — MotionBaseline & MotionFullFrame 【8†source】
- `src/layaos/adapters/storage.py`, `adapters/ws_hub.py` — Integrations 【8†source】
- `src/layaos/core/*` — bus/clock/metrics/log/buffer/contracts 【8†source】

