from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_admin
from app.models.admin import Admin
from app.models.quiz import Quiz
from app.models.quiz_session import QuizSession
from app.models.result import QuizResult
from app.models.answer import QuizAttempt
from app.schemas.auth import AdminResponse, CreateAdminRequest, AdminSetupRequest
from app.services.auth_service import auth_service
from app.services.leaderboard_service import leaderboard_service
from app.core.config import settings

router = APIRouter(prefix="/admin", tags=["Admin Management"])


@router.post("/setup", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
def initial_admin_setup(setup_data: AdminSetupRequest, db: Session = Depends(get_db)):
    """
    Bootstrap the initial admin account.
    Allowed only if no active admins exist or in development mode.
    """
    admin_count = db.query(Admin).count()
    if admin_count > 0:
        # If admins already exist, reject setup
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Initial setup has already been completed. Contact an existing admin.",
        )

    try:
        admin = auth_service.create_admin(
            db,
            email=setup_data.email,
            password=setup_data.password,
            role="ADMIN",
        )
        return admin
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/admins", response_model=List[AdminResponse])
def list_admins(current_admin: Admin = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    List all admin users. Requires Admin authentication.
    """
    return db.query(Admin).order_by(Admin.created_at.desc()).all()


@router.post("/admins", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
def create_new_admin(
    admin_in: CreateAdminRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Create a new admin user account. Requires Admin authentication.
    """
    try:
        new_admin = auth_service.create_admin(
            db,
            email=admin_in.email,
            password=admin_in.password,
            role=admin_in.role,
        )
        return new_admin
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/dashboard-stats")
def get_admin_dashboard_stats(
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Aggregate real-time KPI statistics, recent quiz activity, and student performance metrics for the Admin Dashboard.
    """
    quizzes = db.query(Quiz).filter(Quiz.is_deleted == False).order_by(Quiz.created_at.desc()).all()
    results = db.query(QuizResult).join(Quiz, QuizResult.quiz_id == Quiz.id).filter(Quiz.is_deleted == False).order_by(QuizResult.completed_at.desc()).all()
    sessions = db.query(QuizSession).join(Quiz, QuizSession.quiz_id == Quiz.id).filter(Quiz.is_deleted == False).order_by(QuizSession.started_at.desc()).all()

    total_quizzes = len(quizzes)
    active_quizzes = sum(1 for q in quizzes if q.status == "PUBLISHED")
    completed_quizzes = sum(1 for q in quizzes if q.status in ["UNPUBLISHED", "ARCHIVED"] or len(q.results) > 0)
    total_participants = len(results)
    active_attempting = sum(1 for s in sessions if s.status == "ACTIVE")

    avg_accuracy = round(sum(r.accuracy for r in results) / total_participants, 1) if total_participants > 0 else 0.0
    avg_score = round(sum(r.total_score for r in results) / total_participants, 1) if total_participants > 0 else 0.0
    avg_marks = round(sum((getattr(r, "marks_obtained", r.correct_answers) or r.correct_answers) for r in results) / total_participants, 1) if total_participants > 0 else 0.0

    # Per-quiz participation & performance stats for charts
    quiz_stats = []
    for q in quizzes[:8]:
        q_results = [r for r in results if r.quiz_id == q.id]
        q_count = len(q_results)
        q_avg_acc = round(sum(r.accuracy for r in q_results) / q_count, 1) if q_count > 0 else 0.0
        q_avg_marks = round(sum((getattr(r, "marks_obtained", r.correct_answers) or r.correct_answers) for r in q_results) / q_count, 1) if q_count > 0 else 0.0
        quiz_stats.append({
            "quiz_id": q.id,
            "title": q.title,
            "status": q.status,
            "question_count": len(q.questions),
            "participants": q_count,
            "avg_accuracy": q_avg_acc,
            "avg_marks": q_avg_marks,
            "access_code": getattr(q, "access_code", None),
        })

    # Performance distribution buckets
    buckets = {"90_100": 0, "75_89": 0, "50_74": 0, "below_50": 0}
    for r in results:
        if r.accuracy >= 90:
            buckets["90_100"] += 1
        elif r.accuracy >= 75:
            buckets["75_89"] += 1
        elif r.accuracy >= 50:
            buckets["50_74"] += 1
        else:
            buckets["below_50"] += 1

    recent_activity = []
    for r in results[:10]:
        recent_activity.append({
            "session_id": r.session_id,
            "player_name": r.player_name,
            "register_number": getattr(r, "register_number", None),
            "quiz_id": r.quiz_id,
            "quiz_title": r.quiz.title if r.quiz else f"Quiz #{r.quiz_id}",
            "total_score": r.total_score,
            "marks_obtained": getattr(r, "marks_obtained", r.correct_answers) or r.correct_answers,
            "total_marks": getattr(r, "total_marks", r.total_questions) or r.total_questions,
            "accuracy": r.accuracy,
            "total_time_ms": r.total_time_ms,
            "warnings_count": getattr(r, "warnings_count", 0) or 0,
            "completed_at": r.completed_at,
        })

    return {
        "total_quizzes": total_quizzes,
        "active_quizzes": active_quizzes,
        "completed_quizzes": completed_quizzes,
        "total_participants": total_participants,
        "active_attempting": active_attempting,
        "average_accuracy": avg_accuracy,
        "average_score": avg_score,
        "average_marks": avg_marks,
        "quiz_stats": quiz_stats,
        "performance_distribution": buckets,
        "recent_activity": recent_activity,
    }


@router.get("/live-control")
def get_live_quiz_control_data(
    quiz_id: Optional[int] = Query(None, description="Specific quiz ID to monitor"),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Real-time monitoring data for the Admin Live Quiz Control Room.
    Reports joined students, currently attempting, submitted, disconnected, live submissions, and live leaderboard.
    """
    quizzes = db.query(Quiz).filter(Quiz.is_deleted == False, Quiz.status != "ARCHIVED").order_by(Quiz.created_at.desc()).all()
    target_quiz = None
    if quiz_id:
        target_quiz = db.query(Quiz).filter(Quiz.id == quiz_id, Quiz.is_deleted == False, Quiz.status != "ARCHIVED").first()
        if not target_quiz:
            raise HTTPException(status_code=404, detail="Selected quiz not found")
    if not target_quiz and quizzes:
        published_list = [q for q in quizzes if q.status == "PUBLISHED"]
        target_quiz = published_list[0] if published_list else quizzes[0]

    if not target_quiz:
        return {
            "quiz": None,
            "quizzes": [],
            "joined_count": 0,
            "attempting_count": 0,
            "submitted_count": 0,
            "disconnected_count": 0,
            "participants": [],
            "leaderboard": [],
        }

    now = datetime.now(timezone.utc)
    sessions = db.query(QuizSession).filter(QuizSession.quiz_id == target_quiz.id).order_by(QuizSession.started_at.desc()).all()
    total_q = len(target_quiz.questions)

    joined_count = len(sessions)
    attempting_count = 0
    submitted_count = 0
    disconnected_count = 0
    participants = []

    for s in sessions:
        last_act = s.last_activity_at if s.last_activity_at.tzinfo else s.last_activity_at.replace(tzinfo=timezone.utc)
        exp_at = s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=timezone.utc)
        idle_seconds = (now - last_act).total_seconds()
        answered_count = len(s.attempts) if s.attempts is not None else 0

        if s.status == "COMPLETED" or s.result is not None:
            live_state = "SUBMITTED"
            submitted_count += 1
        elif s.status in ["EXPIRED", "ABANDONED"] or now > exp_at:
            live_state = "DISCONNECTED"
            disconnected_count += 1
        elif idle_seconds > 120:
            live_state = "DISCONNECTED"
            disconnected_count += 1
        else:
            live_state = "ATTEMPTING"
            attempting_count += 1

        rem_seconds = max(0, int((exp_at - now).total_seconds())) if live_state == "ATTEMPTING" else 0

        participants.append({
            "session_id": s.id,
            "player_name": s.player_name,
            "register_number": getattr(s, "register_number", None) or "-",
            "live_state": live_state,
            "status": s.status,
            "answered_count": answered_count,
            "total_questions": total_q,
            "current_question_order": min(s.current_question_order, max(1, total_q)),
            "warnings_count": getattr(s, "warnings_count", 0) or 0,
            "remaining_seconds": rem_seconds,
            "started_at": s.started_at,
            "last_activity_at": s.last_activity_at,
            "score": s.result.total_score if s.result else sum(a.points_earned for a in (s.attempts or [])),
            "marks_obtained": getattr(s.result, "marks_obtained", s.result.correct_answers) if s.result else sum(1 for a in (s.attempts or []) if a.is_correct),
            "accuracy": s.result.accuracy if s.result else 0.0,
            "total_time_ms": s.result.total_time_ms if s.result else sum(a.response_time_ms for a in (s.attempts or [])),
        })

    lb_entries, _, _ = leaderboard_service.get_leaderboard(db, quiz_id=target_quiz.id, limit=25)

    return {
        "quiz": {
            "id": target_quiz.id,
            "title": target_quiz.title,
            "status": target_quiz.status,
            "difficulty": target_quiz.difficulty,
            "question_count": total_q,
            "time_per_question": target_quiz.time_per_question,
            "duration_minutes": getattr(target_quiz, "duration_minutes", 15) or 15,
            "marks_per_question": getattr(target_quiz, "marks_per_question", 1) or 1,
            "access_code": getattr(target_quiz, "access_code", None),
            "results_published": bool(getattr(target_quiz, "results_published", True)),
            "published_at": target_quiz.published_at,
        },
        "quizzes": [
            {
                "id": q.id,
                "title": q.title,
                "status": q.status,
                "access_code": getattr(q, "access_code", None),
                "question_count": len(q.questions),
            }
            for q in quizzes
        ],
        "joined_count": joined_count,
        "attempting_count": attempting_count,
        "submitted_count": submitted_count,
        "disconnected_count": disconnected_count,
        "participants": participants,
        "leaderboard": [e.model_dump() for e in lb_entries],
    }


@router.post("/monitoring/reset")
def reset_monitoring_logs(
    quiz_id: Optional[int] = Query(None, description="Optional quiz ID to reset monitoring for"),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Clear proctoring and student telemetry logs. If quiz_id is provided, clears only that quiz's logs.
    """
    from app.models.audit_log import AuditLog
    player_logs = db.query(AuditLog).filter(AuditLog.actor_type == "PLAYER").all()
    for log in player_logs:
        details = log.details or {}
        if quiz_id:
            log_qid = details.get("quiz_id")
            if log_qid is not None and str(log_qid) == str(quiz_id):
                db.delete(log)
        else:
            db.delete(log)
    db.commit()

    if settings.DATABASE_BACKEND == "firestore":
        try:
            from app.core.firebase import firestore_client
            client = firestore_client()
            if quiz_id:
                for doc in client.collection("monitoring_events").where("quiz_id", "==", quiz_id).stream():
                    doc.reference.delete()
                for doc in client.collection("monitoring_events").where("quiz_id", "==", str(quiz_id)).stream():
                    doc.reference.delete()
            else:
                for doc in client.collection("monitoring_events").stream():
                    doc.reference.delete()
        except Exception:
            pass

    return {"status": "SUCCESS", "message": "Proctoring logs have been reset."}

