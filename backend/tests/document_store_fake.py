"""In-memory document transport for deterministic Firestore unit-of-work tests."""
from copy import deepcopy
from threading import RLock
from sqlalchemy.exc import IntegrityError
from app.core.firestore_store import StorageConflict, normalize


class MemoryDocumentStore:
    def __init__(self):
        self.data, self.unique = {}, {}
        self.lock = RLock()
        self.commits = 0

    def read(self, table, key):
        with self.lock:
            return deepcopy(self.data.get((table, key)))

    def scan(self, table, equality=None):
        with self.lock:
            return [deepcopy(row) for (name, _), row in self.data.items()
                    if name == table and (not equality or row[equality[0]] == equality[1])]

    def commit(self, changes, expected, claims, releases):
        with self.lock:
            for key in changes:
                if normalize(self.data.get(key)) != normalize(expected[key]):
                    raise StorageConflict()
            for uid, allowed in claims.items():
                owner = self.unique.get(uid)
                if owner is not None and owner not in allowed:
                    raise IntegrityError(None, None, ValueError("Duplicate document key"))
            for key, value in changes.items():
                if value is None:
                    self.data.pop(key, None)
                else:
                    self.data[key] = deepcopy(value)
            for uid in releases:
                self.unique.pop(uid, None)
            for uid, allowed in claims.items():
                self.unique[uid] = allowed[0]
            self.commits += 1

    def ping(self):
        pass
