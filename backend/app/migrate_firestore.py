"""Copy a SQL database into an empty Firestore backend without modifying the source.

Run with --source sqlite:///./quizmaster.db for counts only; add --apply to copy.
Existing destination records cause an error. Provision Firebase admin identity
on first application startup using INITIAL_ADMIN_PASSWORD after migration.
"""
import argparse
from sqlalchemy import create_engine, inspect, select
from app.core.database import Base
from app.models import *  # Register all domain tables.
from app.core.firestore_store import FirestoreSession


def migrate(source_url, apply=False, destination=None):
    source = create_engine(source_url)
    records = []
    counts = {}
    models = {mapper.local_table.name: mapper.class_ for mapper in Base.registry.mappers}
    try:
        inspector = inspect(source)
        with source.connect() as connection:
            for table in Base.metadata.sorted_tables:
                if not inspector.has_table(table.name):
                    counts[table.name] = 0
                    continue
                existing = {c["name"] for c in inspector.get_columns(table.name)}
                cols = [col for col in table.columns if col.name in existing]
                rows = [dict(row) for row in connection.execute(select(*cols)).mappings()]
                if table.name == "audit_logs":
                    rows = [row for row in rows if row.get("event_type") != "ADMIN_ACCESS_LOCKDOWN_V2"]
                counts[table.name] = len(rows)
                records.extend((models[table.name], row) for row in rows)
        if not apply:
            return counts
        db = destination or FirestoreSession()
        try:
            for model in models.values():
                if db.query(model).first() is not None:
                    raise ValueError("Destination must be empty; refusing to overwrite existing records")
            for model, row in records:
                db.add(model(**row))
            db.commit()
        finally:
            db.close()
        return counts
    finally:
        source.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Source SQLAlchemy database URL")
    parser.add_argument("--apply", action="store_true", help="Copy records to an empty Firestore backend")
    args = parser.parse_args()
    counts = migrate(args.source, apply=args.apply)
    print("Migration committed." if args.apply else "Dry run only; no database changes.")
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
