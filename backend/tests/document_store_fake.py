"""In-memory document transport for deterministic Firestore unit-of-work tests."""
from copy import deepcopy
from threading import RLock
from app.core.firestore_store import StorageConflict


class MemoryDocumentStore:
    def __init__(self):
        self.data, self.versions = {}, {}
        self.lock = RLock()

    def revision(self, table):
        with self.lock:
            return self.versions.get(table, 0)

    def read(self, table, key):
        with self.lock:
            return deepcopy(self.data.get((table, key)))

    def scan(self, table, equality=None):
        with self.lock:
            return [deepcopy(row) for (name, _), row in self.data.items()
                    if name == table and (not equality or row[equality[0]] == equality[1])]

    def commit(self, revisions, changes):
        with self.lock:
            if any(self.versions.get(table, 0) != expected for table, expected in revisions.items()):
                raise StorageConflict()
            for key, value in changes.items():
                if value is None:
                    self.data.pop(key, None)
                else:
                    self.data[key] = deepcopy(value)
            for table in {key[0] for key in changes}:
                self.versions[table] = self.versions.get(table, 0) + 1

    def ping(self):
        pass
