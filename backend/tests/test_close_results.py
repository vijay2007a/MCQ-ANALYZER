import io
from openpyxl import load_workbook


def test_close_downloads_and_preserves_results(client, admin_headers, published_quiz):
    started = client.post(f"/api/player/quizzes/{published_quiz.id}/start", json={"player_name": "Close Test"}).json()
    response = client.post(f"/api/admin/quizzes/{published_quiz.id}/close", headers=admin_headers)
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    assert "Results" in load_workbook(io.BytesIO(response.content)).sheetnames
    assert client.get("/api/admin/quizzes", headers=admin_headers).json() == []
    assert client.get("/api/player/quizzes").json() == []
    assert client.get("/api/admin/live-control", headers=admin_headers).json()["quiz"] is None
    results = client.get("/api/admin/results", headers=admin_headers).json()["items"]
    assert len(results) == 1
    assert results[0]["quiz_title"] == published_quiz.title
    assert results[0]["session_id"] == started["session_id"]
    # Retrying close re-downloads without duplicating results.
    assert client.post(f"/api/admin/quizzes/{published_quiz.id}/close", headers=admin_headers).status_code == 200
    assert client.get("/api/admin/results", headers=admin_headers).json()["total"] == 1
    result_id = results[0]["id"]
    assert client.delete(f"/api/admin/results/{result_id}").status_code == 401
    assert client.delete(f"/api/admin/results/{result_id}", headers=admin_headers).status_code == 200
    assert client.get("/api/admin/results", headers=admin_headers).json()["total"] == 0
    player_headers = {"X-Session-Token": started["session_token"]}
    assert client.get(f"/api/player/sessions/{started['session_id']}/result", headers=player_headers).status_code == 404
    assert client.post(f"/api/player/sessions/{started['session_id']}/finish", headers=player_headers, json={"answers": {"1": "B"}}).status_code >= 400
    assert client.get("/api/admin/results", headers=admin_headers).json()["total"] == 0


def test_close_requires_admin(client, published_quiz):
    assert client.post(f"/api/admin/quizzes/{published_quiz.id}/close").status_code == 401


def test_close_export_failure_keeps_quiz_open(client, admin_headers, published_quiz, monkeypatch):
    from app.services.export_service import export_service
    def fail(*args, **kwargs):
        raise ValueError("Export unavailable")
    monkeypatch.setattr(export_service, "generate_quiz_results_excel", fail)
    # TestClient propagates unexpected server exceptions.
    import pytest
    with pytest.raises(ValueError, match="Export unavailable"):
        client.post(f"/api/admin/quizzes/{published_quiz.id}/close", headers=admin_headers)
    quizzes = client.get("/api/admin/quizzes", headers=admin_headers).json()
    assert quizzes[0]["status"] == "PUBLISHED"
