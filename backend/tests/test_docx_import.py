import io
import docx
import pytest
from app.services.docx_parser_service import docx_parser_service


def create_sample_docx_bytes(content: str) -> bytes:
    """Helper to generate a .docx file in memory from a multiline string."""
    doc = docx.Document()
    for line in content.strip().split("\n"):
        doc.add_paragraph(line.strip())
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.read()


def test_docx_parser_valid_computer_networks():
    """Test parsing the exact format provided by the user."""
    sample_text = """
    QUIZ TITLE: Computer Networks Unit 1

    Q1. What is the main purpose of a computer network?

    A. To increase CPU speed
    B. To connect computers and share resources
    C. To increase screen resolution
    D. To install software

    ANSWER: B

    EXPLANATION: A computer network allows devices to communicate and share resources.

    Q2. Which OSI layer is responsible for routing?

    A. Physical Layer
    B. Data Link Layer
    C. Network Layer
    D. Application Layer

    ANSWER: C

    EXPLANATION: The Network layer is responsible for logical addressing and routing.

    Q3. Which protocol translates domain names into IP addresses?

    A. FTP
    B. DNS
    C. HTTP
    D. SMTP

    ANSWER: B

    EXPLANATION: DNS translates human-readable domain names into IP addresses.
    """
    file_bytes = create_sample_docx_bytes(sample_text)
    result = docx_parser_service.parse_docx_bytes(file_bytes)

    assert result["is_valid"] is True
    assert result["quiz_title"] == "Computer Networks Unit 1"
    assert result["total_parsed"] == 3
    assert result["valid_questions_count"] == 3
    assert len(result["errors"]) == 0

    # Verify Question 1
    q1 = result["questions"][0]
    assert q1["question_order"] == 1
    assert "main purpose of a computer network" in q1["question_text"]
    assert q1["option_a"] == "To increase CPU speed"
    assert q1["option_b"] == "To connect computers and share resources"
    assert q1["option_c"] == "To increase screen resolution"
    assert q1["option_d"] == "To install software"
    assert q1["correct_option"] == "B"
    assert "communicate and share resources" in q1["explanation"]

    # Verify Question 2
    q2 = result["questions"][1]
    assert q2["correct_option"] == "C"
    assert q2["option_c"] == "Network Layer"

    # Verify Question 3
    q3 = result["questions"][2]
    assert q3["correct_option"] == "B"
    assert q3["option_b"] == "DNS"


def test_docx_parser_malformed_missing_option():
    """Test catching missing Option D and invalid answer value."""
    sample_text = """
    QUIZ TITLE: Sample Malformed Test

    Q5. What is HTTP?
    A. HyperText Transfer Protocol
    B. Hard Text Tool Protocol
    C. High Transmission Protocol
    ANSWER: A
    EXPLANATION: Standard web protocol.

    Q8. Which language is used for styling web pages?
    A. HTML
    B. CSS
    C. JavaScript
    D. Python
    ANSWER: Z
    EXPLANATION: CSS is used for styling.
    """
    file_bytes = create_sample_docx_bytes(sample_text)
    result = docx_parser_service.parse_docx_bytes(file_bytes)

    assert result["is_valid"] is False
    assert any("Question 5: Missing option D." in err for err in result["errors"])
    assert any("Question 8: Invalid ANSWER value" in err for err in result["errors"])


def test_admin_api_parse_and_import_docx(client, admin_token):
    """Test parse-docx and import-docx API endpoints."""
    sample_text = """
    QUIZ TITLE: Cloud Fundamentals

    Q1. Which model delivers virtualized compute resources?
    A. SaaS
    B. PaaS
    C. IaaS
    D. Serverless
    ANSWER: C
    EXPLANATION: Infrastructure as a Service provides virtual machines and storage.
    """
    file_bytes = create_sample_docx_bytes(sample_text)

    # 1. Parse endpoint
    parse_res = client.post(
        "/api/admin/quizzes/parse-docx",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("cloud_fundamentals.docx", file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert parse_res.status_code == 200
    parse_data = parse_res.json()
    assert parse_data["is_valid"] is True
    assert parse_data["quiz_title"] == "Cloud Fundamentals"
    assert len(parse_data["questions"]) == 1

    # 2. Import endpoint
    import_payload = {
        "title": parse_data["quiz_title"],
        "description": "Imported from Word doc",
        "difficulty": "EASY",
        "time_per_question": 25,
        "maximum_attempts": 1,
        "publish_immediately": True,
        "questions": parse_data["questions"],
    }
    import_res = client.post(
        "/api/admin/quizzes/import-docx",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=import_payload,
    )
    assert import_res.status_code == 200
    imported_quiz = import_res.json()
    assert imported_quiz["title"] == "Cloud Fundamentals"
    assert imported_quiz["status"] == "PUBLISHED"
    assert imported_quiz["question_count"] == 1
