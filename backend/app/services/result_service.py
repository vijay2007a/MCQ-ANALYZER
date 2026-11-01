from datetime import datetime, timezone
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.quiz_session import QuizSession
from app.models.answer import QuizAttempt
from app.models.result import QuizResult
from app.models.quiz import Quiz


class ResultService:
    @staticmethod
    def create_result_from_session(db: Session, session: QuizSession) -> Optional[QuizResult]:
        """
        Server-side calculation and storage of final quiz results.
        """
        existing = db.query(QuizResult).filter(QuizResult.session_id == session.id).first()
        if existing:
            return existing

        attempts = db.query(QuizAttempt).filter(QuizAttempt.session_id == session.id).all()
        total_questions = len(session.quiz.questions)
        
        if not attempts and total_questions == 0:
            return None

        total_score = sum(a.points_earned for a in attempts)
        correct_count = sum(1 for a in attempts if a.is_correct)
        incorrect_count = sum(1 for a in attempts if not a.is_correct)
        unanswered_count = max(0, total_questions - len(attempts))

        marks_per_q = getattr(session.quiz, "marks_per_question", 1) or 1
        neg_marks = getattr(session.quiz, "negative_marks", 0) or 0
        marks_obtained = max(0, (correct_count * marks_per_q) - (incorrect_count * neg_marks))
        total_marks = total_questions * marks_per_q

        # For backwards compatibility, incorrect_answers on result includes unanswered if needed by legacy tests,
        # while unanswered_questions tracks exact unanswered count.
        legacy_incorrect_count = incorrect_count + unanswered_count

        total_time_ms = sum(a.response_time_ms for a in attempts)
        if total_time_ms == 0 and session.started_at:
            now_dt = datetime.now(timezone.utc)
            st_dt = session.started_at if session.started_at.tzinfo else session.started_at.replace(tzinfo=timezone.utc)
            total_time_ms = max(100, int((now_dt - st_dt).total_seconds() * 1000))

        avg_response_time_ms = int(total_time_ms / len(attempts)) if attempts else 0
        accuracy = round((correct_count / total_questions * 100.0), 2) if total_questions > 0 else 0.0

        result = QuizResult(
            session_id=session.id,
            player_name=session.player_name,
            register_number=getattr(session, "register_number", None),
            quiz_id=session.quiz_id,
            total_score=total_score,
            marks_obtained=marks_obtained,
            total_marks=total_marks,
            correct_answers=correct_count,
            incorrect_answers=legacy_incorrect_count,
            unanswered_questions=unanswered_count,
            total_questions=total_questions,
            accuracy=accuracy,
            total_time_ms=total_time_ms,
            average_response_time_ms=avg_response_time_ms,
            warnings_count=getattr(session, "warnings_count", 0) or 0,
            quiz_status=session.status if session.status in ["COMPLETED", "EXPIRED"] else "COMPLETED",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        return result

    @staticmethod
    def get_player_result_with_rank(db: Session, session_id: int) -> Tuple[Optional[QuizResult], Optional[int]]:
        result = db.query(QuizResult).filter(QuizResult.session_id == session_id).first()
        if not result:
            return None, None

        # Calculate rank deterministically:
        # 1. Total score DESC
        # 2. Total time ASC
        # 3. Completed at ASC
        higher_ranks_count = db.query(QuizResult).filter(
            QuizResult.quiz_id == result.quiz_id,
            (QuizResult.total_score > result.total_score)
            | (
                (QuizResult.total_score == result.total_score)
                & (QuizResult.total_time_ms < result.total_time_ms)
            )
            | (
                (QuizResult.total_score == result.total_score)
                & (QuizResult.total_time_ms == result.total_time_ms)
                & (QuizResult.completed_at < result.completed_at)
            ),
        ).count()

        rank = higher_ranks_count + 1
        return result, rank

    @staticmethod
    def get_admin_results(
        db: Session,
        quiz_id: Optional[int] = None,
        player_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[QuizResult], int]:
        query = db.query(QuizResult)

        if quiz_id:
            query = query.filter(QuizResult.quiz_id == quiz_id)
        if player_name:
            query = query.filter(QuizResult.player_name.ilike(f"%{player_name.strip()}%"))
        if start_date:
            query = query.filter(QuizResult.completed_at >= start_date)
        if end_date:
            query = query.filter(QuizResult.completed_at <= end_date)

        total = query.count()
        results = query.order_by(QuizResult.completed_at.desc()).offset(skip).limit(limit).all()
        return results, total


result_service = ResultService()
