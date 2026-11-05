"""Endpoint CSV preserves filters, uncertainty and read-only access."""
import csv
import html
import io
import re
import urllib.parse

import pytest

from test_web_ux import console as _console_fixture
from test_evidence_repairs import MAC, seed_fdb
from netconfig.web_evidence import endpoints_csv

console = _console_fixture


def _read(text):
    return list(csv.DictReader(io.StringIO(text.removeprefix("\ufeff"))))


def test_viewer_can_export_filtered_multi_ip_evidence_without_io_or_writes(console, monkeypatch):
    seed_fdb(console.m)
    console.m.db.set_ip_neighbors("gateway", [
        {"ip": "192.0.2.10", "mac": MAC, "address_family": "ipv4", "source": "ARP"},
        {"ip": "2001:db8::10", "mac": MAC, "address_family": "ipv6", "source": "NDP"},
    ])
    def no_io(*args, **kwargs):
        raise AssertionError("export contacted a device")
    monkeypatch.setattr(console.m, "_connect", no_io)
    monkeypatch.setattr(console.m, "snmp_poll", no_io)
    before = console.m.db.conn.total_changes
    query = urllib.parse.urlencode({"format": "csv", "device": "sw", "q": MAC})
    code, headers, body = console.request("GET", "/endpoints?" + query, token=console.session("viewer"))
    assert code == 200
    assert headers["Content-Type"] == "text/csv; charset=utf-8"
    assert headers["Content-Disposition"] == 'attachment; filename="netconfig-endpoints.csv"'
    assert headers["Cache-Control"] == "no-store"
    assert body.startswith("\ufeff")
    rows = _read(body)
    assert {row["IP"] for row in rows} == {"192.0.2.10", "2001:db8::10"}
    assert all(row["MAC"] == MAC and row["Likely switch"] == "sw" and row["Likely port"] == "uplink" for row in rows)
    assert all(row["Result"] == "CANDIDATE" and row["Confidence"] == "LOW" for row in rows)
    assert all(row["Direct connection proven"] == "No" and row["VLAN"] == "10" for row in rows)
    assert console.m.db.conn.total_changes == before


@pytest.mark.parametrize("query", ["q=192.0.2.99", "device=unknown-switch"])
def test_export_applies_both_filters_and_returns_header_for_no_results(console, query):
    seed_fdb(console.m)
    code, _, body = console.request("GET", "/endpoints?format=csv&" + query, token=console.session())
    assert code == 200 and _read(body) == []
    assert "Likely switch" in body and MAC not in body


def test_export_button_keeps_current_filter_and_does_not_include_unknown_query_fields(console):
    seed_fdb(console.m)
    code, _, body = console.request("GET", "/endpoints?q=uplink&device=sw&unused=secret", token=console.session())
    assert code == 200 and "Export CSV" in body
    link = re.search(r'href="([^"]+)">Export CSV</a>', body).group(1)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(html.unescape(link)).query)
    assert query == {"format": ["csv"], "q": ["uplink"], "device": ["sw"]}


def test_anonymous_export_requires_sign_in(console):
    code, headers, _ = console.request("GET", "/endpoints?format=csv")
    assert code == 303 and headers["Location"].startswith("/login")
    assert "Content-Disposition" not in headers


def test_disabled_user_cannot_download_export(console):
    from netconfig.web_security_runtime import create_managed_session
    token, _ = create_managed_session(console.m.users.get("tester"))
    console.m.users.set_disabled("tester", True)
    code, headers, _ = console.request("GET", "/endpoints?format=csv", token=token)
    assert code == 303 and headers["Location"].startswith("/login")
    assert "Content-Disposition" not in headers


@pytest.mark.parametrize("status", ["AMBIGUOUS", "TRANSIT_ONLY", "STALE", "UNRESOLVED"])
def test_unresolved_location_is_never_guessed_and_all_evidence_types_are_retained(status):
    endpoint = {"mac": MAC, "status": status, "confidence": "LOW", "ipv4": [], "ipv6": [],
                "observed_location": {"device": "must-not-select", "ifdescr": "1"},
                "evidence_chain": {"fdb_candidates": [
                    {"device": "candidate", "ifdescr": "p1", "vlan_id": "10", "fresh": True, "transit": False},
                    {"device": "transit", "ifindex": "2", "fresh": True, "transit": True},
                    {"device": "old", "bridge_port": "3", "fresh": False, "transit": False},
                ]}}
    row = _read(endpoints_csv([endpoint]))[0]
    assert row["IP"] == "" and row["MAC"] == MAC
    assert row["Likely switch"] == row["Likely port"] == row["VLAN"] == ""
    assert row["Result"] == status and row["Direct connection proven"] == "No"
    assert row["IP mapping fresh"] == "Unknown"
    assert "candidate: p1 (VLAN 10)" in row["Candidate locations"]
    assert "transit: 2" in row["Transit observations"]
    assert "old: 3" in row["Outdated observations"]


@pytest.mark.parametrize("name", ["=HYPERLINK(1)", "+SUM(1)", "-1+2", "@SUM(1)", "  =1+1", "\t=1+1", "\r=1+1", "\n=1+1"])
def test_spreadsheet_formula_prefix_is_escaped_in_every_exported_location(name):
    endpoint = {"status": "CANDIDATE", "mac": MAC,
                "observed_location": {"device": name, "ifdescr": name, "vlan_id": name},
                "evidence_chain": {"fdb_candidates": [{"device": name, "ifdescr": name, "fresh": True}]}}
    row = _read(endpoints_csv([endpoint]))[0]
    for field in ("Likely switch", "Likely port", "VLAN", "Candidate locations"):
        assert row[field].startswith("'")


def test_unicode_quotes_commas_and_multiline_fields_roundtrip_and_duplicate_ips_are_not_repeated():
    name = '交換器,"North"\nFloor 2'
    endpoint = {"status": "CANDIDATE", "mac": MAC, "ipv4": ["192.0.2.1", "192.0.2.1"],
                "observed_location": {"device": name, "bridge_port": "0", "vlan_id": "0"},
                "ip_mapping_fresh": False}
    rows = _read(endpoints_csv([endpoint]))
    assert len(rows) == 1 and rows[0]["Likely switch"] == name
    assert rows[0]["Likely port"] == rows[0]["VLAN"] == "0"
    assert rows[0]["IP mapping fresh"] == "No"
