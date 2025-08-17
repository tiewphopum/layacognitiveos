
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from statistics import mean
from typing import Any, Deque, Dict, Optional, Tuple, Iterable

# ---------------- Utilities ----------------

LabelKey = Tuple[Tuple[str, str], ...]  # sorted tuple of (k,v)


def _labels_key(labels: Dict[str, Any] | None) -> LabelKey:
    if not labels:
        return tuple()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _pct(sorted_vals: Iterable[float], q: float) -> float:
    vals = list(sorted_vals)
    if not vals:
        return 0.0
    idx = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * q))))
    return vals[idx]


# ---------------- Metric types ----------------

@dataclass
class _Base:
    name: str
    labels: LabelKey


class Counter(_Base):
    def __init__(self, name: str, labels: LabelKey):
        super().__init__(name, labels)
        self._value = 0.0
        self._lock = threading.Lock()

    def inc(self, n: float = 1.0) -> None:
        with self._lock:
            self._value += n

    def value(self) -> float:
        with self._lock:
            return self._value


class Gauge(_Base):
    def __init__(self, name: str, labels: LabelKey):
        super().__init__(name, labels)
        self._value = 0.0
        self._lock = threading.Lock()

    def set(self, v: float) -> None:
        with self._lock:
            self._value = float(v)

    def value(self) -> float:
        with self._lock:
            return self._value


class Histogram(_Base):
    def __init__(self, name: str, labels: LabelKey, maxlen: int = 2048):
        super().__init__(name, labels)
        self._values: Deque[float] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def observe(self, v: float) -> None:
        with self._lock:
            self._values.append(float(v))

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            vals = list(self._values)
        if not vals:
            return {
                "count": 0,
                "min": 0.0,
                "max": 0.0,
                "mean": 0.0,
                "p50": 0.0,
                "p90": 0.0,
                "p99": 0.0,
            }
        vals_sorted = sorted(vals)
        return {
            "count": float(len(vals)),
            "min": vals_sorted[0],
            "max": vals_sorted[-1],
            "mean": mean(vals),
            "p50": _pct(vals_sorted, 0.50),
            "p90": _pct(vals_sorted, 0.90),
            "p99": _pct(vals_sorted, 0.99),
        }


# ---------------- Registry ----------------

class _Registry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: Dict[Tuple[str, LabelKey], Counter] = {}
        self._gauges: Dict[Tuple[str, LabelKey], Gauge] = {}
        self._hists: Dict[Tuple[str, LabelKey], Histogram] = {}

    def counter(self, name: str, labels: Dict[str, Any] | None) -> Counter:
        key = (name, _labels_key(labels))
        with self._lock:
            m = self._counters.get(key)
            if m is None:
                m = Counter(name, key[1])
                self._counters[key] = m
            return m

    def gauge(self, name: str, labels: Dict[str, Any] | None) -> Gauge:
        key = (name, _labels_key(labels))
        with self._lock:
            m = self._gauges.get(key)
            if m is None:
                m = Gauge(name, key[1])
                self._gauges[key] = m
            return m

    def hist(self, name: str, labels: Dict[str, Any] | None) -> Histogram:
        key = (name, _labels_key(labels))
        with self._lock:
            m = self._hists.get(key)
            if m is None:
                m = Histogram(name, key[1])
                self._hists[key] = m
            return m

    def items(self):
        with self._lock:
            return (
                list(self._counters.items()),
                list(self._gauges.items()),
                list(self._hists.items()),
            )


_REG = _Registry()

# ---------------- Public API ----------------

def inc_counter(name: str, n: float = 1.0, **labels: Any) -> None:
    _REG.counter(name, labels).inc(n)


def set_gauge(name: str, v: float, **labels: Any) -> None:
    _REG.gauge(name, labels).set(v)


def observe_hist(name: str, v: float, **labels: Any) -> None:
    _REG.hist(name, labels).observe(v)

# --- Backward-compat aliases (for older imports) ---
def inc(name: str, n: float = 1.0, **labels: Any) -> None:
    """Alias for inc_counter(name, n, **labels)."""
    inc_counter(name, n, **labels)

def gauge_set(name: str, v: float, **labels: Any) -> None:
    """Alias for set_gauge(name, v, **labels)."""
    set_gauge(name, v, **labels)


# ---------------- Exporter (log every N seconds) ----------------

class _Exporter(threading.Thread):
    def __init__(self, interval_sec: float = 5.0, json_mode: bool = False, logger: Optional[logging.Logger] = None):
        super().__init__(name="metrics-exporter", daemon=True)
        self.interval = float(interval_sec)
        self.json_mode = bool(json_mode)
        self.log = logger or logging.getLogger("metrics")
        self._stop_evt = threading.Event()

    def run(self) -> None:
        while not self._stop_evt.is_set():
            t0 = time.time()
            self._emit_snapshot()
            dt = time.time() - t0
            to_sleep = max(0.5, self.interval - dt)
            self._stop_evt.wait(to_sleep)

    def stop(self, timeout: float = 1.0) -> None:
        self._stop_evt.set()
        self.join(timeout=timeout)

    def _emit_snapshot(self) -> None:
        counters, gauges, hists = _REG.items()

        if self.json_mode:
            for (_, labels), m in counters:
                self.log.info({"type": "counter", "name": m.name, "labels": dict(labels), "value": m.value()})
            for (_, labels), m in gauges:
                self.log.info({"type": "gauge", "name": m.name, "labels": dict(labels), "value": m.value()})
            for (_, labels), m in hists:
                snap = m.snapshot()
                self.log.info({"type": "hist", "name": m.name, "labels": dict(labels), **snap})
        else:
            for (_, labels), m in counters:
                self.log.info(f"[ctr] {m.name} {dict(labels)} value={m.value():.0f}")
            for (_, labels), m in gauges:
                self.log.info(f"[gauge] {m.name} {dict(labels)} value={m.value():.3f}")
            for (_, labels), m in hists:
                s = m.snapshot()
                self.log.info(
                    f"[hist] {m.name} {dict(labels)} "
                    f"n={int(s['count'])} min={s['min']:.3f} p50={s['p50']:.3f} "
                    f"p90={s['p90']:.3f} p99={s['p99']:.3f} "
                    f"max={s['max']:.3f} mean={s['mean']:.3f}"
                )


_EXPORTER: Optional[_Exporter] = None


def start_exporter(interval_sec: float = 5.0, json_mode: bool = False, logger: Optional[logging.Logger] = None) -> None:
    global _EXPORTER
    if _EXPORTER is not None:
        return
    _EXPORTER = _Exporter(interval_sec=interval_sec, json_mode=json_mode, logger=logger)
    _EXPORTER.start()


def stop_exporter(timeout: float = 1.0) -> None:
    global _EXPORTER
    if _EXPORTER is not None:
        _EXPORTER.stop(timeout=timeout)
        _EXPORTER = None


# ---------------- Timer Helper ----------------

class Timer:
    """Context manager for measuring latency and reporting into a histogram."""
    def __init__(self, hist_name: str, **labels: Any) -> None:
        self.hist_name = hist_name
        self.labels = labels
        self._t0 = 0.0

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        dt_ms = (time.perf_counter() - self._t0) * 1000.0
        observe_hist(self.hist_name, dt_ms, **self.labels)
        return False


# ---------------- Snapshot helpers for tests ----------------



def snapshot() -> dict:
    """Backward-compat: return a snapshot of current metrics."""
    return snapshot_all()
def snapshot_all() -> dict:
    """Return a snapshot of current metrics (for tests)."""
    counters, gauges, hists = _REG.items()
    out = {"counters": [], "gauges": [], "hists": []}
    for (name, labels), m in counters:
        out["counters"].append({"name": name, "labels": dict(labels), "value": m.value()})
    for (name, labels), m in gauges:
        out["gauges"].append({"name": name, "labels": dict(labels), "value": m.value()})
    for (name, labels), m in hists:
        out["hists"].append({"name": name, "labels": dict(labels), **m.snapshot()})
    return out


def force_emit(logger: Optional[logging.Logger] = None, json_mode: bool = False) -> None:
    """Force emit metrics snapshot now (useful for tests without sleeping)."""
    _Exporter(interval_sec=0, json_mode=json_mode, logger=logger or logging.getLogger("metrics"))._emit_snapshot()
