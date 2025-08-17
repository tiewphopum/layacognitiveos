# **Roadmap: Laya (อัปเดตความคืบหน้า)**

### **ระยะที่ 0 — Bootstrap ✅ เสร็จแล้ว**

* log, clock, bus
* test\_bus\_min, test\_pipeline\_min
* metrics.py (counter/gauge/histogram + log export)
* Acceptance: pytest ผ่าน, มี metric log ทุก 5 วิ

---

### **ระยะที่ 1 — I/O พื้นฐาน & Data Contracts ⚡ ส่วนใหญ่เสร็จ**

* adapters/camera.py (mock + opencv)
* adapters/storage.py (async queue save JSON/frame)
* adapters/ws\_hub.py (เพิ่งเพิ่ม client แล้ว, server รอระยะ 4)
* contracts: FrameEvent, DetectionEvent, ReasonEvent, ActionEvent (มีใน **contracts.py**)
* tests/test\_camera\_to\_bus.py (mock frame → bus → storage)

**สถานะ:** ✅ ผ่าน acceptance เบื้องต้น

---

### **ระยะที่ 2 — 6-State Minimal Pipeline 🚧 ทำไปแล้วบางส่วน**

* pipeline/state{1–6}.py skeleton + StateBase
* BeatClock แยกจังหวะต่อ state
* InProcEventBus รองรับ topic + queue\_depth, try\_consume
* ทดสอบ timeline ครบทุก state (**test\_orchestra\_min.py**) → ยังต้องเขียนเพิ่ม

---

### **ระยะที่ 3 — Vision Baseline 🚧 เริ่มแล้ว**

* motion\_baseline.py (ของเดิม)
* vision/motion\_fullframe.py (wrap เป็น DetectionEvent)
* tests/test\_motion\_pipeline.py → ยังไม่ได้เขียน
* toggle headless / show-window → ยังไม่ทำ

---

### **ระยะที่ 4 — Realtime & Integration ⏳**

* ws\_server (hub/broadcast) → ยัง
* ws\_client (adapters/ws\_hub.py) → มีแล้ว
* dashboard text/JSON metrics → ยัง
* keyboard/http control tempo/threshold/grid → ยัง
* tests/test\_ws\_roundtrip.py (จำลอง echo server)

---

### **ระยะที่ 5 — Packaging & DX ⏳**

* CLI (orchestrai up/demo)
* Dockerfile, Makefile, pre-commit
* CI (pytest, lint, mypy)
* README steps

---

## **สรุป Progress**

* **เสร็จเต็ม:** ระยะ 0, ระยะ 1
* **ก้าวหน้า:** ระยะ 2 (มีโครง state แล้ว), ระยะ 3 (มี motion\_fullframe แล้ว), ระยะ 4 (ws client+เทส)
* **ยังไม่เริ่มจริง:** ระยะ 5
