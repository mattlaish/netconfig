"""Bounded UDP syslog receiver with change-triggered collection."""
import queue
import re
import socket
import threading
import time

CONFIG_PATTERNS = [
    re.compile(r"%SYS-5-CONFIG_I", re.I),
    re.compile(r"configured from (?:console|vty|ssh|snmp)", re.I),
    re.compile(r"configuration (?:changed|committed|saved)", re.I),
    re.compile(r"commit complete", re.I),
]


def is_config_change(message):
    return any(p.search(message or "") for p in CONFIG_PATTERNS)


class Collector:
    def __init__(self, manager, bind="0.0.0.0", port=5514, queue_size=256, debounce_seconds=30):
        self.manager = manager; self.bind = bind; self.port = int(port)
        self.queue = queue.Queue(maxsize=max(1, int(queue_size)))
        self.debounce = max(0, int(debounce_seconds)); self._last = {}
        self._sock = None; self._running = False; self._threads = []
        self.total_packets = 0; self.dropped = 0; self.triggered = 0; self.last_error = None

    def start(self):
        if self._running: return
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.bind, self.port)); s.settimeout(.5); self._sock = s; self._running = True
        self._threads = [threading.Thread(target=self._recv, daemon=True), threading.Thread(target=self._work, daemon=True)]
        [t.start() for t in self._threads]

    def stop(self):
        self._running = False
        if self._sock:
            try: self._sock.close()
            except OSError: pass

    def _recv(self):
        while self._running:
            try: data, addr = self._sock.recvfrom(65535)
            except socket.timeout: continue
            except OSError: break
            self.total_packets += 1
            msg = data.decode("utf-8", "replace")[:8192]
            try: self.queue.put_nowait((time.time(), addr[0], msg))
            except queue.Full: self.dropped += 1

    def _work(self):
        while self._running:
            try: ts, source, msg = self.queue.get(timeout=.5)
            except queue.Empty: continue
            try: self._handle(ts, source, msg)
            except Exception as exc: self.last_error = str(exc)
            finally: self.queue.task_done()

    def _handle(self, ts, source, msg):
        self.manager.db.record_syslog(source, msg)
        if not is_config_change(msg): return
        dev = self.manager.device_by_host(source)
        if not dev:
            self.manager.db.audit("syslog", "config_change_unmanaged_source", source, msg[:300]); return
        last = self._last.get(dev["name"], 0)
        if ts - last < self.debounce: return
        self._last[dev["name"]] = ts
        result = self.manager.collect(dev["name"])
        self.triggered += 1
        self.manager.db.audit("syslog", "triggered_collect", dev["name"], result.message[:500])

    def status(self):
        return {"running": self._running, "port": self.port, "queue_depth": self.queue.qsize(),
                "total_packets": self.total_packets, "dropped": self.dropped,
                "triggered": self.triggered, "last_error": self.last_error}
