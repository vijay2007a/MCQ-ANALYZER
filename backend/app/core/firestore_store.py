"""Firestore document persistence for the application's existing domain services.

Only the query operations used by this project are supported; this is not a SQL
engine. Documents and query revisions live in a server-only namespace. Queries
push one equality predicate into Firestore and evaluate remaining filters and
sorting on the server. Collection revisions serialize overlapping writes and
prevent lost updates and duplicate submissions across function instances.
"""
from collections import namedtuple
from copy import deepcopy
from datetime import datetime, timezone
import operator
import re
import secrets

from fastapi import HTTPException
from sqlalchemy import inspect, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import elements, operators


class StorageConflict(HTTPException):
    def __init__(self):
        super().__init__(409, "Data changed during this request. Please retry.")


class FirestoreStore:
    def __init__(self, client):
        self.client = client
        self.root = client.collection("_quizmaster_backend").document("v1")

    def collection(self, table):
        return self.root.collection(table)

    def revision(self, table):
        snap = self.root.collection("_revisions").document(table).get()
        return (snap.to_dict() or {}).get("version", 0)

    def read(self, table, key):
        snap = self.collection(table).document(str(key)).get()
        return snap.to_dict() if snap.exists else None

    def scan(self, table, equality=None):
        from google.cloud.firestore_v1.base_query import FieldFilter
        query = self.collection(table)
        if equality:
            query = query.where(filter=FieldFilter(equality[0], "==", equality[1]))
        return [snap.to_dict() for snap in query.stream()]

    def commit(self, revisions, changes):
        from google.cloud import firestore
        transaction = self.client.transaction()

        @firestore.transactional
        def save(tx):
            # All reads precede all writes, as required by Firestore transactions.
            for table, expected in revisions.items():
                ref = self.root.collection("_revisions").document(table)
                snap = ref.get(transaction=tx)
                if (snap.to_dict() or {}).get("version", 0) != expected:
                    raise StorageConflict()
            touched = set()
            for (table, key), data in changes.items():
                touched.add(table)
                ref = self.collection(table).document(str(key))
                if data is None:
                    tx.delete(ref)
                else:
                    tx.set(ref, data)
            for table in touched:
                tx.set(self.root.collection("_revisions").document(table), {"version": revisions[table] + 1})
        save(transaction)

    def ping(self):
        self.root.get()


def _value(expr, context):
    if isinstance(expr, elements.BindParameter):
        return expr.value
    if isinstance(expr, elements.Grouping):
        return _value(expr.element, context)
    if isinstance(expr, elements.True_):
        return True
    if isinstance(expr, elements.False_):
        return False
    if isinstance(expr, elements.Null):
        return None
    if isinstance(expr, elements.BooleanClauseList):
        values = [_value(item, context) for item in expr.clauses]
        return all(values) if expr.operator is operators.and_ else any(values)
    if isinstance(expr, elements.BinaryExpression):
        left, right = _value(expr.left, context), _value(expr.right, context)
        op = expr.operator
        if op is operators.in_op:
            return left in right
        if op is operators.not_in_op:
            return left not in right
        if op in (operators.ilike_op, operators.like_op):
            if left is None:
                return False
            pattern = ''.join('.*' if c == '%' else '.' if c == '_' else re.escape(c) for c in right)
            return re.fullmatch(pattern, str(left), re.I if op is operators.ilike_op else 0) is not None
        ops = {operators.eq: operator.eq, operators.ne: operator.ne, operators.lt: operator.lt,
               operators.le: operator.le, operators.gt: operator.gt, operators.ge: operator.ge,
               operators.is_: operator.is_, operators.is_not: operator.is_not}
        if op not in ops:
            raise NotImplementedError(f"Unsupported document filter: {op}")
        if left is None or right is None:
            return ops[op](left, right) if op in (operators.eq, operators.ne, operators.is_, operators.is_not) else False
        if isinstance(left, datetime) and isinstance(right, datetime):
            left = left.replace(tzinfo=timezone.utc) if left.tzinfo is None else left
            right = right.replace(tzinfo=timezone.utc) if right.tzinfo is None else right
        return ops[op](left, right)
    if hasattr(expr, "table") and hasattr(expr, "key"):
        obj = context.get(expr.table.name)
        return getattr(obj, expr.key, None) if obj else None
    raise NotImplementedError(f"Unsupported document expression: {type(expr).__name__}")


class DocumentQuery:
    def __init__(self, session, entity):
        self.session, self.entity = session, entity
        self.model = entity if isinstance(entity, type) else entity.class_
        self.filters, self.sorts, self.joins = [], [], []
        self.skip, self.take = 0, None

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def order_by(self, *sorts):
        self.sorts.extend(sorts)
        return self

    def join(self, model, condition):
        self.joins.append((model, condition))
        return self

    def offset(self, count):
        self.skip = count
        return self

    def limit(self, count):
        self.take = count
        return self

    def with_for_update(self):
        # The unit of work validates read revisions atomically at commit.
        return self

    def _rows(self):
        table = self.model.__tablename__
        equality = None
        for expr in self.filters:
            if isinstance(expr, elements.BinaryExpression) and expr.operator is operators.eq:
                if getattr(getattr(expr.left, "table", None), "name", None) == table and isinstance(expr.right, elements.BindParameter):
                    equality = (expr.left.key, expr.right.value)
                    if equality[0] == "id":
                        break
        rows = self.session.rows(self.model, equality)
        contexts = [{table: row} for row in rows]
        for target, condition in self.joins:
            joined = []
            for context in contexts:
                # Existing joins connect quiz_id to quizzes.id.
                if getattr(getattr(condition.right, "table", None), "name", None) == target.__tablename__:
                    candidates = self.session.rows(target, (condition.right.key, _value(condition.left, context)))
                else:
                    candidates = self.session.rows(target)
                for row in candidates:
                    combined = {**context, target.__tablename__: row}
                    if _value(condition, combined):
                        joined.append(combined)
            contexts = joined
        contexts = [ctx for ctx in contexts if all(_value(expr, ctx) for expr in self.filters)]
        for sort in reversed(self.sorts):
            reverse = isinstance(sort, elements.UnaryExpression) and sort.modifier is operators.desc_op
            expr = sort.element if isinstance(sort, elements.UnaryExpression) else sort
            def _sort_val(ctx, e=expr):
                v = _value(e, ctx)
                if isinstance(v, datetime) and v.tzinfo is None:
                    v = v.replace(tzinfo=timezone.utc)
                return (v is not None, v)
            contexts.sort(key=_sort_val, reverse=reverse)
        return [ctx[table] for ctx in contexts]

    def all(self):
        rows = self._rows()[self.skip:]
        if self.take is not None:
            rows = rows[:self.take]
        if not isinstance(self.entity, type):
            Row = namedtuple("Row", [self.entity.key])
            return [Row(getattr(row, self.entity.key)) for row in rows]
        return rows

    def first(self):
        rows = self.all()
        return rows[0] if rows else None

    def one(self):
        rows = self.all()
        if len(rows) != 1:
            raise ValueError("Expected exactly one record")
        return rows[0]

    def count(self):
        return len(self._rows())

    def update(self, values):
        rows = self._rows()
        for row in rows:
            for key, value in values.items():
                setattr(row, key if isinstance(key, str) else key.key, value)
        return len(rows)

    def delete(self, synchronize_session=False):
        rows = self._rows()
        for row in rows:
            self.session.delete(row)
        return len(rows)


class FirestoreSession:
    def __init__(self, store=None):
        if store is None:
            from app.core.firebase import firestore_client
            store = FirestoreStore(firestore_client())
        self.store = store
        self.objects, self.originals, self.revisions = {}, {}, {}
        self.deleted = set()

    def _observe(self, table):
        if table not in self.revisions:
            self.revisions[table] = self.store.revision(table)

    def _data(self, obj):
        return {column.key: deepcopy(getattr(obj, column.key)) for column in inspect(type(obj)).columns}

    def _load(self, model, data):
        key = (model.__tablename__, data["id"])
        if key not in self.objects:
            obj = model(**data)
            obj._document_session = self
            self.objects[key] = obj
            self.originals[key] = deepcopy(data)
        return self.objects[key]

    def rows(self, model, equality=None):
        table = model.__tablename__
        self._observe(table)
        if equality and equality[0] == "id":
            data = self.store.read(table, equality[1])
            fetched = [data] if data else []
        else:
            fetched = self.store.scan(table, equality)
        rows = {data["id"]: self._load(model, data) for data in fetched}
        # Include local additions/changes and exclude pending deletions.
        for (name, key), obj in self.objects.items():
            if name == table:
                rows[key] = obj
        return [obj for key, obj in rows.items() if (table, key) not in self.deleted
                and (not equality or getattr(obj, equality[0]) == equality[1])]

    def query(self, entity):
        return DocumentQuery(self, entity)

    def get(self, model, key):
        return self.query(model).filter(model.id == key).first()

    def add(self, obj):
        mapper = inspect(type(obj))
        for column in mapper.columns:
            if getattr(obj, column.key) is None and column.default is not None:
                default = column.default
                setattr(obj, column.key, default.arg(None) if default.is_callable else deepcopy(default.arg))
        if obj.id is None:
            obj.id = secrets.randbelow(2**53 - 1) + 1
        key = (obj.__tablename__, obj.id)
        self._observe(key[0])
        if key not in self.objects:
            if self.store.read(*key) is not None:
                raise StorageConflict()
            self.originals[key] = None
        obj._document_session = self
        self.objects[key] = obj

    def add_all(self, objects):
        for obj in objects:
            self.add(obj)

    def related(self, obj, relationship):
        query = self.query(relationship.mapper.class_)
        for local, remote in relationship.local_remote_pairs:
            query.filter(getattr(relationship.mapper.class_, remote.key) == getattr(obj, local.key))
        if relationship.order_by is not False:
            query.order_by(*relationship.order_by)
        return query.all() if relationship.uselist else query.first()

    def delete(self, obj):
        key = (obj.__tablename__, obj.id)
        if key in self.deleted:
            return
        self.deleted.add(key)
        for relation in inspect(type(obj)).relationships:
            if "delete" in relation.cascade:
                values = self.related(obj, relation)
                for value in values if relation.uselist else ([values] if values else []):
                    self.delete(value)

    def flush(self):
        # Defaults/IDs are assigned on add; writes stay pending until commit.
        for key, obj in list(self.objects.items()):
            if key in self.deleted:
                continue
            for column in inspect(type(obj)).columns:
                if not column.nullable and getattr(obj, column.key) is None:
                    raise IntegrityError(None, None, ValueError(f"Missing {key[0]}.{column.key}"))

    def commit(self):
        self.flush()
        changes = {}
        for key, obj in list(self.objects.items()):
            data = None if key in self.deleted else self._data(obj)
            if data != self.originals.get(key):
                changes[key] = data
        if not changes:
            return
        # Enforce existing model constraints against the current collection. The
        # revision check makes this validation atomic with concurrent writers.
        models = {type(self.objects[key]) for key in changes}
        for model in models:
            rows = self.rows(model)
            constraints = [list(c.columns.keys()) for c in model.__table__.constraints if isinstance(c, UniqueConstraint)]
            for fields in constraints:
                seen = set()
                for row in rows:
                    values = tuple(getattr(row, field) for field in fields)
                    if None in values:
                        continue
                    if values in seen:
                        raise IntegrityError(None, None, ValueError("Duplicate document key"))
                    seen.add(values)
            for row in rows:
                if (row.__tablename__, row.id) not in changes:
                    continue
                for column in inspect(model).columns:
                    for foreign in column.foreign_keys:
                        value = getattr(row, column.key)
                        if value is not None:
                            from app.core.database import Base
                            target = next(m.class_ for m in Base.registry.mappers if m.local_table.name == foreign.column.table.name)
                            if self.get(target, value) is None:
                                raise IntegrityError(None, None, ValueError("Missing referenced document"))
        self.store.commit(self.revisions, changes)
        # Keep observed objects and revisions together, so a later commit in the
        # same request cannot overwrite an intervening request's newer values.
        for table in {key[0] for key in changes}:
            self.revisions[table] += 1
        for key, data in changes.items():
            if data is None:
                self.objects.pop(key, None)
                self.originals.pop(key, None)
            else:
                self.originals[key] = deepcopy(data)
        self.deleted.clear()

    def refresh(self, obj):
        # A committed object already contains exactly the persisted values.
        pass

    def rollback(self):
        for key, original in list(self.originals.items()):
            if original is not None:
                for name, value in original.items():
                    setattr(self.objects[key], name, deepcopy(value))
            else:
                self.objects.pop(key, None)
        self.deleted.clear()

    def close(self):
        self.rollback()

    def ping(self):
        self.store.ping()
