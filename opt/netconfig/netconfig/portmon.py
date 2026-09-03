"""Zero-dependency TCP/UDP port status checks for 'system' devices.

Given a host and a port spec like "tcp/22, 80, udp/53, tcp/443", check each port
and report open / closed / filtered. Checks run in parallel with a short timeout.

TCP is reliable (connect succeeds = open, refused = closed, timeout = filtered).
UDP is best-effort by nature: a reply means open, an ICMP port-unreachable means
closed, and silence is reported as open|filtered (the usual UDP ambiguity).
"""
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor

# a few well-known ports for friendlier display
_WELL_KNOWN = {
    22: "ssh", 23: "telnet", 25: "smtp", 53: "dns", 80: "http", 88: "kerberos",
    110: "pop3", 123: "ntp", 143: "imap", 161: "snmp", 389: "ldap", 443: "https",
    445: "smb", 465: "smtps", 514: "syslog", 587: "submission", 636: "ldaps",
    993: "imaps", 995: "pop3s", 1433: "mssql", 1521: "oracle", 2049: "nfs",
    3306: "mysql", 3389: "rdp", 5432: "postgres", 5900: "vnc", 6379: "redis",
    8080: "http-alt", 8443: "https-alt", 9200: "elastic", 27017: "mongodb",
}


def service_name(port):
    return _WELL_KNOWN.get(port, "")


def parse_ports(spec, limit=64):
    """'tcp/22, 80, udp/53' -> [('tcp',22),('tcp',80),('udp',53)] (default tcp)."""
    out, seen = [], set()
    for tok in re.split(r"[,\s]+", (spec or "").strip()):
        if not tok:
            continue
        tok = tok.lower()
        proto = "tcp"
        p = tok
        if "/" in tok:
            proto, _, p = tok.partition("/")
        elif ":" in tok:
            proto, _, p = tok.partition(":")
        proto = "udp" if proto.startswith("u") else "tcp"
        try:
            pn = int(p)
        except ValueError:
            continue
        if 0 < pn < 65536 and (proto, pn) not in seen:
            seen.add((proto, pn))
            out.append((proto, pn))
        if len(out) >= limit:
            break
    return out


def check_tcp(host, port, timeout=1.5):
    t0 = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return {"state": "open", "ms": round((time.time() - t0) * 1000)}
    except socket.timeout:
        return {"state": "filtered", "ms": None}
    except ConnectionRefusedError:
        return {"state": "closed", "ms": round((time.time() - t0) * 1000)}
    except OSError as e:
        return {"state": "error", "ms": None, "detail": str(e)}
    finally:
        try:
            s.close()
        except OSError:
            pass


def check_udp(host, port, timeout=1.5):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(b"\x00", (host, port))
        try:
            s.recvfrom(1024)
            return {"state": "open", "ms": None}
        except socket.timeout:
            return {"state": "open|filtered", "ms": None}
        except ConnectionRefusedError:
            return {"state": "closed", "ms": None}
    except OSError as e:
        return {"state": "error", "ms": None, "detail": str(e)}
    finally:
        try:
            s.close()
        except OSError:
            pass


def check_ports(host, spec, timeout=1.5, workers=16):
    ports = parse_ports(spec)
    if not ports:
        return []
    results = []
    with ThreadPoolExecutor(max_workers=min(workers, len(ports))) as ex:
        futs = {}
        for proto, pn in ports:
            fn = check_tcp if proto == "tcp" else check_udp
            futs[ex.submit(fn, host, pn, timeout)] = (proto, pn)
        for fut, (proto, pn) in futs.items():
            try:
                r = fut.result()
            except Exception as e:  # pragma: no cover
                r = {"state": "error", "detail": str(e)}
            results.append({"proto": proto, "port": pn,
                            "service": service_name(pn), **r})
    results.sort(key=lambda x: (x["proto"], x["port"]))
    return results
