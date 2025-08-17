# LayaOS Motion Pipeline Demo

This repository contains a demo of the **Core Motion Detection Pipeline**  
for LayaOS. It shows how to capture frames, process them through pipeline
states (S1–S3), and publish detection events (`s3.det`) into an event bus.

## 🚀 Quick Start

### Requirements
- Python 3.11+
- Dependencies: `pip install -r requirements.txt`

### Run Demo
```bash
python scripts/demo_motion.py
```

Expected output (20s run):

```
[INFO] demo.motion | demo start: running ~20s
[DBG] det event keys: ['det', 'motion_ratio', 'ts']
[DBG] det payload keys: ['ratio', 'ts']
[INFO] demo.motion | === DEMO SUMMARY ===
[INFO] demo.motion | det_count=79 avg_ratio=0.0421 p50_e2e_ms=6.82
```

## 📊 Metrics
Metrics are exported via the built-in exporter.

- `demo_e2e_ms` – End-to-end latency (ms) from capture → detection → subscriber
- `demo_det_total` – Total number of detection events observed
- `avg_ratio` – Average motion ratio from detections

## 🧩 Pipeline Overview
- **Camera** – frame generator (`cam`)  
- **States S1–S3** – preprocessing and motion detection  
- **Bus** – publish/subscribe backbone  
- **Subscriber** – `on_det` receives `s3.det` events  
- **Metrics** – observability with latency, throughput, motion stats  

## 📂 Repo Structure
```
.
├── scripts/
│   └── demo_motion.py
├── layaos/
│   └── core/ ...
├── tests/
│   └── ...
└── docs/
    └── ARCHITECTURE.md
```

## 🔖 Version
- v0.1 – Core Motion Pipeline Stable
