from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_admin, get_current_player_session
from app.models.admin import Admin
from app.models.quiz_session import QuizSession
from app.schemas.result import PlayerResultResponse, AdminResultResponse, AdminResultsListResponse
from app.services.result_service import result_service

router = APIRouter(tags=["Results"])


@router.get("/player/sessions/{session_id}/result", response_model=PlayerResultResponse)
def get_player_session_result(
    session_id: int,
    session: QuizSession = Depends(get_current_player_session),
    db: Session = Depends(get_db),
):
    """
    Get the official calculated result for the authenticated player session.
    """
    result, rank = result_service.get_player_result_with_rank(db, session_id=session.id)
    if not result:
        # If not already completed, generate from session if done
        result = result_service.create_result_from_session(db, session)
        if result:
            _, rank = result_service.get_player_result_with_rank(db, session_id=session.id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not yet available. Please complete all quiz questions.",
        )

    return PlayerResultResponse(
        session_id=result.session_id,
        player_name=result.player_name,
        quiz_id=result.quiz_id,
        quiz_title=result.quiz.title if result.quiz else "Quiz",
        total_score=result.total_score,
        correct_answers=result.correct_answers,
        incorrect_answers=result.incorrect_answers,
        total_questions=result.total_questions,
        accuracy=result.accuracy,
        total_time_ms=result.total_time_ms,
        average_response_time_ms=result.average_response_time_ms,
        completed_at=result.completed_at,
        rank=rank,
    )


@router.get("/admin/results", response_model=AdminResultsListResponse)
def get_admin_results(
    quiz_id: Optional[int] = Query(None, description="Filter by quiz ID"),
    player_name: Optional[str] = Query(None, description="Search by player name"),
    start_date: Optional[datetime] = Query(None, description="Filter results after date"),
    end_date: Optional[datetime] = Query(None, description="Filter results before date"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Paginated and filtered view of all player results for administrators.
    """
    skip = (page - 1) * size
    results, total = result_service.get_admin_results(
        db,
        quiz_id=quiz_id,
        player_name=player_name,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=size,
    )

    items = [
        AdminResultResponse(
            id=r.id,
            session_id=r.session_id,
            player_name=r.player_name,
            quiz_id=r.quiz_id,
            quiz_title=r.quiz.title if r.quiz else "Quiz",
            total_score=r.total_score,
            correct_answers=r.correct_answers,
            incorrect_answers=r.incorrect_answers,
            total_questions=r.total_questions,
            accuracy=r.accuracy,
            total_time_ms=r.total_time_ms,
            average_response_time_ms=r.average_response_time_ms,
            completed_at=r.completed_at,
        )
        for r in results
    ]

    total_pages = (total + size - 1) // size if total > 0 else 1

    return AdminResultsListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        total_pages=total_pages,
    )
