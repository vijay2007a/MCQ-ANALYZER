from datetime import datetime, timedelta, timezone
from app.models.result import QuizResult
from app.models.quiz_session import QuizSession
from app.core.security import generate_player_session_token, hash_session_token


def test_deterministic_leaderboard_ranking(client, db, published_quiz):
    now = datetime.now(timezone.utc)

    # Create 3 player sessions & results to test tie-breaking
    players_data = [
        # Player A: 100 points, 15000 ms total time
        {"name": "Player A", "score": 100, "time_ms": 15000, "completed_at": now},
        # Player B: 100 points, 10000 ms total time (Faster than A -> Rank higher!)
        {"name": "Player B", "score": 100, "time_ms": 10000, "completed_at": now + timedelta(minutes=1)},
        # Player C: 150 points (Highest score -> Rank 1!)
        {"name": "Player C", "score": 150, "time_ms": 20000, "completed_at": now + timedelta(minutes=2)},
    ]

    for p in players_data:
        token = generate_player_session_token()
        session = QuizSession(
            player_name=p["name"],
            session_token_hash=hash_session_token(token),
            quiz_id=published_quiz.id,
            started_at=now,
            expires_at=now + timedelta(hours=1),
            status="COMPLETED",
        )
        db.add(session)
        db.flush()

        res = QuizResult(
            session_id=session.id,
            player_name=p["name"],
            quiz_id=published_quiz.id,
            total_score=p["score"],
            correct_answers=2,
            incorrect_answers=0,
            total_questions=2,
            accuracy=100.0,
            total_time_ms=p["time_ms"],
            average_response_time_ms=p["time_ms"] // 2,
            completed_at=p["completed_at"],
        )
        db.add(res)
    db.commit()

    # Query leaderboard
    leaderboard_resp = client.get(f"/api/leaderboard?quiz_id={published_quiz.id}")
    assert leaderboard_resp.status_code == 200
    items = leaderboard_resp.json()["items"]
    assert len(items) == 3

    # Rank 1: Player C (Score: 150)
    assert items[0]["player_name"] == "Player C"
    assert items[0]["rank"] == 1

    # Rank 2: Player B (Score: 100, Time: 10000 ms - faster than Player A)
    assert items[1]["player_name"] == "Player B"
    assert items[1]["rank"] == 2

    # Rank 3: Player A (Score: 100, Time: 15000 ms)
    assert items[2]["player_name"] == "Player A"
    assert items[2]["rank"] == 3


def test_admin_results_pagination_and_filter(client, admin_headers, db, published_quiz):
    # Fetch admin results
    resp = client.get(f"/api/admin/results?quiz_id={published_quiz.id}", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "size" in data
