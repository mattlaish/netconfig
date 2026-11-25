"""Safe, actionable PostgreSQL history failures shared by checks and collectors."""
import re
import socket


def failure_verdict(exc, stage, *, credential_state=""):
    # SQLSTATE is stable across server locales. libpq connection failures often
    # have no SQLSTATE, so recognize known transport/authentication messages too.
    state = str(getattr(exc, "sqlstate", "") or "")
    state = state if re.fullmatch(r"[0-9A-Z]{5}", state) else ""
    detail = str(exc).lower()
    code, summary, action = (
        "UNCLASSIFIED", "The database operation failed without a recognized cause.",
        "Run Test saved History + NetFlow and check the PostgreSQL server log at the same time.")
    if isinstance(exc, ImportError):
        code, summary, action = (
            "DRIVER_UNAVAILABLE", "The PostgreSQL driver could not be loaded.",
            "Install psycopg for the Python interpreter running NetConfig.")
    elif not state and ("no password supplied" in detail or "password is required" in detail):
        if credential_state == "locked":
            code, summary, action = (
                "VAULT_LOCKED", "PostgreSQL requires a password, but the Vault is locked.",
                "Unlock the Vault so background flow saving can use the saved History password.")
        else:
            code, summary, action = (
                "PASSWORD_MISSING", "PostgreSQL requires a password and none was supplied.",
                "Save the History database password in Settings → Database with the Vault unlocked.")
    elif state == "28P01" or (not state and "password authentication failed" in detail):
        code, summary, action = (
            "AUTHENTICATION_FAILED", "PostgreSQL rejected the History username or password.",
            "Check the saved History username and password in Settings → Database.")
    elif state == "28000" or (not state and (
            "no pg_hba.conf entry" in detail or ("role " in detail and "does not exist" in detail))):
        code, summary, action = (
            "ACCESS_REJECTED", "PostgreSQL rejected this client's authentication or access policy.",
            "Check the History username, pg_hba.conf rules and SSL mode for this NetConfig server.")
    elif state == "3D000" or (not state and "database " in detail and "does not exist" in detail):
        code, summary, action = (
            "DATABASE_MISSING", "The configured History database does not exist.",
            "Correct the saved database name or create that database on PostgreSQL.")
    elif state == "42501":
        code, summary, action = (
            "PERMISSION_DENIED", "The History account lacks permission for this operation.",
            "Grant the History account the required schema/table permissions, then run the saved History + NetFlow test.")
    elif state == "25006":
        code, summary, action = (
            "DATABASE_READ_ONLY", "The History database connection is read-only.",
            "Use a writable PostgreSQL primary and allow the History account to save and remove flow records.")
    elif state in {"42P01", "42703", "42804"}:
        code, summary, action = (
            "SCHEMA_NOT_READY", "The flow history table is missing or incompatible.",
            "Run Test saved History + NetFlow to prepare and verify the flow table.")
    elif state == "55P03":
        code, summary, action = (
            "LOCK_TIMEOUT", "The flow history operation could not obtain a database lock in time.",
            "Check blocking PostgreSQL transactions and retry after the lock is released.")
    elif state == "57014":
        code, summary, action = (
            "QUERY_CANCELLED", "PostgreSQL cancelled the operation, possibly because its time limit was reached.",
            "Check PostgreSQL query timeouts and server load.")
    elif state == "53100":
        code, summary, action = (
            "STORAGE_FULL", "PostgreSQL has run out of disk space.",
            "Free space on the PostgreSQL server and check its log.")
    elif state in {"53200", "53300", "53400"}:
        code, summary, action = (
            "SERVER_CAPACITY", "PostgreSQL reached a memory, connection or resource limit.",
            "Check PostgreSQL capacity and connection usage.")
    elif state in {"57P01", "57P02", "57P03"}:
        code, summary, action = (
            "SERVER_UNAVAILABLE", "PostgreSQL is shutting down, restarting or not accepting connections.",
            "Check the PostgreSQL service and wait for it to accept connections.")
    elif isinstance(exc, socket.gaierror) or any(text in detail for text in (
            "could not translate host name", "name or service not known", "getaddrinfo failed")):
        code, summary, action = (
            "DNS_FAILED", "The History database hostname could not be resolved.",
            "Check the saved database host and this server's DNS configuration.")
    elif any(text in detail for text in (
            "certificate verify failed", "root certificate file", "server does not support ssl",
            "ssl error: wrong version number", "ssl handshake", "tls handshake", "tlsv1 alert")):
        code, summary, action = (
            "TLS_FAILED", "The secure connection to History PostgreSQL failed.",
            "Check the saved SSL mode, server certificate and trusted CA certificates.")
    elif isinstance(exc, TimeoutError) or "timeout" in detail or "timed out" in detail:
        code, summary, action = (
            "CONNECTION_TIMEOUT", "The database operation timed out.",
            "Check the database host/port, network reachability and PostgreSQL load.")
    elif isinstance(exc, ConnectionRefusedError) or "connection refused" in detail:
        code, summary, action = (
            "CONNECTION_REFUSED", "The History database refused the connection.",
            "Check that PostgreSQL is running and listening on the saved host and port.")
    elif state.startswith("08") or isinstance(exc, ConnectionError) or any(text in detail for text in (
            "no route to host", "network is unreachable", "server closed the connection",
            "connection reset", "connection is closed", "connection is bad",
            "ssl connection has been closed unexpectedly")):
        code, summary, action = (
            "CONNECTION_FAILED", "The connection to History PostgreSQL could not be established or was interrupted.",
            "Check PostgreSQL availability, the saved host/port and the network path.")
    return {"code": code, "stage": stage, "summary": summary, "action": action, "sqlstate": state}


def verdict_text(verdict):
    state = verdict.get("sqlstate")
    evidence = f" SQLSTATE {state}." if state else ""
    return f'{verdict["summary"]} {verdict["action"]}{evidence}'
