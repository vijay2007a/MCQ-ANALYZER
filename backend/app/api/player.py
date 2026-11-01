from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.core.rate_limit import rate_limit
from app.models.quiz import Quiz
from app.schemas.quiz import QuizPublicResponse
from app.schemas.session import StartQuizRequest, StartQuizResponse
from app.services.session_service import session_service

router = APIRouter(prefix="/player", tags=["Player Quizzes"])


def _build_public_quiz_response(q: Quiz) -> QuizPublicResponse:
    return QuizPublicResponse(
        id=q.id,
        title=q.title,
        description=q.description,
        difficulty=q.difficulty,
        time_per_question=q.time_per_question,
        duration_minutes=getattr(q, "duration_minutes", 15) or 15,
        marks_per_question=getattr(q, "marks_per_question", 1) or 1,
        negative_marks=getattr(q, "negative_marks", 0) or 0,
        requires_access_code=bool(getattr(q, "access_code", None) and str(q.access_code).strip()),
        results_published=bool(getattr(q, "results_published", True)),
        total_questions=len(q.questions),
    )


@router.get("/quizzes", response_model=List[QuizPublicResponse])
def get_available_quizzes(db: Session = Depends(get_db)):
    """
    List all currently published quizzes available for players.
    """
    quizzes = db.query(Quiz).filter(
        Quiz.status == "PUBLISHED",
        Quiz.is_deleted == False,
    ).order_by(Quiz.created_at.desc()).all()

    return [_build_public_quiz_response(q) for q in quizzes]


@router.get("/quizzes/code/{access_code}", response_model=QuizPublicResponse)
def get_quiz_by_access_code(access_code: str, db: Session = Depends(get_db)):
    """
    Find a published quiz by its access code.
    """
    clean_code = access_code.strip().upper()
    quiz = db.query(Quiz).filter(
        Quiz.access_code == clean_code,
        Quiz.status == "PUBLISHED",
        Quiz.is_deleted == False,
    ).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active quiz found with that access code")
    return _build_public_quiz_response(quiz)


@router.get("/quizzes/{quiz_id}", response_model=QuizPublicResponse)
def get_public_quiz_info(quiz_id: int, db: Session = Depends(get_db)):
    """
    Get public information and time limits for a published quiz.
    """
    quiz = db.query(Quiz).filter(
        Quiz.id == quiz_id,
        Quiz.status == "PUBLISHED",
        Quiz.is_deleted == False,
    ).first()

    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found or not published")

    return _build_public_quiz_response(quiz)


@router.post(
    "/quizzes/{quiz_id}/start",
    response_model=StartQuizResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("player_start", max_requests=20, window_seconds=60))]
)
def start_quiz(
    request: Request,
    quiz_id: int,
    start_in: StartQuizRequest,
    db: Session = Depends(get_db),
):
    """
    Start a new quiz session for a player.
    Returns session credentials and sanitized questions (without answer key or explanation).
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent")

    try:
        session, raw_token, first_question = session_service.start_quiz_session(
            db,
            quiz_id=quiz_id,
            player_name=start_in.player_name,
            register_number=start_in.register_number,
            access_code=start_in.access_code,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        all_questions = session_service.get_all_session_questions(db, session)
        return StartQuizResponse(
            session_id=session.id,
            session_token=raw_token,
            quiz_id=session.quiz_id,
            quiz_title=session.quiz.title,
            register_number=session.register_number,
            time_per_question=session.quiz.time_per_question,
            duration_minutes=getattr(session.quiz, "duration_minutes", 15) or 15,
            marks_per_question=getattr(session.quiz, "marks_per_question", 1) or 1,
            negative_marks=getattr(session.quiz, "negative_marks", 0) or 0,
            started_at=session.started_at,
            expires_at=session.expires_at,
            total_questions=len(session.quiz.questions),
            first_question=first_question,
            questions=all_questions,
            saved_answers={},
            marked_for_review=session.marked_for_review or [],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
