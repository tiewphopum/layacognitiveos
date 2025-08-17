# src/layaos/adapters/storage.py
from __future__ import annotations

import json
import time
import os
import queue
import threading
import logging
import uuid
from dataclasses import dataclass, asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional

# Optional metrics (no-op fallback)
try:
    from layaos.core.metrics import inc, gauge_set, observe_hist  # type: ignore
except Exception:  # pragma: no cover
    def inc(*args, **kwargs): pass
    def gauge_set(*args, **kwargs): pass
    def observe_hist(*args, **kwargs): pass

log = logging.getLogger("layaos.adapters.storage")


def _to_jsonable(obj: Any) -> Any:
    """พยายามแปลงอ็อบเจ็กต์ให้เป็น JSON-serializable"""
    # dataclass
    if is_dataclass(obj):
        return asdict(obj)

    # มี to_dict()
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass

    # numpy
    try:
        import numpy as np  # type: ignore
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)  # type: ignore[arg-type]
        if isinstance(obj, (np.floating,)):
            return float(obj)  # type: ignore[arg-type]
        if obj is np.nan:
            return None
    except Exception:
        pass

    # types ที่ serialize ได้อยู่แล้ว
    if isinstance(obj, (dict, list, str, int, float, bool)) or obj is None:
        return obj

    # เผื่อเป็นอ็อบเจ็กต์ปกติ
    d = getattr(obj, "__dict__", None)
    if isinstance(d, dict):
        return {k: _to_jsonable(v) for k, v in d.items()}

    # สุดท้าย แปลงเป็น string
    return str(obj)


class AsyncStorage:
    """Simple async JSON/Bytes writer with worker thread + atomic write."""
    def __init__(self, out_dir: str = "data", max_queue: int = 1024, prefix: str = "evt"):
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix
        self.q: "queue.Queue[tuple[str, Any]]" = queue.Queue(max_queue)
        self._th: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._th and self._th.is_alive():
            return
        self._stop.clear()
        self._th = threading.Thread(target=self._worker, name="AsyncStorage", daemon=True)
        self._th.start()
        log.info("storage start dir=%s max_queue=%d", self.dir.as_posix(), self.q.maxsize)

    def stop(self, timeout: float = 2.0) -> None:
        """ขอให้หยุด และรอคิวระบายให้หมดก่อน"""
        self._stop.set()
        try:
            # รอให้เคลียร์คิว (ป้องกันไฟล์ค้างไม่ครบ)
            self.q.join()
        except Exception:
            pass
        if self._th and threading.current_thread() is not self._th:
            self._th.join(timeout=timeout)
        log.info("storage stop")

    def put_json(self, kind: str, obj: Any) -> None:
        """Enqueue JSON write; drop oldest if full (backpressure-friendly)."""
        try:
            self.q.put_nowait((kind, obj))
        except queue.Full:
            # drop policy: remove one oldest then put
            try:
                _ = self.q.get_nowait()
                self.q.task_done()
            except Exception:
                pass
            try:
                self.q.put_nowait((kind, obj))
            except Exception:
                pass
            inc("storage_drops_total", 1, kind=kind)
        gauge_set("storage_queue_depth", float(self.q.qsize()))

    def put_bytes(self, kind: str, data: bytes) -> None:
        """Enqueue raw bytes write; file will have .bin extension."""
        try:
            self.q.put_nowait((f"{kind}::bytes", data))
        except queue.Full:
            try:
                _ = self.q.get_nowait()
                self.q.task_done()
            except Exception:
                pass
            try:
                self.q.put_nowait((f"{kind}::bytes", data))
            except Exception:
                pass
            inc("storage_drops_total", 1, kind=f"{kind}::bytes")
        gauge_set("storage_queue_depth", float(self.q.qsize()))

    def _worker(self) -> None:
        while not self._stop.is_set() or not self.q.empty():
            try:
                kind, obj = self.q.get(timeout=0.1)
            except queue.Empty:
                continue

            t0 = time.perf_counter()
            try:
                if kind.endswith("::bytes"):
                    real_kind = kind.split("::", 1)[0]
                    self._write_bytes(real_kind, obj)
                    inc("storage_write_total", 1, kind=real_kind)
                else:
                    self._write_json(kind, obj)
                    inc("storage_write_total", 1, kind=kind)
            except Exception as e:  # pragma: no cover
                log.error("write error: %s", e, exc_info=True)
            finally:
                dt_ms = (time.perf_counter() - t0) * 1000.0
                try:
                    observe_hist("storage_write_ms", dt_ms, kind=kind)
                except Exception:
                    pass
                self.q.task_done()
                gauge_set("storage_queue_depth", float(self.q.qsize()))

    def _write_json(self, kind: str, obj: Any) -> None:
        folder = self.dir / kind
        folder.mkdir(parents=True, exist_ok=True)
        ts_ns = time.time_ns()
        name = f"{self.prefix}-{ts_ns}-{uuid.uuid4().hex[:6]}.json"
        path = folder / name
        tmp = path.with_suffix(path.suffix + ".tmp")

        data = _to_jsonable(obj)
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _write_bytes(self, kind: str, data: bytes) -> None:
        folder = self.dir / kind
        folder.mkdir(parents=True, exist_ok=True)
        ts_ns = time.time_ns()
        name = f"{self.prefix}-{ts_ns}-{uuid.uuid4().hex[:6]}.bin"
        path = folder / name
        tmp = path.with_suffix(path.suffix + ".tmp")

        with tmp.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    # Convenience helpers (used by LocalEventStorage wrapper)
    def save_image(self, kind: str, frame, *, ext: str = ".png") -> Path:
        """Save numpy array frame as an image file, returns the path."""
        try:
            import numpy as np
            from PIL import Image  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Pillow and numpy required for save_image()") from e

        folder = self.dir / kind
        folder.mkdir(parents=True, exist_ok=True)
        ts_ns = time.time_ns()
        path = folder / f"{self.prefix}-{ts_ns}{ext}"

        arr = np.asarray(frame)
        if arr.ndim == 2:
            img = Image.fromarray(arr)
        elif arr.ndim == 3 and arr.shape[2] in (1, 3, 4):
            if arr.shape[2] == 1:
                arr = arr[..., 0]
                img = Image.fromarray(arr)
            else:
                img = Image.fromarray(arr[..., :3])
        else:
            raise ValueError(f"Unsupported frame shape: {arr.shape}")

        img.save(path)
        inc("storage_write_total", 1, kind=kind)
        return path

    def flush(self, timeout: float = 5.0) -> None:
        """Block until queue is empty or timeout reached."""
        # ใช้ q.join() ถ้าอยากให้บล็อคจนหมดคิว
        deadline = time.time() + timeout
        while time.time() < deadline and not self.q.empty():
            time.sleep(0.01)

    # เผื่อบางเทสต์อยาก q.join() เอง
    @property
    def queue(self) -> "queue.Queue[tuple[str, Any]]":
        return self.q


# --- Back-compat wrappers ---

@dataclass
class StorageConfig:
    # Support both 'out_dir' and 'root_dir' naming (older tests)
    out_dir: Optional[str] = None
    root_dir: Optional[str] = None
    prefix: str = "evt"
    max_queue: int = 1024

    def resolve_out_dir(self) -> str:
        return (self.out_dir or self.root_dir or "data")


class LocalEventStorage:
    """Thin wrapper around AsyncStorage to satisfy older tests importing this name."""
    def __init__(self, cfg: StorageConfig, logger=None):
        self.cfg = cfg
        out = cfg.resolve_out_dir()
        self._impl = AsyncStorage(out_dir=out, max_queue=cfg.max_queue, prefix=cfg.prefix)
        self._logger = logger or logging.getLogger("layaos.adapters.storage.local")

    def start(self) -> None:
        self._impl.start()

    def stop(self) -> None:
        self._impl.stop()

    # aliases for JSON events
    def put_json(self, kind: str, obj: Any) -> None:
        self._impl.put_json(kind, obj)

    def write_event(self, kind: str, obj: Any) -> None:
        self._impl.put_json(kind, obj)

    # image save API expected by some tests
    def save(self, kind: str, frame, *, ext: str = ".png") -> Path:
        return self._impl.save_image(kind, frame, ext=ext)

    def flush(self, timeout: float = 5.0) -> None:
        self._impl.flush(timeout=timeout)

    # convenience
    def dir(self) -> Path:
        return self._impl.dir