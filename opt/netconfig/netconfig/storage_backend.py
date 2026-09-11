"""Storage capability facade.

PH-2 keeps callers independent of the selected core backend. SQLite remains the
single-node development/default implementation; PostgreSQL is the distributed-
capable production implementation selected at Manager startup.
"""
from __future__ import annotations


class StorageBackend:
    def __init__(self, database):
        self.database = database

    @property
    def conn(self):
        return self.database.conn

    @property
    def dialect(self):
        return getattr(self.database, "dialect", "sqlite")

    @property
    def distributed_capable(self):
        return bool(getattr(self.database, "distributed_capable", False))

    def audit(self, *args, **kwargs):
        return self.database.audit(*args, **kwargs)

    def readiness(self):
        return self.database.readiness()

    def close(self):
        return self.database.close()
