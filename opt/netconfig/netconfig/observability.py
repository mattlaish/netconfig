"""Small stdlib-only JSON logging and Prometheus text metrics."""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict


_LOG = logging.getLogger("netconfig")
if not _LOG.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(message)s"))
    _LOG.addHandler(h)
_LOG.setLevel(logging.INFO)


def event(name, **fields):
    payload = {"ts": time.time(), "event": name, **fields}
    _LOG.info(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._counters = defaultdict(float)
        self._gauges = defaultdict(float)

    def inc(self, name, amount=1.0):
        with self._lock:
            self._counters[name] += float(amount)

    def set(self, name, value):
        with self._lock:
            self._gauges[name] = float(value)

    def render(self):
        with self._lock:
            rows = []
            for name, value in sorted(self._counters.items()):
                rows.append(f"# TYPE {name} counter")
                rows.append(f"{name} {value:g}")
            for name, value in sorted(self._gauges.items()):
                rows.append(f"# TYPE {name} gauge")
                rows.append(f"{name} {value:g}")
        return "\n".join(rows) + "\n"


METRICS = Metrics()
