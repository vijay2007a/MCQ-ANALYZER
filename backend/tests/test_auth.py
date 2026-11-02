def test_admin_login_success(client, test_admin):
    response = client.post(
        "/api/admin/auth/login",
        json={"email": "admin@test.com", "password": "AdminSecret123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "ADMIN"
    assert data["email"] == "admin@test.com"


def test_admin_login_invalid_password(client, test_admin):
    response = client.post(
        "/api/admin/auth/login",
        json={"email": "admin@test.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["message"]


def test_admin_login_nonexistent_user(client):
    response = client.post(
        "/api/admin/auth/login",
        json={"email": "nobody@test.com", "password": "SomePassword123!"},
    )
    assert response.status_code == 401


def test_admin_profile_me(client, admin_headers):
    response = client.get("/api/admin/auth/me", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "admin@test.com"
    assert data["role"] == "ADMIN"
    assert data["is_active"] is True


def test_admin_unauthorized_access(client):
    response = client.get("/api/admin/auth/me")
    assert response.status_code == 401


def test_admin_change_password(client, admin_headers):
    response = client.post(
        "/api/admin/auth/change-password",
        headers=admin_headers,
        json={"current_password": "AdminSecret123!", "new_password": "NewAdminSecret456!"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Password updated successfully"

    # Verify login with new password
    login_resp = client.post(
        "/api/admin/auth/login",
        json={"email": "admin@test.com", "password": "NewAdminSecret456!"},
    )
    assert login_resp.status_code == 200


def test_firebase_cannot_grant_admin_access(client, test_admin, db):
    from app.models.admin import Admin
    for email in ["admin@test.com", "stranger@test.com"]:
        response = client.post("/api/admin/auth/firebase-login", json={
            "email": email, "uid": "attacker-chosen", "id_token": "unverified"
        })
        assert response.status_code == 403
        assert "access_token" not in response.json()
    assert db.query(Admin).filter(Admin.email == "stranger@test.com").first() is None


def test_legacy_admin_tokens_are_rejected(client, test_admin):
    import jwt
    from app.core.config import settings
    token = jwt.encode({"sub": str(test_admin.id), "role": "ADMIN", "type": "access"},
                       settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    response = client.get("/api/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_admin_lockdown_provisions_account_and_preserves_password_changes(db, test_admin, monkeypatch):
    from app.core import database
    from app.core.security import hash_password, verify_password
    from app.main import _ensure_default_admins
    from app.models.admin import Admin
    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    legacy_id = test_admin.id
    _ensure_default_admins()
    admin = db.query(Admin).filter(Admin.email == "admin123@gmail.com").one()
    assert admin.is_active
    assert verify_password("12345678", admin.password_hash)
    assert not db.get(Admin, legacy_id).is_active
    admin.password_hash = hash_password("ChangedPassword123!")
    db.commit()
    _ensure_default_admins()
    admin = db.query(Admin).filter(Admin.email == "admin123@gmail.com").one()
    assert verify_password("ChangedPassword123!", admin.password_hash)
