#!/usr/bin/env python3
"""R61 local synthetic scale/performance benchmark.

This benchmark exercises real NetConfig persistence, correlation, HTTP API/WebUI,
external-evidence and NetFlow parsing paths on an isolated temporary SQLite home.
Results are LOCAL_SYNTHETIC evidence only; they are never production capacity claims.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
import http.client
import json
import math
import os
from pathlib import Path
import resource
import shutil
import statistics
import struct
import sys
import tempfile
import threading
import time
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "opt/netconfig"))

from netconfig.apitokens import ApiTokens  # noqa: E402
from netconfig.manager import Manager  # noqa: E402
from netconfig.netflow import NetflowParser  # noqa: E402
from netconfig.web import Console, _Server  # noqa: E402
from netconfig import web  # noqa: E402


@dataclass(frozen=True)
class Profile:
    devices: int
    endpoints: int
    topology_edges: int
    routes: int
    syslog_events: int
    trap_events: int
    external_evidence: int
    incidents: int
    correlation_runs: int
    netflow_records: int
    api_requests: int
    webui_requests: int
    concurrent_operators: int
    fan_in_links: int
    overload_links: int


PROFILES = {
    "smoke": Profile(50, 250, 150, 300, 350, 250, 120, 30, 40, 3000, 40, 20, 8, 200, 2100),
    "standard": Profile(500, 5000, 2500, 5000, 10000, 5000, 3000, 500, 1000, 100000, 1000, 500, 32, 500, 2500),
}


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(x) for x in values)
    if len(ordered) == 1:
        return round(ordered[0], 6)
    rank = (len(ordered) - 1) * q
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return round(ordered[lo], 6)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo), 6)


def latency_summary(samples_ms: list[float]) -> dict:
    return {
        "count": len(samples_ms),
        "min_ms": round(min(samples_ms), 6) if samples_ms else 0.0,
        "mean_ms": round(statistics.fmean(samples_ms), 6) if samples_ms else 0.0,
        "p50_ms": percentile(samples_ms, 0.50),
        "p95_ms": percentile(samples_ms, 0.95),
        "p99_ms": percentile(samples_ms, 0.99),
        "max_ms": round(max(samples_ms), 6) if samples_ms else 0.0,
    }


def current_rss_bytes() -> int:
    status = Path("/proc/self/status")
    if status.is_file():
        for line in status.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value * (1 if sys.platform == "darwin" else 1024))


def tree_bytes(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def timed(count: int, fn) -> dict:
    cpu0 = time.process_time()
    wall0 = time.perf_counter()
    fn()
    wall = max(1e-9, time.perf_counter() - wall0)
    cpu = max(0.0, time.process_time() - cpu0)
    return {
        "count": count,
        "wall_seconds": round(wall, 6),
        "cpu_seconds": round(cpu, 6),
        "per_second": round(count / wall, 3),
    }


def _v5_packet(records: int) -> bytes:
    records = max(1, min(int(records), 30))
    data = bytearray(24 + 48 * records)
    struct.pack_into(">HH", data, 0, 5, records)
    for i in range(records):
        off = 24 + 48 * i
        struct.pack_into(">II", data, off, 0x0A000001 + i, 0x0A010001 + i)
        struct.pack_into(">II", data, off + 16, 10 + i, 1000 + i)
        struct.pack_into(">HH", data, off + 32, 10000 + i, 443)
        data[off + 38] = 6
    return bytes(data)


def _http_get(server, path: str, headers: dict[str, str]) -> tuple[int, int]:
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    conn.request("GET", path, headers=headers)
    response = conn.getresponse()
    body = response.read()
    status = response.status
    conn.close()
    return status, len(body)


def _seed_relational_data(manager: Manager, p: Profile, now: float) -> dict[str, dict]:
    result = {}

    def devices():
        for i in range(p.devices):
            manager.inv.upsert(name=f"r61-sw-{i:05d}", host=f"10.{(i // 254) % 250}.{(i // 32) % 254}.{(i % 254) + 1}", platform="generic", enabled=True)
    result["devices"] = timed(p.devices, devices)

    conn = manager.db.conn
    def endpoints():
        rows_mac, rows_fdb, rows_arp = [], [], []
        for i in range(p.endpoints):
            device = f"r61-sw-{i % p.devices:05d}"
            mac = f"02:61:{(i >> 16) & 255:02x}:{(i >> 8) & 255:02x}:{i & 255:02x}:01"
            port = f"Gi1/0/{(i % 48) + 1}"
            ip = f"172.{16 + ((i // 65000) % 16)}.{(i // 254) % 254}.{(i % 254) + 1}"
            rows_mac.append((device, mac, port, str((i % 48) + 1), port, now))
            rows_fdb.append((device, str((i % 64) + 1), str((i % 64) + 1), mac, str((i % 48) + 1), str((i % 48) + 1), port, "learned", "R61_SYNTHETIC", now))
            rows_arp.append((device, ip, mac, str((i % 48) + 1), now))
        conn.executemany("INSERT OR REPLACE INTO mac_table(device,mac,port,ifindex,ifdescr,ts) VALUES(?,?,?,?,?,?)", rows_mac)
        conn.executemany("INSERT OR REPLACE INTO vlan_fdb(device,vlan_id,fdb_id,mac,bridge_port,ifindex,ifdescr,status,source,ts) VALUES(?,?,?,?,?,?,?,?,?,?)", rows_fdb)
        conn.executemany("INSERT OR REPLACE INTO arp_entries(device,ip,mac,ifindex,ts) VALUES(?,?,?,?,?)", rows_arp)
        conn.commit()
    result["endpoints"] = timed(p.endpoints, endpoints)

    def topology():
        rows = []
        for i in range(p.topology_edges):
            a = i % p.devices
            b = (a + 1 + (i // max(1, p.devices))) % p.devices
            rows.append((f"r61-sw-{a:05d}", "lldp", f"Gi1/0/{(i % 48)+1}", str((i % 48)+1), f"r61-sw-{b:05d}", f"r61-sw-{b:05d}", f"chassis-{b}", f"Gi1/0/{((i+1)%48)+1}", "", "", 1, now))
        conn.executemany("INSERT OR REPLACE INTO l2_neighbors(device,protocol,local_port,local_port_num,neighbor_device,sys_name,chassis_id,port_id,port_desc,sys_desc,managed_neighbor,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
    result["topology_edges"] = timed(p.topology_edges, topology)

    def routes():
        rows = []
        for i in range(p.routes):
            device = f"r61-sw-{i % p.devices:05d}"
            prefix = f"10.{(i // 65536) % 255}.{(i // 256) % 256}.{i % 256}/32"
            next_device = f"r61-sw-{(i + 1) % p.devices:05d}"
            rows.append(("default", device, "default", prefix, "OSPF", "192.0.2.1", "Gi1/0/1", next_device, i % 100, 0, f"r61:route:{i}", "r61", now, now, 3600, "R61_SYNTHETIC", "r61-scale"))
        conn.executemany("INSERT INTO l3_route_observations(tenant_id,device,vrf,destination_prefix,protocol,next_hop,outgoing_interface,next_device,metric,terminal,evidence_ref,actor,observed_ts,received_ts,max_age_seconds,source_kind,collection_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
    result["routes"] = timed(p.routes, routes)
    return result


def run_benchmark(profile: Profile, home: Path) -> dict:
    home.mkdir(parents=True, exist_ok=True)
    before_bytes = tree_bytes(home)
    rss_before = current_rss_bytes()
    manager = Manager(str(home))
    server = None
    thread = None
    started = time.time()
    try:
        now = time.time()
        throughput = _seed_relational_data(manager, profile, now)

        def syslogs():
            for i in range(profile.syslog_events):
                manager.db.record_syslog(f"192.0.2.{(i % 250)+1}", f"r61 synthetic syslog {i}")
        throughput["syslog_events"] = timed(profile.syslog_events, syslogs)

        def traps():
            for i in range(profile.trap_events):
                manager.events.record(source_type="snmp_trap", source="r61", device=f"r61-sw-{i % profile.devices:05d}", event_type="link_state", severity="INFO", interface=f"Gi1/0/{(i%48)+1}", message=f"synthetic trap {i}", dedup_seconds=0, allow_suppression=False, evidence_ref=f"r61-trap:{i}", now=now + i / 1000.0)
        throughput["trap_events"] = timed(profile.trap_events, traps)

        token_store = ApiTokens(manager.db.conn)
        token_id, token_raw = token_store.create("r61-external", ["external:ingest"], created_by="r61", role="operator")
        token = token_store.verify(token_raw)
        manager.external_evidence.register_source("r61-siem", "SIEM", "R61 synthetic SIEM", ingest_token_id=token_id, rate_limit_per_minute=6000, actor="r61")
        ingest_lag_ms = []
        def external():
            for i in range(profile.external_evidence):
                received = now + 10 + i / 100.0
                source = received - (i % 20) / 1000.0
                envelope = {"schema_version":"1","source_event_id":f"r61-{i}","idempotency_key":f"r61-idem-{i}","event_type":"scale.event","source_ts":source,"severity":"INFO","entity_type":"device","entity_id":f"r61-sw-{i % profile.devices:05d}","summary":"R61 synthetic external evidence","metadata":{"profile":"local"},"payload":{"sequence":i}}
                manager.external_evidence.ingest("r61-siem", envelope, token, request_bytes=256, received_ts=received)
                ingest_lag_ms.append((received - source) * 1000.0)
        throughput["external_evidence"] = timed(profile.external_evidence, external)

        incidents = []
        def create_incidents():
            for i in range(profile.incidents):
                incidents.append(manager.incidents.create(f"R61 scale incident {i}", created_by="r61"))
        throughput["incidents"] = timed(profile.incidents, create_incidents)

        syslog_ids = [int(r["id"]) for r in manager.db.conn.execute("SELECT id FROM syslog_events ORDER BY id LIMIT ?", (profile.fan_in_links,)).fetchall()]
        def fan_in():
            if not incidents:
                return
            incident_id = incidents[0]["id"]
            rows = [(incident_id,"syslog",str(row_id),"r61",now,now,now,"{}","") for row_id in syslog_ids]
            manager.db.conn.executemany("INSERT OR IGNORE INTO incident_evidence_links(incident_id,source_type,source_ref,linked_by,linked_ts,source_ts,received_ts,source_clock_json,note) VALUES(?,?,?,?,?,?,?,?,?)", rows)
            manager.db.conn.commit()
        throughput["timeline_fan_in"] = timed(len(syslog_ids), fan_in)

        corr_ms = []
        for i in range(profile.correlation_runs):
            incident = incidents[i % len(incidents)]
            t0 = time.perf_counter()
            manager.correlation.correlate(incident["incident_key"], actor="r61")
            corr_ms.append((time.perf_counter() - t0) * 1000.0)
        correlation = latency_summary(corr_ms)
        wall_corr = max(1e-9, sum(corr_ms) / 1000.0)
        correlation["runs_per_minute_serial"] = round(profile.correlation_runs / wall_corr * 60.0, 3)

        parser = NetflowParser()
        packet = _v5_packet(30)
        loops = max(1, math.ceil(profile.netflow_records / 30))
        parsed = 0
        cpu0 = time.process_time(); wall0 = time.perf_counter()
        for _ in range(loops):
            parsed += len(parser.parse(packet, "192.0.2.1", now=now))
        wall_nf = max(1e-9, time.perf_counter() - wall0)
        netflow = {"records": parsed, "wall_seconds": round(wall_nf, 6), "cpu_seconds": round(time.process_time()-cpu0, 6), "records_per_second": round(parsed/wall_nf, 3), "protocol":"NetFlow v5 parser", "ipfix_v10_measured":False}

        # Deliberately exceed MC-10 timeline scan bound using fast direct fixture inserts.
        overload = manager.incidents.create("R61 overload bound probe", created_by="r61")
        base = int(manager.db.conn.execute("SELECT COALESCE(MAX(id),0) AS n FROM syslog_events").fetchone()["n"])
        overload_syslog = [(now + i/1000.0, "r61-overload", f"overload {i}") for i in range(profile.overload_links)]
        manager.db.conn.executemany("INSERT INTO syslog_events(ts,source,message) VALUES(?,?,?)", overload_syslog)
        overload_ids = [int(r["id"]) for r in manager.db.conn.execute("SELECT id FROM syslog_events WHERE id>? ORDER BY id", (base,)).fetchall()]
        manager.db.conn.executemany("INSERT INTO incident_evidence_links(incident_id,source_type,source_ref,linked_by,linked_ts,source_ts,received_ts,source_clock_json,note) VALUES(?,?,?,?,?,?,?,?,?)", [(overload["id"],"syslog",str(row_id),"r61",now,now,now,"{}","") for row_id in overload_ids])
        manager.db.conn.commit()
        t0=time.perf_counter(); overload_result=manager.correlation.correlate(overload["incident_key"],actor="r61"); overload_ms=(time.perf_counter()-t0)*1000.0
        overload_probe={"input_links":len(overload_ids),"duration_ms":round(overload_ms,6),"max_timeline_scan":overload_result["bounds"]["max_timeline_scan"],"max_facts":overload_result["bounds"]["max_facts"],"fact_evidence_truncated":bool(overload_result["fact_evidence_truncated"]),"facts_considered":int(overload_result["facts_considered"]),"bounded":bool(overload_result["fact_evidence_truncated"] and overload_result["facts_considered"] <= overload_result["bounds"]["max_facts"])}

        Console.manager = manager; Console.tls_enabled = False; Console.netflow = None
        original_log_message = Console.log_message
        Console.log_message = lambda self, fmt, *args: None
        server = _Server(("127.0.0.1", 0), Console)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        _, api_raw = token_store.create("r61-api-reader", ["analytics:read"], created_by="r61", role="viewer")
        api_headers={"Authorization":"Bearer "+api_raw}
        api_ms=[]
        for _ in range(profile.api_requests):
            t0=time.perf_counter(); status,_=_http_get(server,"/api/v1/operations/correlation/health?window_seconds=900",api_headers); api_ms.append((time.perf_counter()-t0)*1000.0)
            if status != 200: raise RuntimeError(f"API benchmark HTTP status {status}")

        session="r61-local-session"; web._SESSIONS[session]={"username":"viewer","role":"viewer","csrf":"r61","created":time.time()}
        web_headers={"Cookie":f"ncsid={session}"}; web_ms=[]
        for _ in range(profile.webui_requests):
            t0=time.perf_counter(); status,_=_http_get(server,"/dashboard",web_headers); web_ms.append((time.perf_counter()-t0)*1000.0)
            if status != 200: raise RuntimeError(f"WebUI benchmark HTTP status {status}")

        concurrent_ms=[]
        def one_request(_):
            t0=time.perf_counter(); status,_=_http_get(server,"/api/v1/operations/correlation/health?window_seconds=900",api_headers); dt=(time.perf_counter()-t0)*1000.0
            if status != 200: raise RuntimeError(f"concurrent API HTTP status {status}")
            return dt
        request_count=max(profile.concurrent_operators*4, profile.concurrent_operators)
        with ThreadPoolExecutor(max_workers=profile.concurrent_operators) as pool:
            concurrent_ms=list(pool.map(one_request, range(request_count)))

        db_counts={}
        for table in ("devices","mac_table","vlan_fdb","l2_neighbors","l3_route_observations","syslog_events","operational_events","external_events","incidents","incident_evidence_links","correlation_runs"):
            db_counts[table]=int(manager.db.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])

        after_bytes=tree_bytes(home)
        rss_after=current_rss_bytes()
        return {
            "evidence_class":"LOCAL_SYNTHETIC",
            "production_capacity_claim":False,
            "profile":asdict(profile),
            "started_unix":started,
            "finished_unix":time.time(),
            "throughput":throughput,
            "external_ingest_lag":latency_summary(ingest_lag_ms),
            "correlation":correlation,
            "netflow_parser":netflow,
            "api_latency":latency_summary(api_ms),
            "webui_dashboard_latency":latency_summary(web_ms),
            "concurrent_operator_api_latency":latency_summary(concurrent_ms),
            "concurrent_operators":profile.concurrent_operators,
            "mc10_overload_probe":overload_probe,
            "resource":{"rss_before_bytes":rss_before,"rss_after_bytes":rss_after,"rss_delta_bytes":rss_after-rss_before,"db_tree_before_bytes":before_bytes,"db_tree_after_bytes":after_bytes,"db_tree_growth_bytes":after_bytes-before_bytes},
            "database_counts":db_counts,
        }
    finally:
        if server is not None:
            server.shutdown(); server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        web._SESSIONS.pop("r61-local-session", None)
        if "original_log_message" in locals():
            Console.log_message = original_log_message
        manager.close()


def main(argv=None) -> int:
    ap=argparse.ArgumentParser(description="NetConfig R61 local synthetic scale benchmark")
    ap.add_argument("--profile", choices=sorted(PROFILES), default="smoke")
    ap.add_argument("--home")
    ap.add_argument("--output", required=True)
    args=ap.parse_args(argv)
    cleanup=None
    if args.home:
        home=Path(args.home).resolve()
    else:
        cleanup=tempfile.mkdtemp(prefix="netconfig-r61-")
        home=Path(cleanup)/"home"
    try:
        result=run_benchmark(PROFILES[args.profile],home)
        out=Path(args.output).resolve(); out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        print(json.dumps({"profile":args.profile,"api_p95_ms":result["api_latency"]["p95_ms"],"webui_p95_ms":result["webui_dashboard_latency"]["p95_ms"],"correlation_p95_ms":result["correlation"]["p95_ms"],"bounded":result["mc10_overload_probe"]["bounded"]},sort_keys=True))
        return 0 if result["mc10_overload_probe"]["bounded"] else 1
    finally:
        if cleanup:
            shutil.rmtree(cleanup,ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
