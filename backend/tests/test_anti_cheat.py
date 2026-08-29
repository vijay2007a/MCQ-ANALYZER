from datetime import datetime, timedelta, timezone
from app.models.quiz_session import QuizSession
from app.models.quiz import Quiz


def test_anti_cheat_out_of_order_submission_rejected(client, published_quiz):
    start_resp = client.post(
        f"/api/player/quizzes/{published_quiz.id}/start",
        json={"player_name": "Bob Trickster"},
    )
    session_id = start_resp.json()["session_id"]
    token = start_resp.json()["session_token"]
    headers = {"X-Session-Token": token}

    # Attempt to skip directly to question 2
    bad_resp = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers=headers,
        json={
            "question_order": 2,
            "selected_option": "C",
            "idempotency_key": "bob_trick_key_002",
        },
    )
    assert bad_resp.status_code == 400
    assert "Invalid question sequence" in bad_resp.json()["message"]


def test_anti_cheat_idempotent_duplicate_submission(client, published_quiz):
    start_resp = client.post(
        f"/api/player/quizzes/{published_quiz.id}/start",
        json={"player_name": "Charlie Duplicate"},
    )
    session_id = start_resp.json()["session_id"]
    token = start_resp.json()["session_token"]
    headers = {"X-Session-Token": token}

    # Submit Q1 first time
    first_ans = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers=headers,
        json={
            "question_order": 1,
            "selected_option": "B",
            "idempotency_key": "charlie_key_q1_001",
        },
    )
    assert first_ans.status_code == 200
    score_first = first_ans.json()["current_score"]

    # Re-submit Q1 with same or different key
    replay_ans = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers=headers,
        json={
            "question_order": 1,
            "selected_option": "B",
            "idempotency_key": "charlie_key_q1_001",
        },
    )
    assert replay_ans.status_code == 200
    # Score must not double!
    assert replay_ans.json()["current_score"] == score_first


def test_anti_cheat_maximum_attempts_enforced(client, published_quiz):
    # published_quiz has maximum_attempts = 3
    for i in range(3):
        resp = client.post(
            f"/api/player/quizzes/{published_quiz.id}/start",
            json={"player_name": "MaxAttemptPlayer"},
        )
        assert resp.status_code == 201

    # 4th attempt must be rejected
    blocked = client.post(
        f"/api/player/quizzes/{published_quiz.id}/start",
        json={"player_name": "MaxAttemptPlayer"},
    )
    assert blocked.status_code == 400
    assert "Maximum attempt limit" in blocked.json()["message"]


def test_anti_cheat_expired_session_rejected(client, db, published_quiz):
    start_resp = client.post(
        f"/api/player/quizzes/{published_quiz.id}/start",
        json={"player_name": "Slow Player"},
    )
    session_id = start_resp.json()["session_id"]
    token = start_resp.json()["session_token"]
    headers = {"X-Session-Token": token}

    # Manually expire the session in the database
    session_db = db.query(QuizSession).filter(QuizSession.id == session_id).first()
    session_db.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()

    # Attempt to answer after expiration
    expired_resp = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers=headers,
        json={
            "question_order": 1,
            "selected_option": "B",
            "idempotency_key": "slow_player_key_001",
        },
    )
    assert expired_resp.status_code == 400
    assert "expired" in expired_resp.json()["message"].lower()


def test_anti_cheat_player_cannot_access_admin_routes(client, published_quiz):
    start_resp = client.post(
        f"/api/player/quizzes/{published_quiz.id}/start",
        json={"player_name": "Hacker Player"},
    )
    token = start_resp.json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Try admin routes
    admin_routes = [
        client.get("/api/admin/quizzes", headers=headers),
        client.post("/api/admin/quizzes", headers=headers, json={"title": "Hacked"}),
        client.delete(f"/api/admin/quizzes/{published_quiz.id}", headers=headers),
        client.get("/api/admin/results", headers=headers),
        client.get("/api/admin/results/export", headers=headers),
    ]

    for resp in admin_routes:
        assert resp.status_code == 401


def test_anti_cheat_player_event_telemetry(client, published_quiz):
    start_resp = client.post(
        f"/api/player/quizzes/{published_quiz.id}/start",
        json={"player_name": "Proctored Student"},
    )
    assert start_resp.status_code == 201
    session_id = start_resp.json()["session_id"]
    token = start_resp.json()["session_token"]
    headers = {"X-Session-Token": token}

    events_to_test = [
        ("COPY_ATTEMPT", 1, {"shortcut": "Ctrl+C"}),
        ("PASTE_ATTEMPT", 1, {"shortcut": "Ctrl+V"}),
        ("TAB_SWITCH", 1, {"visibility_state": "hidden"}),
        ("RIGHT_CLICK_ATTEMPT", 1, {}),
        ("DEVTOOLS_SHORTCUT", 1, {"key": "F12"}),
    ]

    for event_type, q_order, details in events_to_test:
        resp = client.post(
            f"/api/player/sessions/{session_id}/event",
            headers=headers,
            json={
                "event_type": event_type,
                "question_order": q_order,
                "details": details,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "RECORDED"
        assert resp.json()["event_type"] == event_type
