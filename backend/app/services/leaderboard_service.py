from datetime import datetime
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from app.models.result import QuizResult
from app.models.quiz import Quiz
from app.schemas.leaderboard import LeaderboardEntry


class LeaderboardService:
    @staticmethod
    def get_leaderboard(
        db: Session,
        quiz_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[LeaderboardEntry], int, Optional[str]]:
        query = db.query(QuizResult).join(Quiz, QuizResult.quiz_id == Quiz.id).filter(
            Quiz.is_deleted == False
        )

        quiz_title = None
        if quiz_id:
            query = query.filter(QuizResult.quiz_id == quiz_id)
            quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
            if quiz:
                quiz_title = quiz.title

        if date_from:
            query = query.filter(QuizResult.completed_at >= date_from)
        if date_to:
            query = query.filter(QuizResult.completed_at <= date_to)

        total = query.count()

        # Deterministic Ranking Rule:
        # 1. Highest Score
        # 2. Fastest Completion Time
        # 3. Earliest Completion Timestamp
        results = (
            query.order_by(
                QuizResult.total_score.desc(),
                QuizResult.total_time_ms.asc(),
                QuizResult.completed_at.asc(),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

        entries = []
        last_key = None
        current_rank = skip + 1
        for idx, r in enumerate(results, start=skip + 1):
            key = (r.total_score, r.total_time_ms)
            if last_key is not None and key == last_key:
                rank_val = current_rank
            else:
                rank_val = idx
                current_rank = idx
            last_key = key

            entries.append(
                LeaderboardEntry(
                    rank=rank_val,
                    player_name=r.player_name,
                    register_number=getattr(r, "register_number", None),
                    quiz_id=r.quiz_id,
                    quiz_title=r.quiz.title if r.quiz else "Unknown Quiz",
                    total_score=r.total_score,
                    marks_obtained=getattr(r, "marks_obtained", r.correct_answers) or r.correct_answers,
                    total_marks=getattr(r, "total_marks", r.total_questions) or r.total_questions,
                    correct_answers=r.correct_answers,
                    total_questions=r.total_questions,
                    accuracy=r.accuracy,
                    total_time_ms=r.total_time_ms,
                    completed_at=r.completed_at,
                )
            )

        return entries, total, quiz_title


leaderboard_service = LeaderboardService()
