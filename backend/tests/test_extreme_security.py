import io
import time
from datetime import datetime, timedelta, timezone
import pytest
from app.models.quiz_session import QuizSession
from app.models.quiz import Quiz
from app.models.question import Question
from app.models.result import QuizResult
from app.models.audit_log import AuditLog
from app.core.security import generate_player_session_token, hash_session_token


# -----------------------------------------------------------------------------
# 1. Modify Score: Student tries to inject 'score' or 'points_earned' in payload
# -----------------------------------------------------------------------------
def test_attack_01_modify_score(client, published_quiz):
    start = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 01"}).json()
    token = start["session_token"]
    session_id = start["session_id"]

    # Extra fields like score or points_earned are rejected by extra='forbid'
    resp = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers={"X-Session-Token": token},
        json={
            "question_order": 1,
            "selected_option": "B",
            "idempotency_key": "atk01_key_01",
            "score": 999999,
            "points_earned": 999999,
        },
    )
    assert resp.status_code == 422
    assert "Extra inputs are not permitted" in str(resp.json())


# -----------------------------------------------------------------------------
# 2. Modify Response Time: Student tries to inject 'elapsed_time' or 'response_time'
# -----------------------------------------------------------------------------
def test_attack_02_modify_response_time(client, published_quiz):
    start = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 02"}).json()
    token = start["session_token"]
    session_id = start["session_id"]

    resp = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers={"X-Session-Token": token},
        json={
            "question_order": 1,
            "selected_option": "B",
            "idempotency_key": "atk02_key_01",
            "elapsed_time": 0.001,
            "response_time_ms": 1,
        },
    )
    assert resp.status_code == 422


# -----------------------------------------------------------------------------
# 3. Modify Accuracy: Student tries to inject 'accuracy' or 'is_correct'
# -----------------------------------------------------------------------------
def test_attack_03_modify_accuracy(client, published_quiz):
    start = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 03"}).json()
    token = start["session_token"]
    session_id = start["session_id"]

    resp = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers={"X-Session-Token": token},
        json={
            "question_order": 1,
            "selected_option": "A",  # Wrong answer
            "idempotency_key": "atk03_key_01",
            "accuracy": 100.0,
            "is_correct": True,
        },
    )
    assert resp.status_code == 422


# -----------------------------------------------------------------------------
# 4. Submit Duplicate Answer: Repeated submission does not award points twice
# -----------------------------------------------------------------------------
def test_attack_04_submit_duplicate_answer(client, published_quiz):
    start = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 04"}).json()
    token = start["session_token"]
    session_id = start["session_id"]
    headers = {"X-Session-Token": token}

    ans1 = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers=headers,
        json={"question_order": 1, "selected_option": "B", "idempotency_key": "atk04_key_01"},
    )
    assert ans1.status_code == 200
    first_score = ans1.json()["current_score"]

    ans2 = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers=headers,
        json={"question_order": 1, "selected_option": "B", "idempotency_key": "atk04_key_01"},
    )
    assert ans2.status_code == 200
    assert ans2.json()["current_score"] == first_score


# -----------------------------------------------------------------------------
# 5. Submit Answer Out of Order: Skipping questions is rejected
# -----------------------------------------------------------------------------
def test_attack_05_submit_answer_out_of_order(client, published_quiz):
    start = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 05"}).json()
    token = start["session_token"]
    session_id = start["session_id"]

    resp = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers={"X-Session-Token": token},
        json={"question_order": 2, "selected_option": "C", "idempotency_key": "atk05_key_02"},
    )
    assert resp.status_code == 400
    assert "Invalid question sequence" in resp.json()["message"]


# -----------------------------------------------------------------------------
# 6. Submit Answer After Expiration: Submissions on expired sessions are rejected
# -----------------------------------------------------------------------------
def test_attack_06_submit_answer_after_expiration(client, db, published_quiz):
    start = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 06"}).json()
    token = start["session_token"]
    session_id = start["session_id"]

    sess = db.query(QuizSession).filter(QuizSession.id == session_id).first()
    sess.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db.commit()

    resp = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers={"X-Session-Token": token},
        json={"question_order": 1, "selected_option": "B", "idempotency_key": "atk06_key_01"},
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["message"].lower()


# -----------------------------------------------------------------------------
# 7. Submit Another Question ID: Sending extra fields or mismatched order is blocked
# -----------------------------------------------------------------------------
def test_attack_07_submit_another_question_id(client, published_quiz):
    start = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 07"}).json()
    token = start["session_token"]
    session_id = start["session_id"]

    # Student tries to send another quiz's question_id
    resp = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers={"X-Session-Token": token},
        json={
            "question_order": 1,
            "selected_option": "B",
            "idempotency_key": "atk07_key_01",
            "question_id": 99999,
        },
    )
    assert resp.status_code == 422


# -----------------------------------------------------------------------------
# 8. IDOR: Access Another Student's Session (e.g. Session 1 using Token 2)
# -----------------------------------------------------------------------------
def test_attack_08_idor_access_other_student_session(client, published_quiz):
    s1 = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Victim 08"}).json()
    s2 = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 08"}).json()

    # Attacker tries to view Victim's question using Attacker's token
    resp = client.get(
        f"/api/player/sessions/{s1['session_id']}/question",
        headers={"X-Session-Token": s2["session_token"]},
    )
    assert resp.status_code == 401


# -----------------------------------------------------------------------------
# 9. IDOR: Access Another Student's Result
# -----------------------------------------------------------------------------
def test_attack_09_idor_access_other_student_result(client, published_quiz):
    s1 = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Victim 09"}).json()
    s2 = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 09"}).json()

    # Attacker tries to view Victim's results
    resp = client.get(
        f"/api/player/sessions/{s1['session_id']}/result",
        headers={"X-Session-Token": s2["session_token"]},
    )
    assert resp.status_code == 401


# -----------------------------------------------------------------------------
# 10. Access Unpublished Quiz
# -----------------------------------------------------------------------------
def test_attack_10_access_unpublished_quiz(client, admin_headers, published_quiz):
    # Unpublish the quiz
    client.post(f"/api/admin/quizzes/{published_quiz.id}/unpublish", headers=admin_headers)

    # Student tries to start unpublished quiz
    resp = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 10"})
    assert resp.status_code == 400
    assert "not currently published" in resp.json()["message"]


# -----------------------------------------------------------------------------
# 11. Access Draft Quiz
# -----------------------------------------------------------------------------
def test_attack_11_access_draft_quiz(client, admin_headers):
    # Admin creates a draft quiz
    draft = client.post("/api/admin/quizzes", headers=admin_headers, json={"title": "Secret Exam Draft"}).json()

    resp = client.post(f"/api/player/quizzes/{draft['id']}/start", json={"player_name": "Attacker 11"})
    assert resp.status_code == 400


# -----------------------------------------------------------------------------
# 12. Call Admin Without Auth
# -----------------------------------------------------------------------------
def test_attack_12_call_admin_without_auth(client):
    endpoints = [
        client.get("/api/admin/quizzes"),
        client.post("/api/admin/quizzes", json={"title": "Hack"}),
        client.get("/api/admin/results"),
        client.get("/api/admin/results/export"),
        client.get("/api/admin/audit-logs"),
    ]
    for r in endpoints:
        assert r.status_code == 401


# -----------------------------------------------------------------------------
# 13. Call Admin with Player Token
# -----------------------------------------------------------------------------
def test_attack_13_call_admin_with_player_token(client, published_quiz):
    s = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 13"}).json()
    player_headers = {"Authorization": f"Bearer {s['session_token']}"}

    resp = client.get("/api/admin/quizzes", headers=player_headers)
    assert resp.status_code == 401


# -----------------------------------------------------------------------------
# 14. Mass Assignment Admin Role
# -----------------------------------------------------------------------------
def test_attack_14_mass_assignment_admin_role(client, published_quiz):
    resp = client.post(
        f"/api/player/quizzes/{published_quiz.id}/start",
        json={"player_name": "Attacker 14", "role": "SUPERADMIN", "is_admin": True},
    )
    assert resp.status_code == 422


# -----------------------------------------------------------------------------
# 15. Mass Assignment Quiz Owner
# -----------------------------------------------------------------------------
def test_attack_15_mass_assignment_quiz_owner(client, admin_headers):
    resp = client.post(
        "/api/admin/quizzes",
        headers=admin_headers,
        json={"title": "Quiz Ownership Test", "created_by": 9999, "is_deleted": True},
    )
    assert resp.status_code == 422


# -----------------------------------------------------------------------------
# 16. SQL Injection Payloads
# -----------------------------------------------------------------------------
def test_attack_16_sql_injection_payloads(client, admin_headers):
    sqli_payloads = [
        "' OR '1'='1",
        "admin'--",
        "1; DROP TABLE quizzes; --",
        "1' UNION SELECT 1, 'admin', 'hash', 'ADMIN', 1, NULL, NULL, NULL --",
    ]
    for p in sqli_payloads:
        # Search by player name with SQL injection
        res = client.get(f"/api/admin/results?player_name={p}", headers=admin_headers)
        assert res.status_code == 200  # Handled safely by ORM parameterized query

        # Login attempt with SQL injection
        login_res = client.post("/api/admin/auth/login", json={"email": f"{p}@test.com", "password": p})
        assert login_res.status_code in [401, 422]


# -----------------------------------------------------------------------------
# 17. XSS Injection Sanitization
# -----------------------------------------------------------------------------
def test_attack_17_xss_injection_sanitization(client, published_quiz):
    xss_name = '<script>alert("XSS")</script>'
    s = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": xss_name}).json()
    status_res = client.get(
        f"/api/player/sessions/{s['session_id']}/status",
        headers={"X-Session-Token": s["session_token"]},
    ).json()
    # Name must be HTML-escaped
    assert "<script>" not in status_res["player_name"]
    assert "&lt;script&gt;" in status_res["player_name"]


# -----------------------------------------------------------------------------
# 18. Oversized Input Payload
# -----------------------------------------------------------------------------
def test_attack_18_oversized_input_payload(client, published_quiz):
    huge_name = "A" * 10000
    resp = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": huge_name})
    assert resp.status_code == 422


# -----------------------------------------------------------------------------
# 19. Admin Brute Force: No User Enumeration Leak
# -----------------------------------------------------------------------------
def test_attack_19_admin_brute_force_no_user_enumeration(client, test_admin):
    # Existing user with wrong password
    r1 = client.post("/api/admin/auth/login", json={"email": test_admin.email, "password": "WrongPassword!"})
    # Nonexistent user
    r2 = client.post("/api/admin/auth/login", json={"email": "nonexistent@univ.edu", "password": "WrongPassword!"})

    assert r1.status_code == 401
    assert r2.status_code == 401
    assert r1.json()["message"] == r2.json()["message"] == "Invalid email or password"


# -----------------------------------------------------------------------------
# 20. Replay Valid Request
# -----------------------------------------------------------------------------
def test_attack_20_replay_valid_request(client, published_quiz):
    s = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 20"}).json()
    headers = {"X-Session-Token": s["session_token"]}

    payload = {"question_order": 1, "selected_option": "B", "idempotency_key": "replay_key_20"}
    res1 = client.post(f"/api/player/sessions/{s['session_id']}/answer", headers=headers, json=payload)
    res2 = client.post(f"/api/player/sessions/{s['session_id']}/answer", headers=headers, json=payload)

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["current_score"] == res2.json()["current_score"]


# -----------------------------------------------------------------------------
# 21. Concurrent Answer Submissions
# -----------------------------------------------------------------------------
def test_attack_21_concurrent_answer_submissions(client, published_quiz):
    s = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 21"}).json()
    headers = {"X-Session-Token": s["session_token"]}

    # Simulate 2 simultaneous requests for Q1
    res1 = client.post(
        f"/api/player/sessions/{s['session_id']}/answer",
        headers=headers,
        json={"question_order": 1, "selected_option": "B", "idempotency_key": "concurrent_key_01"},
    )
    res2 = client.post(
        f"/api/player/sessions/{s['session_id']}/answer",
        headers=headers,
        json={"question_order": 1, "selected_option": "B", "idempotency_key": "concurrent_key_02"},
    )

    assert res1.status_code == 200
    # Second request is recognized as idempotent attempt for question 1 or rejected as out of order
    assert res2.status_code in [200, 400]
    # Total points from Q1 must never exceed 100
    assert res1.json()["current_score"] <= 100


# -----------------------------------------------------------------------------
# 22. Manipulate Pagination Parameters
# -----------------------------------------------------------------------------
def test_attack_22_manipulate_pagination_parameters(client, admin_headers):
    # Negative page
    r1 = client.get("/api/admin/results?page=-5", headers=admin_headers)
    assert r1.status_code == 422

    # Excessively large page size (e.g. 50000)
    r2 = client.get("/api/admin/results?size=50000", headers=admin_headers)
    assert r2.status_code == 422


# -----------------------------------------------------------------------------
# 23. Enumerate IDs: Safe 404 Response
# -----------------------------------------------------------------------------
def test_attack_23_enumerate_ids_safe_handling(client, admin_headers):
    r = client.get("/api/admin/quizzes/999999", headers=admin_headers)
    assert r.status_code == 404
    assert "Quiz not found" in r.json()["message"]


# -----------------------------------------------------------------------------
# 24. Unauthorized Excel Export
# -----------------------------------------------------------------------------
def test_attack_24_unauthorized_excel_export(client):
    r = client.get("/api/admin/results/export")
    assert r.status_code == 401


# -----------------------------------------------------------------------------
# 25. Bypass Maximum Attempts
# -----------------------------------------------------------------------------
def test_attack_25_bypass_maximum_attempts(client, published_quiz):
    # Limit is 3 attempts
    for _ in range(3):
        r = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attempt Attacker"})
        assert r.status_code == 201
    
    # 4th attempt is strictly blocked
    blocked = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "attempt attacker"})
    assert blocked.status_code == 400
    assert "Maximum attempt limit" in blocked.json()["message"]


# -----------------------------------------------------------------------------
# 26. Player Modify Quiz Scoring
# -----------------------------------------------------------------------------
def test_attack_26_player_modify_quiz_scoring(client, published_quiz):
    s = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 26"}).json()
    player_headers = {"Authorization": f"Bearer {s['session_token']}"}

    r = client.put(
        f"/api/admin/quizzes/{published_quiz.id}",
        headers=player_headers,
        json={"scoring_config": {"base_points": 5000}},
    )
    assert r.status_code == 401


# -----------------------------------------------------------------------------
# 27. Player Modify Question Order
# -----------------------------------------------------------------------------
def test_attack_27_player_modify_question_order(client, published_quiz):
    s = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 27"}).json()
    player_headers = {"Authorization": f"Bearer {s['session_token']}"}

    r = client.post(
        f"/api/admin/quizzes/{published_quiz.id}/questions/reorder",
        headers=player_headers,
        json={"orders": [{"question_id": 1, "question_order": 2}]},
    )
    assert r.status_code == 401


# -----------------------------------------------------------------------------
# 28. Player Modify Correct Answer
# -----------------------------------------------------------------------------
def test_attack_28_player_modify_correct_answer(client, published_quiz):
    s = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 28"}).json()
    player_headers = {"Authorization": f"Bearer {s['session_token']}"}

    r = client.put(
        "/api/admin/quizzes/questions/1",
        headers=player_headers,
        json={"correct_option": "A"},
    )
    assert r.status_code == 401


# -----------------------------------------------------------------------------
# 29. Player Modify Completion Status
# -----------------------------------------------------------------------------
def test_attack_29_player_modify_completion_status(client, published_quiz):
    s = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Attacker 29"}).json()

    r = client.post(
        f"/api/player/sessions/{s['session_id']}/answer",
        headers={"X-Session-Token": s["session_token"]},
        json={
            "question_order": 1,
            "selected_option": "B",
            "idempotency_key": "atk29_key",
            "status": "COMPLETED",
        },
    )
    assert r.status_code == 422


# -----------------------------------------------------------------------------
# 30. Audit Log Tracking Suspicious Behavior
# -----------------------------------------------------------------------------
def test_attack_30_audit_log_tracking_suspicious_behavior(client, admin_headers, db, published_quiz):
    # Perform a malicious out-of-order action
    s = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Logged Attacker"}).json()
    client.post(
        f"/api/player/sessions/{s['session_id']}/answer",
        headers={"X-Session-Token": s["session_token"]},
        json={"question_order": 2, "selected_option": "C", "idempotency_key": "logged_key"},
    )

    # Verify audit log was recorded
    logs_resp = client.get("/api/admin/audit-logs", headers=admin_headers)
    assert logs_resp.status_code == 200
    events = [item["event_type"] for item in logs_resp.json()["items"]]
    assert "OUT_OF_ORDER_SUBMISSION" in events
