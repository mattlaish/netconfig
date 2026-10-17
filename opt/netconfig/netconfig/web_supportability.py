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
            '<div class="panel"><h2>NetConfig Service Status</h2>'
            '<p class=muted>Shows current NetConfig service information. Opening this page does not poll devices or change cluster state.</p>'
            f'<pre>{snapshot}</pre></div>'
        )
        if _can(sess["role"], "settings"):
            rows = [
                f'<tr><td>{html.escape(item["name"])}</td><td>{item["size"]}</td>'
                f'<td><a href="/debug-download?name={urllib.parse.quote(item["name"], safe="")}">Download</a>'
                f'<form method=post action="/debug-verify">{self._csrf_field()}'
                f'<input type=hidden name=name value="{html.escape(item["name"])}">'
                '<button class=ghost>Verify signature / trust</button></form></td></tr>'
                for item in DebugBundle(self.manager).list_bundles()
            ]
            devices = ''.join(
                f'<option value="{html.escape(dev["name"])}">{html.escape(dev["name"])}</option>'
                for dev in self.manager.inv.all())
            inner += (
                '<div class="panel"><h2>Diagnostic Support Bundles</h2>'
                '<p class=muted>Admin-only because bundles can contain sensitive operational evidence.</p>'
                f'<form method=post action="/debug-create">{self._csrf_field()}'
                '<input type=hidden name=mode value=full>'
                '<label><input type=checkbox name=require_signature value=1> Require signature for this bundle</label>'
                '<button>Create support bundle</button></form>'
                '<h3>Per-device capture</h3><p class=muted>Captures stored inventory, topology, drift and trace metadata; '
                'does not poll or change the device.</p>'
                f'<form method=post action="/debug-create">{self._csrf_field()}'
                '<input type=hidden name=mode value=device>'
                f'<label>Device</label><select name=device required>{devices}</select>'
                '<label><input type=checkbox name=require_signature value=1> Require signature for this capture</label>'
                '<button>Create device capture</button></form>'
                '<table><tr><th>Bundle</th><th>Size</th><th></th></tr>'
                + (''.join(rows) or '<tr><td colspan=3 class=muted>No bundles</td></tr>')
                + '</table><h3>Clean up old bundles</h3>'
                '<p class=muted>Removes older archives from the managed support-bundle directory. Download needed archives first.</p>'
                '<form method=post action="/debug-cleanup" data-confirm="Permanently remove older support bundles?">'
                f'{self._csrf_field()}<label>Keep newest bundles (minimum 1)</label>'
                f'<input type=number name=keep min=1 max=10000 value="{int(self.manager.settings.get("debug_bundle_keep", 10))}">'
                '<button class=danger>Clean up older bundles</button></form></div>'
            )
            inner += self._signing_status_panel()
            inner += '<p><a href="/settings?section=evidence">Edit evidence signing policy</a> · <a href="/traces">Protocol traces</a></p>'
        else:
            inner += '<div class="panel"><p class=muted>Support-bundle creation and download are admin-only.</p></div>'
        return self._send(self._page("Diagnostics & Support", inner, sess), 200)
