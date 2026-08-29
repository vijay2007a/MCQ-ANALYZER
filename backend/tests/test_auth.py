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


def test_admin_firebase_login_existing_and_new(client, test_admin):
    # Test for existing admin
    resp = client.post(
        "/api/admin/auth/firebase-login",
        json={"email": "admin@test.com", "uid": "firebase_uid_123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["email"] == "admin@test.com"

    # Test auto-provisioning new admin from Firebase auth
    resp2 = client.post(
        "/api/admin/auth/firebase-login",
        json={"email": "firebase_admin@test.com", "uid": "firebase_uid_456"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert "access_token" in data2
    assert data2["email"] == "firebase_admin@test.com"
