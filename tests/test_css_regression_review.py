import re
from pathlib import Path

from netconfig.web_ui import _CSS, _GRAPH_JS


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "opt/netconfig/netconfig/web.py"
WEB_UI = ROOT / "opt/netconfig/netconfig/web_ui.py"


def test_all_css_custom_properties_referenced_by_console_are_defined():
    defined = set(re.findall(r"(--[A-Za-z0-9_-]+)\s*:", _CSS))
    source = WEB.read_text(encoding="utf-8") + "\n" + WEB_UI.read_text(encoding="utf-8")
    used = set(re.findall(r"var\((--[A-Za-z0-9_-]+)", source))
    assert used - defined == set()


def test_dashboard_no_results_uses_hidden_attribute_not_persistent_display_none():
    source = WEB.read_text(encoding="utf-8")
    assert 'id="devnoresults" class="muted" hidden' in source
    assert 'style="display:none">No devices match your search.' not in source


def test_checkbox_and_radio_controls_are_not_forced_to_full_width():
    assert 'input[type="checkbox"],input[type="radio"]{width:auto;' in _CSS


def test_graph_runtime_markup_uses_theme_css_classes():
    assert "card.className='graph-card'" in _GRAPH_JS
    assert "head.className='graph-head'" in _GRAPH_JS
    assert 'graph-in-line' in _GRAPH_JS
    assert 'graph-out-line' in _GRAPH_JS
    assert 'background:#fff' not in _GRAPH_JS
    assert '#1E6641' not in _GRAPH_JS
    assert '#8A5A00' not in _GRAPH_JS


def test_mobile_header_can_wrap_operator_controls():
    assert '@media(max-width:760px)' in _CSS
    assert 'header{padding:12px 16px;flex-wrap:wrap}' in _CSS


def test_mobile_tables_scroll_inside_viewport_and_help_code_can_wrap():
    assert 'table{display:block;max-width:100%;overflow-x:auto;' in _CSS
    assert '.help code{white-space:normal!important;overflow-wrap:anywhere;word-break:break-word}' in _CSS


def test_dark_theme_neutral_and_error_tokens_do_not_use_light_only_hardcoded_colors():
    assert '.b-dim{background:var(--row-alt);color:var(--grey)}' in _CSS
    assert '.err{background:var(--red10);border:1px solid var(--red);' in _CSS
    assert '.vault-lock{background:var(--red10);border:1px solid var(--red);' in _CSS
