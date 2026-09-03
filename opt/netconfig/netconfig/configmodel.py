"""Offline semantic configuration model and remediation planner.

The model intentionally covers indentation-scoped network CLIs and JunOS
`display set`. It is conservative: unsupported constructs are retained as flat
commands and destructive removals are emitted only when a driver advertises a
negation verb.
"""
from __future__ import annotations

from dataclasses import dataclass, field


_NOISE_PREFIXES = (
    "building configuration", "current configuration", "version ",
    "boot-start-marker", "boot-end-marker",
)


@dataclass
class Node:
    text: str
    indent: int = 0
    children: list["Node"] = field(default_factory=list)


def clean_lines(text):
    out = []
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped == "!" or stripped.startswith("! "):
            continue
        low = stripped.lower()
        if low == "end" or low.startswith(_NOISE_PREFIXES):
            continue
        out.append(line)
    return out


def parse_indented(text):
    root = Node("<root>", -1)
    stack = [root]
    for raw in clean_lines(text):
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        node = Node(stripped, indent)
        while len(stack) > 1 and indent <= stack[-1].indent:
            stack.pop()
        stack[-1].children.append(node)
        stack.append(node)
    return root


def _paths(root):
    out = set()
    def walk(node, prefix):
        for child in node.children:
            path = prefix + (child.text,)
            out.add(path)
            walk(child, path)
    walk(root, ())
    return out


def _emit_transition(context, target, exit_command="exit"):
    common = 0
    for a, b in zip(context, target):
        if a != b:
            break
        common += 1
    cmds = [exit_command] * (len(context) - common)
    cmds.extend(target[common:])
    return cmds


def plan_indented(baseline, current, *, negation="no", exit_command="exit"):
    desired = _paths(parse_indented(baseline))
    actual = _paths(parse_indented(current))
    add = sorted(desired - actual, key=lambda p: (len(p), p))
    remove = sorted(actual - desired, key=lambda p: (-len(p), p))
    commands = []
    context = ()
    # Remove leaves first. Removing a child enters its parent context; top-level
    # additions/removals are emitted directly.
    for path in remove:
        # If an ancestor is also absent from desired state, remove that ancestor
        # once instead of trying to negate every child in a subtree.
        if any(path[:len(other)] == other for other in remove if len(other) < len(path)):
            continue
        parent, leaf = path[:-1], path[-1]
        commands += _emit_transition(context, parent, exit_command)
        context = parent
        commands.append(f"{negation} {leaf}".strip())
    for path in add:
        # Only emit leaf additions; entering parent modes creates context.
        if any(path == other[:len(path)] for other in add if len(other) > len(path)):
            continue
        parent, leaf = path[:-1], path[-1]
        commands += _emit_transition(context, parent, exit_command)
        context = parent
        commands.append(leaf)
    commands += [exit_command] * len(context)
    return {"commands": commands, "add": add, "remove": remove}


def plan_junos_set(baseline, current):
    desired = {line.strip() for line in clean_lines(baseline) if line.strip().startswith("set ")}
    actual = {line.strip() for line in clean_lines(current) if line.strip().startswith("set ")}
    add = sorted(desired - actual)
    remove = sorted(actual - desired)
    cmds = ["delete " + line[4:] for line in remove] + add
    return {"commands": cmds, "add": add, "remove": remove}
