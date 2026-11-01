import io
import docx
from openpyxl import load_workbook


def _build_numbered_docx_bytes() -> bytes:
    """Create a .docx buffer using the standard numbered format from the Argon prompt."""
    doc = docx.Document()
    doc.add_paragraph("Cloud Computing Assessment")
    doc.add_paragraph("1. What is cloud computing?")
    doc.add_paragraph("A. Delivery of computing services over the internet")
    doc.add_paragraph("B. A computer hardware component")
    doc.add_paragraph("C. An offline operating system")
    doc.add_paragraph("D. A network cable")
    doc.add_paragraph("Answer: A")

    doc.add_paragraph("2) Which protocol secures HTTP traffic using TLS?")
    doc.add_paragraph("(a) FTP")
    doc.add_paragraph("(b) HTTPS")
    doc.add_paragraph("(c) Telnet")
    doc.add_paragraph("(d) SMTP")
    doc.add_paragraph("Correct Answer: Option B")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_numbered_docx_extraction_and_import_with_settings(client, admin_headers):
    """Test standard numbered Word (.docx) extraction and import with duration, marks, access code, and randomization."""
    docx_bytes = _build_numbered_docx_bytes()

    # Step 1: Parse .docx
    parse_res = client.post(
        "/api/admin/quizzes/parse-docx",
        headers=admin_headers,
        files={"file": ("cloud_quiz.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert parse_res.status_code == 200
    parsed = parse_res.json()
    assert parsed["total_parsed"] == 2
    assert parsed["is_valid"] is True
    assert parsed["questions"][0]["question_text"] == "What is cloud computing?"
    assert parsed["questions"][0]["correct_option"] == "A"
    assert parsed["questions"][1]["correct_option"] == "B"

    # Step 2: Import and publish with custom duration, marks, and access code
    import_payload = {
        "title": "Cloud Computing Midterm",
        "description": "Cloud & Security MCQs",
        "difficulty": "MEDIUM",
        "time_per_question": 45,
        "duration_minutes": 15,
        "marks_per_question": 10,
        "negative_marks": 0,
        "access_code": "CLOUD101",
        "maximum_attempts": 1,
        "randomize_questions": False,
        "randomize_options": False,
        "results_published": True,
        "publish_immediately": True,
        "questions": parsed["questions"],
    }
    imp_res = client.post("/api/admin/quizzes/import-docx", headers=admin_headers, json=import_payload)
    assert imp_res.status_code == 200
    created = imp_res.json()
    assert created["status"] == "PUBLISHED"
    assert created["access_code"] == "CLOUD101"
    assert created["duration_minutes"] == 15
    assert created["marks_per_question"] == 10

    # Step 3: Lookup by Access Code
    lookup_res = client.get("/api/player/quizzes/code/cloud101")
    assert lookup_res.status_code == 200
    assert lookup_res.json()["id"] == created["id"]


def test_student_palette_autosave_refresh_recovery_and_batch_finish(client, admin_headers):
    """Test student join with register number, draft auto-saving, refresh recovery, and batch finish."""
    # Create & publish a 2-question quiz (deterministic order for testing)
    q_res = client.post(
        "/api/admin/quizzes",
        headers=admin_headers,
        json={
            "title": "DBMS Quiz",
            "description": "SQL & Normalization",
            "difficulty": "EASY",
            "time_per_question": 30,
            "duration_minutes": 10,
            "marks_per_question": 5,
            "access_code": "DBMS2026",
            "maximum_attempts": 1,
            "randomize_questions": False,
            "randomize_options": False,
            "results_published": True,
        },
    )
    assert q_res.status_code == 201
    quiz_id = q_res.json()["id"]

    for order, (text, ans) in enumerate([("What does SQL stand for?", "A"), ("Which normal form removes partial dependency?", "B")], start=1):
        client.post(
            f"/api/admin/quizzes/{quiz_id}/questions",
            headers=admin_headers,
            json={
                "question_text": text,
                "option_a": "Structured Query Language" if order == 1 else "1NF",
                "option_b": "Simple Query Language" if order == 1 else "2NF",
                "option_c": "System Query Logic" if order == 1 else "3NF",
                "option_d": "Standard Question Language" if order == 1 else "BCNF",
                "correct_option": ans,
                "explanation": f"Correct is {ans}",
                "question_order": order,
            },
        )
    client.post(f"/api/admin/quizzes/{quiz_id}/publish", headers=admin_headers)

    # 1. Start session with wrong access code -> rejected
    bad_start = client.post(
        f"/api/player/quizzes/{quiz_id}/start",
        json={"player_name": "Arun Kumar", "register_number": "21CS101", "access_code": "WRONG"},
    )
    assert bad_start.status_code == 400

    # 2. Start session with valid access code & register number
    start_res = client.post(
        f"/api/player/quizzes/{quiz_id}/start",
        json={"player_name": "Arun Kumar", "register_number": "21CS101", "access_code": "DBMS2026"},
    )
    assert start_res.status_code == 201
    session_data = start_res.json()
    session_id = session_data["session_id"]
    token = session_data["session_token"]
    questions = session_data["questions"]
    assert len(questions) == 2

    # 3. Auto-save draft answer for Q1 & mark Q2 for review
    draft1 = client.post(
        f"/api/player/sessions/{session_id}/save-draft",
        headers={"X-Session-Token": token},
        json={"question_order": 1, "selected_option": "A", "marked_for_review": False},
    )
    assert draft1.status_code == 200
    assert draft1.json()["saved_answers"]["1"] == "A"

    draft2 = client.post(
        f"/api/player/sessions/{session_id}/save-draft",
        headers={"X-Session-Token": token},
        json={"question_order": 2, "selected_option": None, "marked_for_review": True},
    )
    assert draft2.status_code == 200
    assert 2 in draft2.json()["marked_for_review"]

    # 4. Refresh recovery via GET /status
    status_res = client.get(
        f"/api/player/sessions/{session_id}/status",
        headers={"X-Session-Token": token},
    )
    assert status_res.status_code == 200
    status_payload = status_res.json()
    assert status_payload["register_number"] == "21CS101"
    assert status_payload["saved_answers"]["1"] == "A"
    assert 2 in status_payload["marked_for_review"]
    assert status_payload["remaining_seconds"] > 0

    # 5. Final batch submission (/finish)
    finish_res = client.post(
        f"/api/player/sessions/{session_id}/finish",
        headers={"X-Session-Token": token},
        json={
            "answers": {
                "1": "A",  # Correct (5 marks)
                "2": "C",  # Wrong (0 marks)
            }
        },
    )
    assert finish_res.status_code == 200
    result = finish_res.json()
    assert result["marks_obtained"] == 5
    assert result["total_marks"] == 10
    assert result["correct_answers"] == 1
    assert result["incorrect_answers"] == 1
    assert result["unanswered_questions"] == 0
    assert result["accuracy"] == 50.0

    # 6. Duplicate attempt with same Register Number -> blocked
    dup_res = client.post(
        f"/api/player/quizzes/{quiz_id}/start",
        json={"player_name": "Arun K", "register_number": "21CS101", "access_code": "DBMS2026"},
    )
    assert dup_res.status_code == 400


def test_tie_breaker_ranking_and_shared_ranks(client, db, published_quiz):
    """
    Verify ranking rules:
    1. Higher marks receive higher ranks.
    2. If marks are equal, faster completion time receives the higher rank.
    3. If marks and completion time are equal, students share the rank.
    """
    from datetime import datetime, timedelta, timezone
    from app.models.quiz_session import QuizSession
    from app.models.result import QuizResult

    now = datetime.now(timezone.utc)

    def _insert_result(name: str, reg_no: str, score: int, time_ms: int):
        sess = QuizSession(
            quiz_id=published_quiz.id,
            player_name=name,
            register_number=reg_no,
            session_token_hash=f"hash_{reg_no}",
            started_at=now,
            expires_at=now + timedelta(minutes=20),
            current_question_order=3,
            current_question_started_at=now,
            status="COMPLETED",
        )
        db.add(sess)
        db.flush()
        res = QuizResult(
            session_id=sess.id,
            quiz_id=published_quiz.id,
            player_name=name,
            register_number=reg_no,
            total_score=score,
            marks_obtained=score // 10,
            total_marks=20,
            correct_answers=score // 10,
            incorrect_answers=0,
            unanswered_questions=0,
            total_questions=2,
            accuracy=90.0,
            total_time_ms=time_ms,
            average_response_time_ms=time_ms // 2,
            warnings_count=0,
            quiz_status="COMPLETED",
        )
        db.add(res)
        db.commit()

    # Student A: 180 pts — 7 minutes (420,000 ms)
    # Student B: 180 pts — 5 minutes (300,000 ms)
    # Student B2: 180 pts — 5 minutes (300,000 ms) -> shares Rank 1 with Student B
    # Student C: 170 pts — 4 minutes (240,000 ms)
    _insert_result("Student A", "REG01", 180, 420000)
    _insert_result("Student B", "REG02", 180, 300000)
    _insert_result("Student B2", "REG03", 180, 300000)
    _insert_result("Student C", "REG04", 170, 240000)

    lb_res = client.get(f"/api/leaderboard?quiz_id={published_quiz.id}")
    assert lb_res.status_code == 200
    entries = lb_res.json()["items"]
    assert len(entries) == 4

    # Both B and B2 have 180 pts and 300,000 ms -> both share Rank 1
    assert entries[0]["rank"] == 1
    assert entries[1]["rank"] == 1
    assert {entries[0]["player_name"], entries[1]["player_name"]} == {"Student B", "Student B2"}

    # Student A is next (Rank 3)
    assert entries[2]["player_name"] == "Student A"
    assert entries[2]["rank"] == 3

    # Student C is 4th (Rank 4)
    assert entries[3]["player_name"] == "Student C"
    assert entries[3]["rank"] == 4


def test_result_publishing_toggle_and_live_control_and_excel_export(client, admin_headers, published_quiz):
    """Test hiding/publishing results, Admin Dashboard Stats, Live Control Room, and 14-column Excel Export."""
    # Student starts quiz
    start = client.post(
        f"/api/player/quizzes/{published_quiz.id}/start",
        json={"player_name": "Priya Sharma", "register_number": "21CS205"},
    ).json()
    session_id = start["session_id"]
    token = start["session_token"]

    # Hide results before student finishes
    toggle_hide = client.post(
        f"/api/admin/quizzes/{published_quiz.id}/toggle-results?publish=false",
        headers=admin_headers,
    )
    assert toggle_hide.status_code == 200
    assert toggle_hide.json()["results_published"] is False

    # Student finishes quiz -> scores should be hidden while results_published=False
    finish_res = client.post(
        f"/api/player/sessions/{session_id}/finish",
        headers={"X-Session-Token": token},
        json={"answers": {"1": "B"}},
    )
    assert finish_res.status_code == 200
    hidden_data = finish_res.json()
    assert hidden_data["results_published"] is False
    assert hidden_data["total_score"] == 0
    assert hidden_data["rank"] is None

    # Admin publishes results -> student can now see full scores and rank
    toggle_show = client.post(
        f"/api/admin/quizzes/{published_quiz.id}/toggle-results?publish=true",
        headers=admin_headers,
    )
    assert toggle_show.status_code == 200
    assert toggle_show.json()["results_published"] is True

    visible_res = client.get(
        f"/api/player/sessions/{session_id}/result",
        headers={"X-Session-Token": token},
    )
    assert visible_res.status_code == 200
    assert visible_res.json()["results_published"] is True
    assert visible_res.json()["correct_answers"] == 1
    assert visible_res.json()["rank"] == 1

    # Check Admin Dashboard Stats
    stats_res = client.get("/api/admin/dashboard-stats", headers=admin_headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_quizzes"] >= 1
    assert stats["total_participants"] >= 1

    # Check Live Control Room
    live_res = client.get(f"/api/admin/live-control?quiz_id={published_quiz.id}", headers=admin_headers)
    assert live_res.status_code == 200
    live_data = live_res.json()
    assert live_data["joined_count"] >= 1
    assert live_data["submitted_count"] >= 1

    # Check Excel Export (.xlsx) contains all 14 required columns
    export_res = client.get("/api/admin/results/export", headers=admin_headers)
    assert export_res.status_code == 200
    wb = load_workbook(io.BytesIO(export_res.content))
    ws = wb["Results"]
    headers = [cell.value for cell in ws[1]]
    required_columns = [
        "Rank",
        "Student Name",
        "Register Number",
        "Quiz Name",
        "Total Questions",
        "Correct Answers",
        "Wrong Answers",
        "Unanswered Questions",
        "Marks Obtained",
        "Percentage",
        "Completion Time",
        "Submission Time",
        "Quiz Status",
        "Recorded Warnings",
    ]
    for col in required_columns:
        assert col in headers, f"Missing required Excel column: {col}"
