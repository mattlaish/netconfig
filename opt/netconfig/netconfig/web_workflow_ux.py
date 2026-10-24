"""Operator summaries over the existing approved-change workflow; no device I/O."""
import html
import json
import re


def e(value):
    return html.escape(str(value if value is not None else ""))


STAGES = {"incident": "Incident", "hypothesis": "Possible cause", "evidence": "Collected information",
          "topology_path": "Path analysis", "proposed_change": "Proposed change", "approval": "Approval",
          "structured_change": "Apply change", "validation": "Verify results"}


def words(value):
    return str(value or "Unknown").replace("_", " ").capitalize()


def summary_text(value):
    text = str(value or "")
    text = re.sub(r"PLAN#(\d+)", r"Path analysis #\1", text)
    text = re.sub(r"CR#(\d+)", r"Approval request #\1", text)
    text = re.sub(r"TX#(\d+)", r"Change result #\1", text)
    text = text.replace("Structured Change", "device change").replace("Automation Request", "approval request")
    return re.sub(r"\b[A-Z]+(?:_[A-Z]+)+\b", lambda m: words(m.group()), text)


def advanced(value, label="Advanced details"):
    return '<details><summary>' + e(label) + '</summary><pre>' + e(json.dumps(value, indent=2, sort_keys=True, default=str)) + '</pre></details>'


def proposal_summary(proposal):
    value = proposal.get("value")
    if isinstance(value, bool):
        value = "Enabled" if value else "Disabled"
    elif isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True)
    selectors = proposal.get("selectors") or {}
    target = ", ".join(f"{words(k)}: {v}" for k, v in selectors.items()) or "Device-wide setting"
    resource = {"interface_enabled": "Interface state"}.get(proposal.get("resource"), words(proposal.get("resource")))
    return ('<table><tr><th>Device to change</th><td>' + e(proposal.get("device") or "Not specified")
            + '</td></tr><tr><th>Setting</th><td>' + e(resource)
            + '</td></tr><tr><th>Target</th><td>' + e(target)
            + '</td></tr><tr><th>Requested value</th><td>' + e(value) + '</td></tr></table>')


def path_summary(path):
    path = path or {}
    hops = path.get("hops") or []
    devices = [str(h.get("device") or "Unknown device") for h in hops if isinstance(h, dict)]
    route = " → ".join(devices) or "No path could be determined from the collected information."
    return '<p><b>' + e(words(path.get("status"))) + '</b> · ' + e(route) + '</p>' + advanced(path)


def guide(handler, view, sess):
    plan = view.get("selected_plan") or {}
    req = (view.get("selected_request") or {}).get("request") or {}
    tx = view.get("selected_transaction") or {}
    proposals = view.get("proposals") or []
    devices = sorted({str(p.get("device")) for p in proposals if p.get("device")})
    if tx.get("device"):
        devices = [str(tx["device"])]
    # For submitted requests, show the reviewed intent, not a newer proposal list.
    if req:
        try:
            intent = (handler.wf.preview(int(req["id"])) or {}).get("automation", {}).get("intent", {})
            devices = [str(intent["device"])] if intent.get("device") else []
        except Exception:
            devices = []
    role = sess.get("role")
    can_change = role in {"operator", "approver", "admin"}
    can_execute = role in {"approver", "admin"}
    state = str(tx.get("state") or req.get("status") or plan.get("planning_status") or "Not started")
    link, label = "#workflow-plan", "Review path analysis"
    if tx.get("state") == "RECOVERY_REQUIRED":
        text = "The device outcome is uncertain. An administrator must check and reconcile the interrupted change before another attempt."
        link, label = "#workflow-result", "Review recovery"
    elif tx:
        text = "Review the change result, verification and rollback status. Compare the linked monitoring records before deciding whether the incident is resolved."
        link, label = "#workflow-result", "Review results"
    elif req.get("status") == "pending":
        text = "Review the requested device, setting and value before approving or rejecting." if can_execute else "Waiting for an approver or administrator to review this request."
        link, label = "#workflow-approval", "Review approval request"
    elif req.get("status") == "approved":
        text = ("Unlock the vault here, then apply the approved change." if not handler.manager.vault_ready()
                else "Review the approved request, then apply it. Safety checks still run before any device is changed.") if can_execute else "Waiting for an approver or administrator to apply the approved change."
        link, label = "#workflow-approval", "Continue approved change"
    elif req:
        text = "This request is " + words(req.get("status")).lower() + ". Review its outcome; rejected or failed requests cannot be applied."
        link, label = "#workflow-approval", "Review request outcome"
    elif proposals:
        text = "Review each proposed device change and submit one for approval." if can_change else "An operator must review and submit a proposed change for approval."
        link, label = "#workflow-proposals", "Review proposed changes"
    elif plan:
        text = "No supported device change is available. Review the path and missing information; do not assume a change is necessary."
    else:
        text = "Choose source and destination, then analyze the collected information." if can_change else "An operator must create a path analysis before a change can be proposed."
    return ('<div class="panel" aria-label="Workflow next step"><h3>Next step</h3><p>' + e(text)
            + '</p><p><b>Current status:</b> ' + e(words(state))
            + '</p><p><b>Devices to change:</b> ' + e(", ".join(devices) or "None confirmed")
            + '</p><p class="muted">This is not a list of every device or service that may be affected. Review dependencies and the change details before approval.</p>'
            + '<a class="btn" href="' + link + '">' + e(label) + '</a></div>')
