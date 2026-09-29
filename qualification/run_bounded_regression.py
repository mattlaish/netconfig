#!/usr/bin/env python3
"""Run the NetConfig pytest inventory in deterministic bounded file groups."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = re.compile(
    r"(?:(?P<passed>\d+) passed)?(?:,?\s*(?P<failed>\d+) failed)?(?:,?\s*(?P<skipped>\d+) skipped)?"
)


def _parse_counts(text: str) -> tuple[int, int, int]:
    passed = failed = skipped = 0
    for line in reversed(text.splitlines()):
        if " passed" not in line and " failed" not in line and " skipped" not in line:
            continue
        m = SUMMARY.search(line.strip())
        if m:
            passed = int(m.group("passed") or 0)
            failed = int(m.group("failed") or 0)
            skipped = int(m.group("skipped") or 0)
            return passed, failed, skipped
    return passed, failed, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--groups", type=int, default=5)
    parser.add_argument("--group-timeout", type=int, default=60)
    args = parser.parse_args(argv)
    if args.groups < 1 or args.groups > 20:
        raise SystemExit("--groups must be between 1 and 20")

    files = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").rglob("test_*.py"))
    groups = [files[i::args.groups] for i in range(args.groups)]
    totals = {"passed": 0, "failed": 0, "skipped": 0}
    rc_final = 0
    seen: list[str] = []
    for idx, group in enumerate(groups, 1):
        if not group:
            continue
        seen.extend(group)
        print(f"=== bounded group {idx}/{args.groups}: {len(group)} files ===", flush=True)
        try:
            cp = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", *group],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
                timeout=args.group_timeout,
            )
            combined = (cp.stdout or "") + (cp.stderr or "")
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            combined = out + err + f"\nGROUP TIMEOUT after {args.group_timeout}s\n"
            cp = subprocess.CompletedProcess([], 124, out, err)
        print(combined, end="" if combined.endswith("\n") else "\n", flush=True)
        p, f, s = _parse_counts(combined)
        totals["passed"] += p
        totals["failed"] += f
        totals["skipped"] += s
        if cp.returncode != 0:
            rc_final = 1

    if sorted(seen) != files or len(seen) != len(set(seen)):
        print("bounded partition integrity failure: tests missing or duplicated", file=sys.stderr)
        return 1
    collected = sum(totals.values())
    print(
        "Q2 bounded regression: "
        f"{collected} collected / {totals['passed']} passed / "
        f"{totals['skipped']} skipped / {totals['failed']} failed"
    )
    return rc_final


if __name__ == "__main__":
    raise SystemExit(main())
