import pytest
from pydantic import ValidationError
from app.core.config import Settings


@pytest.mark.parametrize("url", [None, "", "sqlite:///./quizmaster.db", "sqlite:////tmp/quizmaster.db"])
def test_vercel_rejects_temporary_database(monkeypatch, url):
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(ValidationError, match="persistent PostgreSQL"):
        Settings(_env_file=None, DATABASE_URL=url)


def test_vercel_accepts_postgres(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    url = "postgresql://user:password@db.example/quiz?sslmode=require"
    assert Settings(_env_file=None, DATABASE_URL=url).DATABASE_URL == url


def test_local_development_keeps_sqlite(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    assert Settings(_env_file=None, DATABASE_URL=None).DATABASE_URL == "sqlite:///./quizmaster.db"
