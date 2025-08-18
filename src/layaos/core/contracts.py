
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
    NDArray = np.ndarray  # type: ignore[name-defined]
except Exception:  # pragma: no cover
    np = None  # type: ignore[assignment]
    NDArray = Any  # type: ignore[misc]


__all__ = [
    "EventId",
    "Event",
    "BBox",
    "CellStat",
    "BaseEvent",
    "FrameEvent",
    "DetectionEvent",
    "ReasonEvent",
    "ActionEvent",
]


# --------- Primitive / aliases ---------
EventId = str


# --------- Lightweight bus wrapper (for EventBus) ---------
@dataclass(slots=True)
class Event:
    """Simple bus envelope: a topic and its payload (data)."""
    topic: str
    data: Any

    # Backward-compat aliases used by some tests/code
    @property
    def payload(self) -> Any:
        return self.data

    @property
    def value(self) -> Any:
        return self.data

    @property
    def body(self) -> Any:
        return self.data

    @property
    def content(self) -> Any:
        return self.data

    @property
    def message(self) -> Any:
        return self.data


@dataclass(slots=True)
class BBox:
    x: int
    y: int
    w: int
    h: int
    score: Optional[float] = None
    cls: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BBox":
        return cls(**d)


@dataclass(slots=True)
class CellStat:
    """A single grid cell motion stat."""
    idx: int                     # linear index (r*cols + c), or custom mapping
    ratio: float                 # motion ratio in [0,1]
    thr: Optional[float] = None  # threshold used when computed

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CellStat":
        return cls(**d)


# --------- Base event ---------
@dataclass(slots=True)
class BaseEvent:
    ts: float                                  # UNIX epoch seconds (float)
    event_id: EventId = field(default_factory=lambda: str(uuid.uuid4()))
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BaseEvent":
        return cls(**d)


# --------- Concrete events (aligned & simplified) ---------
@dataclass(slots=True)
class FrameEvent(BaseEvent):
    cam_id: str = "cam0"
    frame: NDArray | None = None               # raw frame (BGR uint8)
    shape: Tuple[int, int, int] | None = None  # (H, W, C), auto-infer if None

    def __post_init__(self):
        if self.frame is None:
            raise ValueError("FrameEvent requires frame")
        if self.shape is None and hasattr(self.frame, "shape"):
            try:
                self.shape = tuple(self.frame.shape)  # type: ignore[assignment]
            except Exception:
                pass

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FrameEvent":
        # Expect callers to reconstruct 'frame' explicitly if needed.
        return cls(**d)


@dataclass(slots=True)
class DetectionEvent(BaseEvent):
    cam_id: str = "cam0"
    any_motion: bool = False
    motion_ratio: float = 0.0
    cells: List[CellStat] = field(default_factory=list)
    bboxes: List[BBox] = field(default_factory=list)

    # Backward-compat: allow det.ratio access
    @property
    def ratio(self) -> float:
        return self.motion_ratio

    # Backward-compat: expose list of ratios as det.cell_ratios
    @property
    def cell_ratios(self) -> List[float]:
        try:
            return [float(c.ratio) for c in self.cells]
        except Exception:
            return []

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["cells"] = [c.to_dict() for c in self.cells]
        d["bboxes"] = [b.to_dict() for b in self.bboxes]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DetectionEvent":
        cells = [CellStat.from_dict(c) for c in d.get("cells", [])]
        bboxes = [BBox.from_dict(b) for b in d.get("bboxes", [])]
        d = {**d, "cells": cells, "bboxes": bboxes}
        return cls(**d)


@dataclass(slots=True)
class ReasonEvent(BaseEvent):
    """Semantic/contextual reasoning derived from detections & memory."""
    cam_id: Optional[str] = None
    label: str = ""                 # e.g., "motion_in_region", "intrusion"
    score: Optional[float] = None
    context: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReasonEvent":
        return cls(**d)


@dataclass(slots=True)
class ActionEvent(BaseEvent):
    """Action decision to be executed by an actuator or external system."""
    action: str = ""                # e.g., "alert", "record", "light_on"
    target: Optional[str] = None    # e.g., "ws://...", "file://...", device id
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionEvent":
        return cls(**d)
