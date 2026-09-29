"""R66 supportability Web rendering extracted from the core console."""
from __future__ import annotations

import html
import json
import urllib.parse

from .debug import DebugBundle
from .users import can as _can


class WebSupportabilityMixin:
    def _diagnostics_page(self, sess):
        if not _can(sess["role"], "view"):
            return self._send("forbidden", 403, "text/plain")
        snapshot = html.escape(json.dumps(self.manager.supportability.snapshot(), indent=2, sort_keys=True))
        inner = (
            '<div class="panel"><h2>Runtime Supportability</h2>'
            '<p class=muted>Read-only R66 snapshot for operators/viewers; no device polling, heartbeat write, or HA lock acquisition is triggered by this page.</p>'
            f'<pre>{snapshot}</pre></div>'
        )
        if _can(sess["role"], "settings"):
            rows = [
                f'<tr><td>{html.escape(item["name"])}</td><td>{item["size"]}</td>'
                f'<td><a href="/debug-download?name={urllib.parse.quote(item["name"])}">Download</a></td></tr>'
                for item in DebugBundle(self.manager).list_bundles()
            ]
            inner += (
                '<div class="panel"><h2>Diagnostic Support Bundles</h2>'
                '<p class=muted>Admin-only because bundles can contain sensitive operational evidence.</p>'
                f'<form method=post action="/debug-create">{self._csrf_field()}<button>Create support bundle</button></form>'
                '<table><tr><th>Bundle</th><th>Size</th><th></th></tr>'
                + (''.join(rows) or '<tr><td colspan=3 class=muted>No bundles</td></tr>')
                + '</table></div>'
            )
        else:
            inner += '<div class="panel"><p class=muted>Support-bundle creation and download are admin-only.</p></div>'
        return self._send(self._page("Diagnostics & Supportability", inner, sess), 200)
