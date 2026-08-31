"""
session.py -- Per-connection transcript recording.

Every collection run can persist the full byte transcript of what happened on the
wire (login banner, commands sent, output received). This mirrors VaultGate's
session recording: useful for audit ("what did the tool actually run on that box?")
and for debugging a driver against an unfamiliar platform.

Transcripts can contain secrets (the config itself, possibly typed passwords echo
depending on the device). They are written 0600 and optionally scrubbed. Treat
this directory as sensitive.
"""

import os
import datetime

from . import scrub as _scrub


class SessionRecorder:
    def __init__(self, root, enabled=True, do_scrub=False):
        self.root = root
        self.enabled = enabled
        self.do_scrub = do_scrub
        if enabled:
            os.makedirs(root, exist_ok=True)

    def write(self, device, transcript_bytes):
        if not self.enabled:
            return None
        d = os.path.join(self.root, _safe(device))
        os.makedirs(d, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(d, f"{stamp}.log")
        text = bytes(transcript_bytes).decode("utf-8", "replace")
        if self.do_scrub:
            text, _ = _scrub.scrub(text)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(text)
        return path


def _safe(name):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
