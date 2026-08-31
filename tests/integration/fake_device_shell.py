#!/usr/bin/env python3
"""Tiny deterministic network-CLI shell used only by CI's real OpenSSH daemon."""
import sys

PROMPT = "R1#"
CONFIG = "hostname R1\ninterface GigabitEthernet1/0/1\n description CI\n switchport access vlan 10\n!\nend"


def emit(text=""):
    if text:
        sys.stdout.write(text + "\r\n")
    sys.stdout.write(PROMPT)
    sys.stdout.flush()


emit()
for raw in sys.stdin:
    cmd = raw.strip()
    if cmd in {"exit", "logout"}:
        break
    if cmd in {"show running-config", "show run"}:
        emit(CONFIG)
    elif cmd in {"terminal length 0", "configure terminal", "end", "exit"}:
        emit()
    else:
        emit()
