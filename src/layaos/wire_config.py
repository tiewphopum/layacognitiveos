# src/layaos/wire_config.py
from __future__ import annotations
import importlib
from types import SimpleNamespace
from pathlib import Path
from typing import Any, Dict, Tuple, List

try:
    import yaml  # PyYAML
except ImportError as e:
    raise RuntimeError("Please install PyYAML: pip install pyyaml") from e

from layaos.core.bus import Bus  # ปรับให้ตรงกับที่โปรเจกต์คุณใช้จริง

def _imp(module: str, cls: str):
    mod = importlib.import_module(module)
    return getattr(mod, cls)

def _mk_cfg(d: Dict[str, Any]):
    # ให้ state ใช้งาน .cfg.foo ได้ (เหมือนเดิม)
    return SimpleNamespace(**(d or {}))

def build_from_yaml(yaml_path: str) -> Tuple[Bus, List[Any]]:
    """อ่าน pipeline.yaml แล้วประกอบ bus/detector/states ให้พร้อมใช้งาน"""
    data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))

    # bus
    bus_cfg = data.get("bus", {}) or {}
    bus = Bus(daemon=bool(bus_cfg.get("daemon", True)))

    # detector (ถ้ามี)
    detector = None
    det_cfg = data.get("detector")
    if det_cfg:
        DetCls = _imp(det_cfg["module"], det_cfg["class"])
        det_args = det_cfg.get("args") or {}
        detector = DetCls(**det_args)

    # states
    states = []
    for s in data.get("states", []):
        StateCls = _imp(s["module"], s["class"])
        cfg = _mk_cfg(s.get("cfg") or {})
        # ส่วนใหญ่ฐาน PipelineState รับ (cfg, bus), บางตัวเช่น s3 ต้องการ detector
        if "Perception" in s["class"]:
            instance = StateCls(cfg, bus, detector=detector)
        else:
            instance = StateCls(cfg, bus)
        states.append(instance)

    return bus, states