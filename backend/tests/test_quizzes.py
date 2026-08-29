def test_admin_create_quiz(client, admin_headers):
    response = client.post(
        "/api/admin/quizzes",
        headers=admin_headers,
        json={
            "title": "Data Structures 101",
            "description": "Introduction to common data structures",
            "difficulty": "EASY",
            "time_per_question": 20,
            "maximum_attempts": 2,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Data Structures 101"
    assert data["status"] == "DRAFT"
    assert data["time_per_question"] == 20
    assert data["maximum_attempts"] == 2


def test_admin_add_question_and_publish(client, admin_headers):
    # 1. Create Quiz Draft
    create_resp = client.post(
        "/api/admin/quizzes",
        headers=admin_headers,
        json={"title": "Algorithms & Flow"},
    )
    quiz_id = create_resp.json()["id"]

    # 2. Try publishing empty quiz -> Expect validation error
    pub_fail = client.post(f"/api/admin/quizzes/{quiz_id}/publish", headers=admin_headers)
    assert pub_fail.status_code == 200
    assert pub_fail.json()["is_valid"] is False
    assert len(pub_fail.json()["errors"]) > 0

    # 3. Add valid question
    q_resp = client.post(
        f"/api/admin/quizzes/{quiz_id}/questions",
        headers=admin_headers,
        json={
            "question_text": "What is the worst-case time complexity of QuickSort?",
            "option_a": "O(n)",
            "option_b": "O(n log n)",
            "option_c": "O(n^2)",
            "option_d": "O(log n)",
            "correct_option": "C",
            "explanation": "QuickSort degrades to O(n^2) when poor pivots are chosen.",
            "question_order": 1,
        },
    )
    assert q_resp.status_code == 201
    assert q_resp.json()["correct_option"] == "C"

    # 4. Now publish valid quiz -> Expect success
    pub_success = client.post(f"/api/admin/quizzes/{quiz_id}/publish", headers=admin_headers)
    assert pub_success.status_code == 200
    assert pub_success.json()["is_valid"] is True

    # 5. Verify published quiz is in public list
    public_list = client.get("/api/player/quizzes")
    assert public_list.status_code == 200
    titles = [q["title"] for q in public_list.json()]
    assert any("Algorithms" in t for t in titles)


def test_admin_unpublish_and_duplicate_quiz(client, admin_headers, published_quiz):
    # Unpublish
    unpub = client.post(f"/api/admin/quizzes/{published_quiz.id}/unpublish", headers=admin_headers)
    assert unpub.status_code == 200
    assert unpub.json()["status"] == "UNPUBLISHED"

    # Duplicate
    dup = client.post(f"/api/admin/quizzes/{published_quiz.id}/duplicate", headers=admin_headers)
    assert dup.status_code == 201
    dup_data = dup.json()
    assert dup_data["title"] == f"{published_quiz.title} (Copy)"
    assert dup_data["status"] == "DRAFT"
    assert dup_data["question_count"] == 2


def test_admin_delete_quiz(client, admin_headers, published_quiz):
    del_resp = client.delete(f"/api/admin/quizzes/{published_quiz.id}", headers=admin_headers)
    assert del_resp.status_code == 200

    # Ensure it no longer appears in public quizzes
    public_list = client.get("/api/player/quizzes")
    quiz_ids = [q["id"] for q in public_list.json()]
    assert published_quiz.id not in quiz_ids
