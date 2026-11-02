from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings


class Base(DeclarativeBase):
    def __getattribute__(self, name):
        if not name.startswith("_"):
            state = object.__getattribute__(self, "__dict__")
            session = state.get("_document_session")
            if session is not None:
                mapper = type(self).__mapper__
                if name in mapper.relationships:
                    return session.related(self, mapper.relationships[name])
        return super().__getattribute__(name)


engine = None
if settings.DATABASE_BACKEND == "firestore":
    from app.core.firestore_store import FirestoreSession
    SessionLocal = FirestoreSession
else:
    if settings.DATABASE_URL.startswith("sqlite"):
        engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
