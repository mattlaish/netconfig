"""Thin storage capability boundary for future full PostgreSQL migration.

The existing Database remains the production implementation today. New callers
can depend on this protocol-shaped adapter instead of sqlite3 details.
"""
from __future__ import annotations


class StorageBackend:
    def __init__(self, database):
        self.database = database

    @property
    def conn(self):
        return self.database.conn

    def audit(self, *args, **kwargs):
        return self.database.audit(*args, **kwargs)

    def close(self):
        return self.database.close()
