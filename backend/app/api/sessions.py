from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_player_session
from app.core.rate_limit import rate_limit
from app.models.quiz_session import QuizSession
from app.schemas.question import QuestionPlayerResponse
from app.schemas.session import (
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    SessionStatusResponse,
    PlayerEventRequest,
    PlayerEventResponse,
)
from app.services.session_service import session_service
from app.services.audit_service import audit_service

router = APIRouter(prefix="/player/sessions", tags=["Quiz Sessions"])


@router.get("/{session_id}/question", response_model=QuestionPlayerResponse)
def get_current_question(
    session_id: int,
    session: QuizSession = Depends(get_current_player_session),
    db: Session = Depends(get_db),
):
    """
    Get the current active question for the session.
    NEVER includes the correct answer or explanation.
    """
    try:
        question = session_service.get_current_question(db, session)
        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No further active questions available for this session",
            )
        return question
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{session_id}/answer",
    response_model=SubmitAnswerResponse,
    dependencies=[Depends(rate_limit("submit_answer", max_requests=60, window_seconds=60))]
)
def submit_answer(
    request: Request,
    session_id: int,
    answer_in: SubmitAnswerRequest,
    session: QuizSession = Depends(get_current_player_session),
    db: Session = Depends(get_db),
):
    """
    Submit an answer for the current question.
    Calculates server-authoritative elapsed response time and scoring.
    Returns explanation and correct answer ONLY after submission.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent")

    try:
        response = session_service.submit_answer(
            db,
            session=session,
            question_order=answer_in.question_order,
            selected_option=answer_in.selected_option,
            idempotency_key=answer_in.idempotency_key,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{session_id}/status", response_model=SessionStatusResponse)
def get_session_status(
    session_id: int,
    session: QuizSession = Depends(get_current_player_session),
):
    """
    Get the current progression status of the quiz session.
    """
    total_questions = len(session.quiz.questions)
    return SessionStatusResponse(
        session_id=session.id,
        status=session.status,
        player_name=session.player_name,
        quiz_id=session.quiz_id,
        quiz_title=session.quiz.title,
        current_question_order=session.current_question_order,
        total_questions=total_questions,
        is_completed=(session.status == "COMPLETED" or session.current_question_order > total_questions),
        started_at=session.started_at,
        expires_at=session.expires_at,
    )


@router.post(
    "/{session_id}/event",
    response_model=PlayerEventResponse,
    dependencies=[Depends(rate_limit("player_event", max_requests=120, window_seconds=60))]
)
def record_player_event(
    request: Request,
    session_id: int,
    event_in: PlayerEventRequest,
    session: QuizSession = Depends(get_current_player_session),
    db: Session = Depends(get_db),
):
    """
    Record an anti-cheating, clipboard, or client-side monitoring event.
    Logs event into the server-authoritative audit log and proctoring trail.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent")
    now_utc = datetime.now(timezone.utc)

    details = event_in.details or {}
    details.update({
        "question_order": event_in.question_order,
        "quiz_id": session.quiz_id,
        "quiz_title": session.quiz.title,
        "session_status": session.status,
        "current_question_order": session.current_question_order,
    })

    audit_service.log_event(
        db,
        event_type=event_in.event_type.upper(),
        actor_type="PLAYER",
        actor_id=session.player_name,
        ip_address=client_ip,
        user_agent=user_agent,
        resource_type="QUIZ_SESSION",
        resource_id=str(session.id),
        details=details,
    )

    return PlayerEventResponse(
        status="RECORDED",
        event_type=event_in.event_type.upper(),
        recorded_at=now_utc,
    )
