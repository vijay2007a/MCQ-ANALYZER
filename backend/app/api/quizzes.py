from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_admin
from app.core.rate_limit import rate_limit
from app.models.admin import Admin
from app.schemas.quiz import (
    QuizCreate,
    QuizUpdate,
    QuizAdminResponse,
    QuizPublishValidationResponse,
    DocxParseResponse,
    QuizImportDocxRequest,
)
from app.schemas.question import (
    QuestionCreate,
    QuestionUpdate,
    QuestionAdminResponse,
    QuestionReorderRequest,
)
from app.services.quiz_service import quiz_service
from app.services.audit_service import audit_service
from app.services.docx_parser_service import docx_parser_service

router = APIRouter(prefix="/admin/quizzes", tags=["Admin Quizzes"])


def _build_quiz_admin_response(q) -> QuizAdminResponse:
    return QuizAdminResponse(
        id=q.id,
        title=q.title,
        description=q.description,
        difficulty=q.difficulty,
        status=q.status,
        time_per_question=q.time_per_question,
        duration_minutes=getattr(q, "duration_minutes", 15) or 15,
        marks_per_question=getattr(q, "marks_per_question", 1) or 1,
        negative_marks=getattr(q, "negative_marks", 0) or 0,
        access_code=getattr(q, "access_code", None),
        randomize_questions=bool(getattr(q, "randomize_questions", False)),
        randomize_options=bool(getattr(q, "randomize_options", False)),
        results_published=bool(getattr(q, "results_published", True)),
        maximum_attempts=q.maximum_attempts,
        scoring_config=q.scoring_config,
        created_by=q.created_by,
        question_count=len(q.questions),
        participant_count=len(q.results) if hasattr(q, "results") and q.results is not None else 0,
        created_at=q.created_at,
        updated_at=q.updated_at,
        published_at=q.published_at,
    )


@router.get("", response_model=List[QuizAdminResponse])
def list_admin_quizzes(
    status: Optional[str] = Query(None, description="Filter by status (DRAFT, PUBLISHED, etc.)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    List all quizzes with question count for admin dashboard.
    """
    quizzes, _ = quiz_service.get_quizzes(db, skip=skip, limit=limit, status=status)
    return [_build_quiz_admin_response(q) for q in quizzes]


@router.post("", response_model=QuizAdminResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit("quiz_create", max_requests=30, window_seconds=60))])
def create_quiz(
    quiz_in: QuizCreate,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Create a new quiz draft.
    """
    quiz = quiz_service.create_quiz(db, quiz_in=quiz_in, admin_id=current_admin.id)
    return _build_quiz_admin_response(quiz)


@router.get("/{quiz_id}", response_model=QuizAdminResponse)
def get_quiz_detail(
    quiz_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Get quiz details by ID.
    """
    quiz = quiz_service.get_quiz_by_id(db, quiz_id=quiz_id)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    return _build_quiz_admin_response(quiz)


@router.put("/{quiz_id}", response_model=QuizAdminResponse)
def update_quiz(
    quiz_id: int,
    quiz_in: QuizUpdate,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Update quiz details and configuration.
    """
    quiz = quiz_service.get_quiz_by_id(db, quiz_id=quiz_id)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    updated = quiz_service.update_quiz(db, quiz=quiz, quiz_in=quiz_in)
    return _build_quiz_admin_response(updated)


@router.delete("/{quiz_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(rate_limit("quiz_delete", max_requests=20, window_seconds=60))])
def delete_quiz(
    quiz_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Permanently delete / archive a quiz and its questions while preserving historical student records.
    """
    quiz = quiz_service.get_quiz_by_id(db, quiz_id=quiz_id)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    quiz_title = quiz.title
    quiz_service.delete_quiz(db, quiz=quiz, soft_delete=True)

    audit_service.log_event(
        db=db,
        event_type="QUIZ_DELETED",
        actor_type="ADMIN",
        actor_id=current_admin.email,
        resource_type="QUIZ",
        resource_id=str(quiz_id),
        details={"title": quiz_title, "action": "PERMANENT_DELETE"}
    )

    return {"message": "Quiz deleted successfully."}


@router.post("/{quiz_id}/publish", response_model=QuizPublishValidationResponse)
def publish_quiz(
    quiz_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Validate and publish a quiz so it becomes playable by students.
    """
    quiz = quiz_service.get_quiz_by_id(db, quiz_id=quiz_id)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    success, errors = quiz_service.publish_quiz(db, quiz=quiz)
    if not success:
        return QuizPublishValidationResponse(is_valid=False, errors=errors)

    return QuizPublishValidationResponse(is_valid=True, errors=[])


@router.post("/{quiz_id}/unpublish", response_model=QuizAdminResponse)
def unpublish_quiz(
    quiz_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Unpublish a quiz to withdraw it from the public player view.
    """
    quiz = quiz_service.get_quiz_by_id(db, quiz_id=quiz_id)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    unpublished = quiz_service.unpublish_quiz(db, quiz=quiz)
    return _build_quiz_admin_response(unpublished)


@router.post("/{quiz_id}/toggle-results", response_model=QuizAdminResponse)
def toggle_quiz_results_visibility(
    quiz_id: int,
    publish: Optional[bool] = None,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Toggle whether student results and ranks are published/visible for a quiz.
    """
    quiz = quiz_service.get_quiz_by_id(db, quiz_id=quiz_id)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    if publish is not None:
        quiz.results_published = bool(publish)
    else:
        quiz.results_published = not bool(getattr(quiz, "results_published", True))
    db.commit()
    db.refresh(quiz)
    return _build_quiz_admin_response(quiz)


@router.post("/{quiz_id}/duplicate", response_model=QuizAdminResponse, status_code=status.HTTP_201_CREATED)
def duplicate_quiz(
    quiz_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Duplicate a quiz and all its questions into a new draft.
    """
    duplicated = quiz_service.duplicate_quiz(db, quiz_id=quiz_id, admin_id=current_admin.id)
    if not duplicated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original quiz not found")

    return _build_quiz_admin_response(duplicated)


# --- Question Management Endpoints ---

@router.get("/{quiz_id}/questions", response_model=List[QuestionAdminResponse])
def get_admin_questions(
    quiz_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Get all questions for a quiz (including correct answers and explanations for admins).
    """
    quiz = quiz_service.get_quiz_by_id(db, quiz_id=quiz_id)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    return quiz.questions


@router.post("/{quiz_id}/questions", response_model=QuestionAdminResponse, status_code=status.HTTP_201_CREATED)
def add_question_to_quiz(
    quiz_id: int,
    question_in: QuestionCreate,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Add a question to a quiz.
    """
    try:
        question = quiz_service.add_question(db, quiz_id=quiz_id, question_in=question_in)
        return question
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/questions/{question_id}", response_model=QuestionAdminResponse)
@router.put("/{quiz_id}/questions/{question_id}", response_model=QuestionAdminResponse)
def update_quiz_question(
    question_id: int,
    question_in: QuestionUpdate,
    quiz_id: Optional[int] = None,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Update a quiz question.
    """
    updated = quiz_service.update_question(db, question_id=question_id, question_in=question_in)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return updated


@router.delete("/questions/{question_id}", status_code=status.HTTP_200_OK)
@router.delete("/{quiz_id}/questions/{question_id}", status_code=status.HTTP_200_OK)
def delete_quiz_question(
    question_id: int,
    quiz_id: Optional[int] = None,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Delete a quiz question and re-order remaining questions continuously.
    """
    success = quiz_service.delete_question(db, question_id=question_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return {"message": "Question deleted successfully"}


@router.post("/{quiz_id}/questions/reorder", status_code=status.HTTP_200_OK)
def reorder_quiz_questions(
    quiz_id: int,
    reorder_in: QuestionReorderRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Reorder questions in a quiz.
    """
    try:
        quiz_service.reorder_questions(db, quiz_id=quiz_id, orders=reorder_in.orders)
        return {"message": "Questions reordered successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/parse-docx", response_model=DocxParseResponse)
async def parse_docx_quiz(
    file: UploadFile = File(...),
    current_admin: Admin = Depends(get_current_admin),
):
    """
    Parse an uploaded Word (.docx) assessment file into structured MCQs.
    Validates all questions, options, answers, and explanations.
    """
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only Word documents (.docx) are supported."
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    clean_filename = file.filename.rsplit(".", 1)[0].replace("_", " ").title()
    result = docx_parser_service.parse_docx_bytes(file_bytes, fallback_title=clean_filename)
    return result


@router.post("/import-docx", response_model=QuizAdminResponse)
def import_docx_quiz(
    import_data: QuizImportDocxRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Import and persist a reviewed Word (.docx) quiz and all its MCQs into the database.
    """
    if not import_data.questions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot import an empty quiz. At least 1 question is required."
        )

    # Validate each question before importing
    for idx, q in enumerate(import_data.questions, start=1):
        if not q.question_text or len(q.question_text.strip()) < 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Question {idx}: Question text is required (minimum 5 characters)."
            )
        if not (q.option_a and q.option_b and q.option_c and q.option_d):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Question {idx}: All four options (A, B, C, D) are required."
            )
        if q.correct_option.upper() not in ["A", "B", "C", "D"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Question {idx}: Correct answer must be one of A, B, C, D."
            )

    # 1. Create Quiz in Database
    quiz_in = QuizCreate(
        title=import_data.title,
        description=import_data.description,
        difficulty=import_data.difficulty,
        time_per_question=import_data.time_per_question,
        duration_minutes=getattr(import_data, "duration_minutes", 15),
        marks_per_question=getattr(import_data, "marks_per_question", 1),
        negative_marks=getattr(import_data, "negative_marks", 0),
        access_code=getattr(import_data, "access_code", None),
        randomize_questions=getattr(import_data, "randomize_questions", False),
        randomize_options=getattr(import_data, "randomize_options", False),
        results_published=getattr(import_data, "results_published", True),
        maximum_attempts=import_data.maximum_attempts,
    )
    quiz = quiz_service.create_quiz(db, quiz_in=quiz_in, admin_id=current_admin.id)

    # 2. Create Questions
    for idx, q in enumerate(import_data.questions, start=1):
        q_in = QuestionCreate(
            question_text=q.question_text,
            option_a=q.option_a,
            option_b=q.option_b,
            option_c=q.option_c,
            option_d=q.option_d,
            correct_option=q.correct_option.upper(),
            explanation=q.explanation or f"Correct option is {q.correct_option.upper()}.",
            question_order=idx,
        )
        quiz_service.add_question(db, quiz_id=quiz.id, question_in=q_in)

    # 3. Publish immediately if requested
    if import_data.publish_immediately:
        quiz_service.publish_quiz(db, quiz=quiz)

    db.refresh(quiz)

    # 4. Log Audit Event
    audit_service.log_event(
        db=db,
        event_type="QUIZ_IMPORTED_DOCX",
        actor_type="ADMIN",
        actor_id=current_admin.email,
        resource_type="QUIZ",
        resource_id=str(quiz.id),
        details={
            "title": quiz.title,
            "questions_imported": len(import_data.questions),
            "published": import_data.publish_immediately,
        }
    )

    return _build_quiz_admin_response(quiz)
