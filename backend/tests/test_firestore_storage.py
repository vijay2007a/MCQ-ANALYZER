import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.core.firestore_store import FirestoreSession, StorageConflict
from app.models.admin import Admin
from document_store_fake import MemoryDocumentStore


def test_documents_survive_new_sessions_and_rollback():
    store = MemoryDocumentStore()
    first = FirestoreSession(store)
    admin = Admin(email="persist@test.com", password_hash="hash")
    first.add(admin)
    first.commit()
    second = FirestoreSession(store)
    loaded = second.get(Admin, admin.id)
    assert loaded.email == "persist@test.com"
    loaded.email = "unsaved@test.com"
    second.rollback()
    assert FirestoreSession(store).get(Admin, admin.id).email == "persist@test.com"
    assert loaded.email == "persist@test.com"


def test_stale_updates_are_rejected_without_overwriting():
    store = MemoryDocumentStore()
    seed = FirestoreSession(store)
    obj = Admin(email="concurrent@test.com", password_hash="hash")
    seed.add(obj)
    seed.commit()
    first, second = FirestoreSession(store), FirestoreSession(store)
    a, b = first.get(Admin, obj.id), second.get(Admin, obj.id)
    a.password_hash, b.password_hash = "first", "second"
    first.commit()
    with pytest.raises(StorageConflict):
        second.commit()
    assert FirestoreSession(store).get(Admin, obj.id).password_hash == "first"


def test_unique_emails_and_new_record_races_are_rejected():
    store = MemoryDocumentStore()
    first, second = FirestoreSession(store), FirestoreSession(store)
    first.add(Admin(email="same@test.com", password_hash="one"))
    second.add(Admin(email="same@test.com", password_hash="two"))
    first.commit()
    with pytest.raises((IntegrityError, StorageConflict)):
        second.commit()
    assert FirestoreSession(store).query(Admin).count() == 1


@pytest.mark.parametrize("claims", [{}, {"admin": False}, {"admin": "true"}])
def test_firebase_non_admin_claims_are_denied(monkeypatch, claims):
    from firebase_admin import auth
    from app.core import firebase
    monkeypatch.setattr(firebase, "firebase_app", lambda: object())
    monkeypatch.setattr(auth, "verify_id_token", lambda *args, **kwargs: {"uid": "student", "email": "student@test.com", **claims})
    with pytest.raises(HTTPException) as exc:
        firebase.verify_admin_identity("token")
    assert exc.value.status_code == 403


def test_verified_admin_identity_ignores_browser_email(client, test_admin, monkeypatch):
    from app.core.config import settings
    from app.core import firebase
    monkeypatch.setattr(settings, "DATABASE_BACKEND", "firestore")
    monkeypatch.setattr(firebase, "verify_admin_identity", lambda token: {"uid": "trusted", "email": test_admin.email, "admin": True})
    response = client.post("/api/admin/auth/firebase-login", json={"email": "spoofed@test.com", "uid": "spoofed", "id_token": "verified-token"})
    assert response.status_code == 200
    assert response.json()["email"] == test_admin.email
    assert response.json()["access_token"] == "verified-token"
    assert client.get("/api/admin/auth/me", headers={"Authorization": "Bearer verified-token"}).status_code == 200
    assert client.post("/api/admin/auth/login", json={"email": test_admin.email, "password": "AdminSecret123!"}).status_code == 403


def test_firebase_claim_alone_cannot_create_admin(client, db, monkeypatch):
    from app.core.config import settings
    from app.core import firebase
    monkeypatch.setattr(settings, "DATABASE_BACKEND", "firestore")
    monkeypatch.setattr(firebase, "verify_admin_identity", lambda token: {"uid": "unknown", "email": "unknown@test.com", "admin": True})
    response = client.post("/api/admin/auth/firebase-login", json={"email": "unknown@test.com", "id_token": "token"})
    assert response.status_code == 403
    assert db.query(Admin).filter(Admin.email == "unknown@test.com").first() is None


def test_vercel_firestore_needs_no_sql_database(monkeypatch):
    from app.core.config import Settings
    monkeypatch.setenv("VERCEL", "1")
    config = Settings(_env_file=None, DATABASE_BACKEND="firestore", DATABASE_URL=None)
    assert config.DATABASE_BACKEND == "firestore"

def test_sql_migration_preserves_source_and_refuses_overwrite(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.database import Base
    from app.migrate_firestore import migrate
    source_url = f"sqlite:///{(tmp_path / 'source.db').as_posix()}"
    engine = create_engine(source_url)
    Base.metadata.create_all(engine)
    with Session(engine) as sql:
        sql.add(Admin(id=42, email="migrate@test.com", password_hash="hash"))
        sql.commit()
    store = MemoryDocumentStore()
    assert migrate(source_url)["admins"] == 1
    assert store.data == {}
    migrate(source_url, apply=True, destination=FirestoreSession(store))
    assert FirestoreSession(store).get(Admin, 42).email == "migrate@test.com"
    with pytest.raises(ValueError, match="Destination must be empty"):
        migrate(source_url, apply=True, destination=FirestoreSession(store))
    with Session(engine) as sql:
        assert sql.get(Admin, 42).email == "migrate@test.com"
    engine.dispose()


def test_firebase_revoked_token_verification_is_required(monkeypatch):
    from firebase_admin import auth
    from app.core import firebase
    monkeypatch.setattr(firebase, "firebase_app", lambda: "app")
    def reject(token, **kwargs):
        assert kwargs["check_revoked"] is True
        raise auth.RevokedIdTokenError("Revoked")
    monkeypatch.setattr(auth, "verify_id_token", reject)
    with pytest.raises(HTTPException) as exc:
        firebase.verify_admin_identity("revoked")
    assert exc.value.status_code == 401
