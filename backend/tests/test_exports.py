import io
import openpyxl


def test_admin_excel_export_all_results(client, admin_headers, published_quiz):
    # 1. Complete a quiz session first to ensure data is present
    start_resp = client.post(
        f"/api/player/quizzes/{published_quiz.id}/start",
        json={"player_name": "Export Test Player"},
    )
    session_id = start_resp.json()["session_id"]
    token = start_resp.json()["session_token"]
    player_headers = {"X-Session-Token": token}

    # Submit answers
    client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers=player_headers,
        json={"question_order": 1, "selected_option": "B", "idempotency_key": "exp_key_1"},
    )
    client.post(
        f"/api/player/sessions/{session_id}/answer",
        headers=player_headers,
        json={"question_order": 2, "selected_option": "C", "idempotency_key": "exp_key_2"},
    )

    # 2. Admin requests Excel export
    export_resp = client.get("/api/admin/results/export", headers=admin_headers)
    assert export_resp.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in export_resp.headers["content-type"]
    assert "Content-Disposition" in export_resp.headers

    # 3. Parse and validate Excel file in memory
    excel_data = io.BytesIO(export_resp.content)
    wb = openpyxl.load_workbook(excel_data)

    # Verify sheet names
    sheet_names = wb.sheetnames
    assert "Summary" in sheet_names
    assert "Results" in sheet_names
    assert "Question Performance" in sheet_names

    # Verify Results sheet content
    ws_results = wb["Results"]
    assert ws_results.max_row >= 2  # Header + at least 1 record
    headers = [cell.value for cell in ws_results[1]]
    assert "Rank" in headers
    assert "Player Name" in headers
    assert "Score" in headers
    assert "Accuracy (%)" in headers


def test_excel_export_unauthorized(client):
    export_resp = client.get("/api/admin/results/export")
    assert export_resp.status_code == 401
