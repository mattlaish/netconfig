"""
store.py -- On-disk config archive with versioning, diffs, and retention.

Layout:
    <root>/<device>/
        current.cfg                 # newest retrieved config (text)
        <UTC-timestamp>.cfg         # historical snapshots
        meta.json                   # per-device metadata (hashes, timestamps)

Design:
  * Text files, not a blob DB -- greppable, diffable with standard tools, and
    trivially fed into git or the SIEM if desired. difflib (stdlib) produces the
    unified diffs so a change to a config is a first-class, reviewable object.
  * A new snapshot is only written when the content hash changes, so a device
    polled hourly doesn't accumulate identical files. The 'collected' timestamp
    is always updated in meta so you can still see it was checked.
  * Retention keeps the last N distinct versions per device (default 30).
"""

import os
import re
import json
import hashlib
import difflib
import datetime


def _utc_stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_name(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


class ConfigStore:
    def __init__(self, root, keep_versions=30):
        self.root = root
        self.keep_versions = keep_versions
        os.makedirs(root, exist_ok=True)

    def _dir(self, device):
        d = os.path.join(self.root, _safe_name(device))
        os.makedirs(d, exist_ok=True)
        return d

    def _meta_path(self, device):
        return os.path.join(self._dir(device), "meta.json")

    def _load_meta(self, device):
        p = self._meta_path(device)
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
        return {"device": device, "versions": [], "last_collected": None,
                "last_hash": None, "last_changed": None}

    def _save_meta(self, device, meta):
        p = self._meta_path(device)
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(meta, f, indent=2)
        os.replace(tmp, p)

    def save(self, device, config_text):
        """Store a config. Returns dict: {changed, hash, version, diff}."""
        meta = self._load_meta(device)
        h = _sha256(config_text)
        now = _utc_stamp()
        meta["last_collected"] = now
        d = self._dir(device)

        if h == meta.get("last_hash"):
            self._save_meta(device, meta)
            return {"changed": False, "hash": h, "version": None, "diff": ""}

        # changed (or first) -> write snapshot + current
        prev_text = self.current(device)
        stamp = now
        snap = os.path.join(d, f"{stamp}.cfg")
        # avoid collision if two saves land in the same second
        i = 1
        while os.path.exists(snap):
            snap = os.path.join(d, f"{stamp}-{i}.cfg")
            i += 1
        with open(snap, "w") as f:
            f.write(config_text)
        with open(os.path.join(d, "current.cfg"), "w") as f:
            f.write(config_text)

        diff = ""
        if prev_text is not None:
            diff = self._unified(prev_text, config_text, device)

        meta["versions"].append({"stamp": os.path.basename(snap), "hash": h, "ts": now})
        meta["last_hash"] = h
        meta["last_changed"] = now
        self._save_meta(device, meta)
        self._prune(device, meta)
        return {"changed": True, "hash": h, "version": os.path.basename(snap), "diff": diff}

    def current(self, device):
        p = os.path.join(self._dir(device), "current.cfg")
        if os.path.exists(p):
            with open(p) as f:
                return f.read()
        return None

    def versions(self, device):
        return self._load_meta(device).get("versions", [])

    def read_version(self, device, stamp):
        d = self._dir(device)
        # Path-traversal guard: `stamp` may arrive from an HTTP query param
        # (/raw, /diff), so it must be a bare filename that resolves *inside*
        # the device directory. Reject separators, parent refs, and anything
        # whose real path escapes the device dir.
        if (not stamp or "/" in stamp or "\\" in stamp
                or os.path.basename(stamp) != stamp):
            raise FileNotFoundError(stamp)
        p = os.path.join(d, stamp)
        real_d = os.path.realpath(d)
        real_p = os.path.realpath(p)
        if os.path.commonpath([real_p, real_d]) != real_d:
            raise FileNotFoundError(stamp)
        if not os.path.exists(p):
            raise FileNotFoundError(stamp)
        with open(p) as f:
            return f.read()

    def diff_versions(self, device, stamp_a, stamp_b):
        a = self.read_version(device, stamp_a)
        b = self.read_version(device, stamp_b)
        return self._unified(a, b, device, stamp_a, stamp_b)

    @staticmethod
    def _unified(a, b, device, la="previous", lb="current"):
        return "".join(difflib.unified_diff(
            a.splitlines(keepends=True), b.splitlines(keepends=True),
            fromfile=f"{device}:{la}", tofile=f"{device}:{lb}"))

    def _prune(self, device, meta, keep=None):
        keep = self.keep_versions if keep is None else keep
        vers = meta.get("versions", [])
        if len(vers) <= keep:
            return
        drop = vers[:-keep]
        d = self._dir(device)
        for v in drop:
            try:
                os.remove(os.path.join(d, v["stamp"]))
            except OSError:
                pass
        meta["versions"] = vers[-keep:]
        self._save_meta(device, meta)

    def prune(self, device, keep):
        """Trim a device's archive to the newest `keep` snapshots. Returns how
        many are kept."""
        meta = self._load_meta(device)
        self._prune(device, meta, keep)
        return len(meta.get("versions", []))

    def rename(self, old, new):
        """Move a device's config archive directory old -> new."""
        src = os.path.join(self.root, _safe_name(old))
        dst = os.path.join(self.root, _safe_name(new))
        if os.path.isdir(src) and not os.path.exists(dst):
            os.rename(src, dst)
            try:
                meta = self._load_meta(new)
                meta["device"] = new
                self._save_meta(new, meta)
            except Exception:
                pass

    def devices(self):
        out = []
        for name in sorted(os.listdir(self.root)):
            p = os.path.join(self.root, name)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "meta.json")):
                out.append(self._load_meta(name))
        return out

    # ---- baseline / drift ------------------------------------------------
    def set_baseline(self, device, stamp=None):
        """Designate a version (default: current) as the golden baseline."""
        meta = self._load_meta(device)
        if stamp is None:
            stamp = meta.get("versions", [])[-1]["stamp"] if meta.get("versions") else None
            if stamp is None:
                raise ValueError("no stored config to baseline")
        # verify it exists
        self.read_version(device, stamp)
        meta["baseline"] = {"stamp": stamp, "hash": _sha256(self.read_version(device, stamp)),
                            "ts": _utc_stamp()}
        self._save_meta(device, meta)
        return meta["baseline"]

    def clear_baseline(self, device):
        meta = self._load_meta(device)
        meta.pop("baseline", None)
        self._save_meta(device, meta)

    def get_baseline(self, device):
        return self._load_meta(device).get("baseline")

    def baseline_text(self, device):
        b = self.get_baseline(device)
        if not b:
            return None
        try:
            return self.read_version(device, b["stamp"])
        except FileNotFoundError:
            return None

    def drift(self, device):
        """Compare current config to the baseline.
        Returns {baselined, drifted, diff, baseline_stamp}."""
        b = self.get_baseline(device)
        if not b:
            return {"baselined": False, "drifted": False, "diff": "", "baseline_stamp": None}
        base = self.baseline_text(device)
        cur = self.current(device)
        if base is None or cur is None:
            return {"baselined": True, "drifted": False, "diff": "",
                    "baseline_stamp": b["stamp"]}
        drifted = _sha256(cur) != _sha256(base)
        diff = self._unified(base, cur, device, "baseline", "current") if drifted else ""
        return {"baselined": True, "drifted": drifted, "diff": diff,
                "baseline_stamp": b["stamp"]}
