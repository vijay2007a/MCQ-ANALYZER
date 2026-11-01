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
    SaveAnswerDraftRequest,
    FinishQuizRequest,
)
from app.schemas.result import PlayerResultResponse
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
    db: Session = Depends(get_db),
):
    """
    Get the current progression status of the quiz session, including sanitized questions and saved answers for refresh recovery.
    """
    total_questions = len(session.quiz.questions)
    all_questions = session_service.get_all_session_questions(db, session)
    saved_answers = session_service.get_saved_answers_map(db, session)
    now_utc = datetime.now(timezone.utc)
    exp_utc = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
    rem_sec = max(0, int((exp_utc - now_utc).total_seconds()))
    return SessionStatusResponse(
        session_id=session.id,
        status=session.status,
        player_name=session.player_name,
        register_number=session.register_number,
        quiz_id=session.quiz_id,
        quiz_title=session.quiz.title,
        current_question_order=session.current_question_order,
        total_questions=total_questions,
        time_per_question=session.quiz.time_per_question,
        duration_minutes=getattr(session.quiz, "duration_minutes", 15) or 15,
        marks_per_question=getattr(session.quiz, "marks_per_question", 1) or 1,
        negative_marks=getattr(session.quiz, "negative_marks", 0) or 0,
        is_completed=(session.status == "COMPLETED" or session.current_question_order > total_questions),
        started_at=session.started_at,
        expires_at=session.expires_at,
        remaining_seconds=rem_sec,
        questions=all_questions,
        saved_answers=saved_answers,
        marked_for_review=session.marked_for_review or [],
        warnings_count=getattr(session, "warnings_count", 0) or 0,
    )


@router.post(
    "/{session_id}/save-draft",
    dependencies=[Depends(rate_limit("save_draft", max_requests=120, window_seconds=60))]
)
def save_answer_draft(
    session_id: int,
    draft_in: SaveAnswerDraftRequest,
    session: QuizSession = Depends(get_current_player_session),
    db: Session = Depends(get_db),
):
    """
    Autosave a student's selected answer and/or Mark-for-Review status on the backend.
    Supports non-sequential palette navigation and refresh recovery.
    """
    try:
        return session_service.save_draft_answer(
            db,
            session=session,
            question_order=draft_in.question_order,
            selected_option=draft_in.selected_option,
            marked_for_review=draft_in.marked_for_review,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{session_id}/finish",
    response_model=PlayerResultResponse,
    dependencies=[Depends(rate_limit("finish_quiz", max_requests=30, window_seconds=60))]
)
def finish_quiz_session(
    request: Request,
    session_id: int,
    finish_in: FinishQuizRequest,
    session: QuizSession = Depends(get_current_player_session),
    db: Session = Depends(get_db),
):
    """
    Finalize and submit the entire quiz session (manual submission or timer expiry auto-submit).
    Computes server-authoritative scores, marks, and leaderboard rank.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent")

    try:
        result, rank = session_service.finish_quiz_session(
            db,
            session=session,
            answers=finish_in.answers,
            marked_for_review=finish_in.marked_for_review,
            reason=finish_in.reason or "MANUAL_SUBMIT",
            client_ip=client_ip,
            user_agent=user_agent,
        )
        if not result:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to finalize result")

        results_pub = bool(getattr(session.quiz, "results_published", True))
        return PlayerResultResponse(
            session_id=result.session_id,
            player_name=result.player_name,
            register_number=getattr(result, "register_number", None),
            quiz_id=result.quiz_id,
            quiz_title=result.quiz.title if result.quiz else "Quiz",
            total_score=result.total_score if results_pub else 0,
            marks_obtained=getattr(result, "marks_obtained", result.correct_answers) if results_pub else 0,
            total_marks=getattr(result, "total_marks", result.total_questions),
            correct_answers=result.correct_answers if results_pub else 0,
            incorrect_answers=result.incorrect_answers if results_pub else 0,
            unanswered_questions=getattr(result, "unanswered_questions", 0),
            total_questions=result.total_questions,
            accuracy=result.accuracy if results_pub else 0.0,
            total_time_ms=result.total_time_ms,
            average_response_time_ms=result.average_response_time_ms,
            warnings_count=getattr(result, "warnings_count", 0) or 0,
            quiz_status=getattr(result, "quiz_status", "COMPLETED"),
            results_published=results_pub,
            completed_at=result.completed_at,
            rank=rank if results_pub else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


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

    ev_upper = event_in.event_type.upper()
    if ev_upper in {
        "TAB_SWITCH", "WINDOW_BLUR", "FULLSCREEN_EXIT",
        "COPY_ATTEMPT", "PASTE_ATTEMPT", "CUT_ATTEMPT",
        "SELECT_ALL_ATTEMPT", "RIGHT_CLICK_ATTEMPT", "DEVTOOLS_SHORTCUT",
    }:
        session.warnings_count = (getattr(session, "warnings_count", 0) or 0) + 1
        session.last_activity_at = now_utc
        db.commit()

    audit_service.log_event(
        db,
        event_type=ev_upper,
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
        event_type=ev_upper,
        recorded_at=now_utc,
    )
