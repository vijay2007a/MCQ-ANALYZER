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
        # Unanswered questions in expired sessions count as incorrect
        unanswered_count = max(0, total_questions - len(attempts))
        incorrect_count += unanswered_count

        total_time_ms = sum(a.response_time_ms for a in attempts)
        avg_response_time_ms = int(total_time_ms / len(attempts)) if attempts else 0
        accuracy = round((correct_count / total_questions * 100.0), 2) if total_questions > 0 else 0.0

        result = QuizResult(
            session_id=session.id,
            player_name=session.player_name,
            quiz_id=session.quiz_id,
            total_score=total_score,
            correct_answers=correct_count,
            incorrect_answers=incorrect_count,
            total_questions=total_questions,
            accuracy=accuracy,
            total_time_ms=total_time_ms,
            average_response_time_ms=avg_response_time_ms,
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
