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

    results_pub = bool(getattr(result.quiz, "results_published", True)) if result.quiz else True

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

    # Compute per-quiz competition ranks (tied marks/score + completion time share the same rank)
    from collections import defaultdict
    from app.models.result import QuizResult
    quiz_ids = {r.quiz_id for r in results if r.quiz_id is not None}
    rank_by_result_id = {}
    if quiz_ids:
        all_quiz_results = (
            db.query(QuizResult)
            .filter(QuizResult.quiz_id.in_(quiz_ids))
            .order_by(
                QuizResult.quiz_id.asc(),
                QuizResult.marks_obtained.desc(),
                QuizResult.total_score.desc(),
                QuizResult.total_time_ms.asc(),
                QuizResult.completed_at.asc(),
            )
            .all()
        )
        grouped = defaultdict(list)
        for qr in all_quiz_results:
            grouped[qr.quiz_id].append(qr)
        for q_id, qr_list in grouped.items():
            prev_key = None
            prev_rank = 1
            for idx_pos, qr in enumerate(qr_list, start=1):
                marks_val = getattr(qr, "marks_obtained", None) or qr.correct_answers or 0
                key = (marks_val, qr.total_score, qr.total_time_ms)
                if prev_key is not None and key == prev_key:
                    current_rank = prev_rank
                else:
                    current_rank = idx_pos
                    prev_rank = current_rank
                    prev_key = key
                rank_by_result_id[qr.id] = current_rank

    items = [
        AdminResultResponse(
            id=r.id,
            session_id=r.session_id,
            player_name=r.player_name,
            register_number=getattr(r, "register_number", None) or (r.session.register_number if r.session else None),
            quiz_id=r.quiz_id,
            quiz_title=r.quiz.title if r.quiz else "Quiz",
            total_score=r.total_score,
            marks_obtained=getattr(r, "marks_obtained", r.correct_answers) or r.correct_answers,
            total_marks=getattr(r, "total_marks", r.total_questions) or r.total_questions,
            correct_answers=r.correct_answers,
            incorrect_answers=r.incorrect_answers,
            unanswered_questions=getattr(r, "unanswered_questions", 0) or 0,
            total_questions=r.total_questions,
            accuracy=r.accuracy,
            total_time_ms=r.total_time_ms,
            average_response_time_ms=r.average_response_time_ms,
            warnings_count=getattr(r, "warnings_count", 0) or (r.session.warnings_count if r.session else 0) or 0,
            quiz_status=getattr(r, "quiz_status", "COMPLETED") or "COMPLETED",
            completed_at=r.completed_at,
            rank=rank_by_result_id.get(r.id, 1),
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


@router.delete("/admin/results/{result_id}")
def delete_admin_result(
    result_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Delete a saved result and its answers; retain a session tombstone against replay."""
    from app.models.result import QuizResult
    from app.models.answer import QuizAttempt
    from app.models.audit_log import AuditLog
    result = db.query(QuizResult).filter(QuizResult.id == result_id).with_for_update().first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    session = result.session
    if session:
        session.status = "RESULT_DELETED"
        db.query(QuizAttempt).filter(QuizAttempt.session_id == session.id).delete(synchronize_session=False)
    db.delete(result)
    db.add(AuditLog(event_type="RESULT_DELETED", actor_type="ADMIN",
                    actor_id=str(current_admin.id), resource_type="RESULT", resource_id=str(result_id)))
    db.commit()
    return {"message": "Result deleted"}
