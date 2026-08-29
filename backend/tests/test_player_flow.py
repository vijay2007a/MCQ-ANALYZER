def test_player_complete_quiz_journey(client, published_quiz):
    # 1. Player browses available quizzes
    quizzes_resp = client.get("/api/player/quizzes")
    assert quizzes_resp.status_code == 200
    assert len(quizzes_resp.json()) == 1

    # 2. Player starts quiz session
    start_resp = client.post(
        f"/api/player/quizzes/{published_quiz.id}/start",
        json={"player_name": "Alice Johnson"},
    )
    assert start_resp.status_code == 201
    start_data = start_resp.json()
    session_id = start_data["session_id"]
    session_token = start_data["session_token"]
    assert session_token is not None
    assert start_data["total_questions"] == 2

    # Verify first question is SANITIZED (No correct answer or explanation)
    first_q = start_data["first_question"]
    assert first_q is not None
    assert first_q["question_number"] == 1
    assert "correct_option" not in first_q
    assert "explanation" not in first_q
    assert "B" in first_q["options"]

    player_headers = {"X-Session-Token": session_token}

    # 3. Player fetches current question
    curr_q_resp = client.get(f"/api/player/sessions/{session_id}/question", headers=player_headers)
    assert curr_q_resp.status_code == 200
    curr_q = curr_q_resp.json()
    assert curr_q["question_number"] == 1
    assert "correct_option" not in curr_q
    assert "explanation" not in curr_q

    # 4. Player submits correct answer to Q1
    ans1_resp = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers=player_headers,
        json={
            "question_order": 1,
            "selected_option": "B",
            "idempotency_key": "idempotency_key_q1_alice_001",
        },
    )
    assert ans1_resp.status_code == 200
    ans1_data = ans1_resp.json()
    assert ans1_data["is_correct"] is True
    assert ans1_data["points_earned"] > 0
    assert ans1_data["correct_option"] == "B"
    assert "explanation" in ans1_data
    assert ans1_data["is_quiz_completed"] is False
    assert ans1_data["next_question_available"] is True
    assert ans1_data["next_question"]["question_number"] == 2

    # 5. Player submits incorrect answer to Q2
    ans2_resp = client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers=player_headers,
        json={
            "question_order": 2,
            "selected_option": "A",  # Wrong option (correct is C)
            "idempotency_key": "idempotency_key_q2_alice_002",
        },
    )
    assert ans2_resp.status_code == 200
    ans2_data = ans2_resp.json()
    assert ans2_data["is_correct"] is False
    assert ans2_data["points_earned"] == 0
    assert ans2_data["correct_option"] == "C"
    assert ans2_data["is_quiz_completed"] is True
    assert ans2_data["next_question_available"] is False

    # 6. Player views final official calculated result
    result_resp = client.get(f"/api/player/sessions/{session_id}/result", headers=player_headers)
    assert result_resp.status_code == 200
    res = result_resp.json()
    assert res["player_name"] == "Alice Johnson"
    assert res["correct_answers"] == 1
    assert res["incorrect_answers"] == 1
    assert res["total_questions"] == 2
    assert res["accuracy"] == 50.0
    assert res["total_score"] == ans1_data["points_earned"]
    assert res["rank"] == 1
