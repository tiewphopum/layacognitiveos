
from __future__ import annotations

import time
from typing import Any, Iterable, List, Tuple

import numpy as np

from layaos.core import log
from layaos.core.contracts import DetectionEvent, CellStat, BBox
from layaos.vision.motion_baseline import MotionBaseline, MotionBaselineConfig


def _get(obj: Any, keys, default=None):
    """Fetch attribute/key from dict/object; keys can be str or iterable of candidates."""
    if not isinstance(keys, (list, tuple)):
        keys = (keys,)
    for k in keys:
        if isinstance(obj, dict) and k in obj:
            return obj[k]
        if hasattr(obj, k):
            return getattr(obj, k)
    return default


class MotionFullFrame:
    """
    Wrapper around MotionBaseline: ensures output is a DetectionEvent
    and supports multiple baseline signatures.
    """

    def __init__(self, cfg: MotionBaselineConfig, cam_id: str = "cam0"):
        self._mb = MotionBaseline(cfg)
        self._last_frame: np.ndarray | None = None
        self._cam_id = cam_id
        self._l = log.get("vision.motion_fullframe")

    def _call_process(self, frame: np.ndarray) -> Any:
        """Fallback chain to support different baseline signatures."""
        # 1) process(frame)
        try:
            return self._mb.process(frame)  # type: ignore[arg-type]
        except TypeError:
            pass
        # 2) process(prev, frame)
        try:
            return self._mb.process(self._last_frame, frame)  # type: ignore[arg-type]
        except TypeError:
            pass
        # 3) process(frame=..., prev=...)
        try:
            return self._mb.process(frame=frame, prev=self._last_frame)  # type: ignore[call-arg]
        except TypeError:
            pass
        # give up
        raise

    def detect(self, frame: np.ndarray) -> DetectionEvent:
        """Run baseline and return unified DetectionEvent."""
        # Try preferred (cam_id, frame) first
        try:
            result = self._mb.process(self._cam_id, frame)
        except (TypeError, AttributeError):
            result = self._call_process(frame)

        # Extract fields from result (dict or object)
        any_motion = bool(_get(result, "any_motion", False))
        ratio = float(_get(result, ("motion_ratio", "ratio"), 0.0) or 0.0)

        cells_raw = _get(result, ("cells", "cell_ratios"), [])
        bboxes_raw = _get(result, ("bboxes", "boxes"), [])

        cells: List[CellStat] = []
        if isinstance(cells_raw, dict):
            # e.g., {"0": 0.1, "1": 0.0, ...}
            for k, v in cells_raw.items():
                try:
                    cells.append(CellStat(idx=int(k), ratio=float(v)))
                except Exception:
                    continue
        elif isinstance(cells_raw, (list, tuple)):
            for i, c in enumerate(cells_raw):
                if isinstance(c, dict):
                    idx = int(c.get("idx", i))
                    r = float(c.get("ratio", 0.0))
                    cells.append(CellStat(idx=idx, ratio=r))
                else:
                    # assume scalar ratio
                    try:
                        cells.append(CellStat(idx=i, ratio=float(c)))
                    except Exception:
                        continue

        bboxes: List[BBox] = []
        if isinstance(bboxes_raw, (list, tuple)):
            for bb in bboxes_raw:
                if isinstance(bb, dict):
                    try:
                        bboxes.append(BBox(
                            x=int(bb["x"]), y=int(bb["y"]),
                            w=int(bb["w"]), h=int(bb["h"]),
                            score=bb.get("score"), cls=bb.get("cls"),
                        ))
                    except Exception:
                        continue
                else:
                    # assume (x,y,w,h)
                    try:
                        x, y, w, h = bb  # type: ignore[misc]
                        bboxes.append(BBox(x=int(x), y=int(y), w=int(w), h=int(h)))
                    except Exception:
                        continue

        det = DetectionEvent(
            ts=time.time(),
            cam_id=self._cam_id,
            any_motion=any_motion,
            motion_ratio=ratio,
            cells=cells,
            bboxes=bboxes,
        )


        # --- Fallback: naive frame-diff if baseline reports no motion ---
        if (not det.any_motion) and (not cells) and (not bboxes) and (self._last_frame is not None):
            try:
                prev = self._last_frame
                cur = frame
                if prev.shape == cur.shape:
                    # compute absolute difference on luminance
                    if cur.ndim == 3:
                        curY = (0.114*cur[...,0] + 0.587*cur[...,1] + 0.299*cur[...,2])
                        prevY = (0.114*prev[...,0] + 0.587*prev[...,1] + 0.299*prev[...,2])
                    else:
                        curY = cur
                        prevY = prev
                    diff = np.abs(curY.astype(np.float32) - prevY.astype(np.float32))
                    thr = max(5.0, diff.mean() + 2*diff.std())  # adaptive-ish threshold
                    motion_mask = (diff > thr)
                    ratio_fallback = float(motion_mask.mean())
                    # simple 3x3 grid cell ratios
                    h, w = motion_mask.shape[:2]
                    gh, gw = h//3, w//3
                    cell_list = []
                    for gy in range(3):
                        for gx in range(3):
                            y0, y1 = gy*gh, (gy+1)*gh if gy<2 else h
                            x0, x1 = gx*gw, (gx+1)*gw if gx<2 else w
                            cell_ratio = float(motion_mask[y0:y1, x0:x1].mean())
                            cell_list.append(CellStat(idx=gy*3+gx, ratio=cell_ratio))
                    det.any_motion = ratio_fallback > 0.001
                    det.motion_ratio = max(det.motion_ratio, ratio_fallback)
                    det.cells = cell_list
            except Exception:
                pass
        self._last_frame = frame

        # Log succinctly
        (self._l.info if det.any_motion else self._l.debug)(
            f"cam={self._cam_id} any={det.any_motion} ratio={det.motion_ratio:.4f} "
            f"cells={len(det.cells)} bboxes={len(det.bboxes)}"
        )

        return det
