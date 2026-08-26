"""
config.py -- Filesystem layout and settings for a netconfig instance.

Everything lives under one data directory (default: ./netconfig-data, overridable
via $NETCONFIG_HOME). Kept as plain paths so the operator can see and back up
exactly what exists.
"""

import os
import json

DEFAULT_HOME = os.environ.get("NETCONFIG_HOME", os.path.abspath("netconfig-data"))


class Paths:
    def __init__(self, home=None):
        self.home = home or DEFAULT_HOME
        os.makedirs(self.home, exist_ok=True)

    @property
    def inventory_db(self):
        return os.path.join(self.home, "inventory.db")

    @property
    def vault_file(self):
        return os.path.join(self.home, "credentials.vault")

    @property
    def configs_dir(self):
        return os.path.join(self.home, "configs")

    @property
    def sessions_dir(self):
        return os.path.join(self.home, "sessions")

    @property
    def known_hosts(self):
        return os.path.join(self.home, "known_hosts")

    @property
    def settings_file(self):
        return os.path.join(self.home, "settings.json")


DEFAULT_SETTINGS = {
    "keep_versions": 30,
    "record_sessions": True,
    "scrub_sessions": False,
    "connect_timeout": 15,
    "command_timeout": 60,
    "host_key_policy": "accept-new",   # accept-new | yes | no
    "web_bind": "127.0.0.1",
    "web_port": 8778,
    "cookie_secure": False,            # add Secure to the session cookie; enable when
                                       # the console is fronted by the WAF for TLS
    "bulk_workers": 5,                 # concurrent SSH sessions for bulk jobs
    "snmp_timeout": 2.0,
    "snmp_port": 161,
    "snmp_poll_interval": 0,           # seconds; >0 enables the background poller
    "snmp_history_seconds": 1800,      # rolling window kept for live graphs
    "if_history_enabled": False,       # persist long interface throughput history
    "if_history_hours": 24,            # retention / default history window (hours)
    "if_history_bucket_seconds": 60,   # downsample bucket for 24h history reads
    # PostgreSQL connection for the history store (Settings -> Database). The
    # password is kept in the vault, never here. if_history_dsn is a legacy
    # single-string override; when set it wins over the discrete columns.
    "pg_host": "",
    "pg_port": 5432,
    "pg_dbname": "",
    "pg_user": "",
    "pg_sslmode": "prefer",            # disable|allow|prefer|require|verify-ca|verify-full
    "if_history_dsn": "",
    "backup_keep": 5,                  # config copies kept per device by the weekly backup
    "netflow_enabled": False,          # run the NetFlow collector in the console
    "netflow_port": 2055,              # UDP port to receive NetFlow exports
    "netflow_max_flows": 500,          # recent flows kept per exporter (in memory)
    "monitor_poll_interval": 0,        # seconds; 0 = off. Background port/http/tls polling
    "monitor_history_days": 7,         # how long to keep monitor history
    "smtp_enabled": False,             # send alert emails
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_starttls": True,
    "smtp_user": "",
    "smtp_from": "",
    "smtp_to": "",                     # comma-separated recipients
    "o365_enabled": False,             # use Microsoft Entra (O365) OAuth for SMTP
    "o365_tenant": "",                 # Entra tenant ID (GUID or domain)
    "o365_client_id": "",              # app (client) ID
    "o365_authority": "https://login.microsoftonline.com",
    "o365_scope": "https://outlook.office365.com/.default"
}


def load_settings(paths):
    s = dict(DEFAULT_SETTINGS)
    if os.path.exists(paths.settings_file):
        try:
            with open(paths.settings_file) as f:
                s.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return s


def save_settings(paths, settings):
    tmp = paths.settings_file + ".tmp"
    with open(tmp, "w") as f:
        json.dump(settings, f, indent=2)
    os.replace(tmp, paths.settings_file)
