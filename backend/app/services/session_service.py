from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.quiz import Quiz
from app.models.question import Question
from app.models.quiz_session import QuizSession
from app.models.answer import QuizAttempt
from app.schemas.question import QuestionPlayerResponse
from app.schemas.session import SubmitAnswerResponse
from app.core.security import generate_player_session_token, hash_session_token
from app.core.config import settings
from app.services.scoring_service import scoring_service
from app.services.result_service import result_service
from app.services.audit_service import audit_service


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SessionService:
    @staticmethod
    def start_quiz_session(
        db: Session,
        quiz_id: int,
        player_name: str,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[QuizSession, str, Optional[QuestionPlayerResponse]]:
        quiz = db.query(Quiz).filter(
            Quiz.id == quiz_id,
            Quiz.status == "PUBLISHED",
            Quiz.is_deleted == False,
        ).first()

        if not quiz:
            audit_service.log_event(
                db,
                event_type="UNAUTHORIZED_QUIZ_ACCESS",
                actor_type="PLAYER",
                actor_id=player_name,
                ip_address=client_ip,
                user_agent=user_agent,
                resource_type="QUIZ",
                resource_id=str(quiz_id),
                details={"reason": "Quiz does not exist, is draft/archived, or is not published"},
            )
            raise ValueError("Quiz not found or is not currently published")

        total_questions = len(quiz.questions)
        if total_questions == 0:
            raise ValueError("Quiz has no questions available")

        clean_name = player_name.strip()
        if not clean_name:
            raise ValueError("Player name cannot be empty")

        # Check maximum attempts restriction
        if quiz.maximum_attempts > 0:
            existing_attempts = db.query(QuizSession).filter(
                QuizSession.quiz_id == quiz_id,
                QuizSession.player_name.ilike(clean_name),
            ).count()
            if existing_attempts >= quiz.maximum_attempts:
                audit_service.log_event(
                    db,
                    event_type="MAX_ATTEMPTS_EXCEEDED",
                    actor_type="PLAYER",
                    actor_id=clean_name,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    resource_type="QUIZ",
                    resource_id=str(quiz_id),
                    details={"attempt_count": existing_attempts, "max_allowed": quiz.maximum_attempts},
                )
                raise ValueError(
                    f"Maximum attempt limit ({quiz.maximum_attempts}) reached for player '{clean_name}' on this quiz"
                )

        raw_token = generate_player_session_token()
        token_hash = hash_session_token(raw_token)

        now = utc_now()
        # Allocate total quiz time plus 5-minute network buffer
        calculated_seconds = (quiz.time_per_question * total_questions) + 300
        expires_at = now + timedelta(seconds=max(calculated_seconds, settings.SESSION_EXPIRE_MINUTES * 60))

        session = QuizSession(
            player_name=clean_name,
            session_token_hash=token_hash,
            quiz_id=quiz.id,
            started_at=now,
            expires_at=expires_at,
            current_question_order=1,
            current_question_started_at=now,
            status="ACTIVE",
            created_at=now,
            last_activity_at=now,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        audit_service.log_event(
            db,
            event_type="QUIZ_SESSION_STARTED",
            actor_type="PLAYER",
            actor_id=str(session.id),
            ip_address=client_ip,
            user_agent=user_agent,
            resource_type="SESSION",
            resource_id=str(session.id),
            details={"quiz_id": quiz.id, "player_name": clean_name},
        )

        # Retrieve sanitized first question
        first_q = db.query(Question).filter(
            Question.quiz_id == quiz_id,
            Question.question_order == 1,
        ).first()

        first_q_response = None
        if first_q:
            first_q_response = QuestionPlayerResponse(
                question_number=1,
                total_questions=total_questions,
                question_text=first_q.question_text,
                options={
                    "A": first_q.option_a,
                    "B": first_q.option_b,
                    "C": first_q.option_c,
                    "D": first_q.option_d,
                },
                time_per_question=quiz.time_per_question,
            )

        return session, raw_token, first_q_response

    @staticmethod
    def get_session_by_token(db: Session, raw_token: str) -> Optional[QuizSession]:
        token_hash = hash_session_token(raw_token)
        return db.query(QuizSession).filter(QuizSession.session_token_hash == token_hash).first()

    @staticmethod
    def get_session_by_id(db: Session, session_id: int) -> Optional[QuizSession]:
        return db.query(QuizSession).filter(QuizSession.id == session_id).first()

    @staticmethod
    def get_current_question(db: Session, session: QuizSession) -> Optional[QuestionPlayerResponse]:
        now = utc_now()
        if session.status != "ACTIVE":
            raise ValueError(f"Session is no longer active (status: {session.status})")
        
        if ensure_utc(now) > ensure_utc(session.expires_at):
            session.status = "EXPIRED"
            db.commit()
            raise ValueError("Quiz session has expired")

        total_questions = len(session.quiz.questions)
        if session.current_question_order > total_questions:
            return None

        question = db.query(Question).filter(
            Question.quiz_id == session.quiz_id,
            Question.question_order == session.current_question_order,
        ).first()

        if not question:
            return None

        # Sanitize: NEVER return correct_option or explanation
        return QuestionPlayerResponse(
            question_number=question.question_order,
            total_questions=total_questions,
            question_text=question.question_text,
            options={
                "A": question.option_a,
                "B": question.option_b,
                "C": question.option_c,
                "D": question.option_d,
            },
            time_per_question=session.quiz.time_per_question,
        )

    @staticmethod
    def submit_answer(
        db: Session,
        session: QuizSession,
        question_order: int,
        selected_option: str,
        idempotency_key: str,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> SubmitAnswerResponse:
        now = utc_now()

        # 1. Validate session status
        if session.status == "COMPLETED":
            raise ValueError("Quiz session has already been completed")
        if session.status in ["EXPIRED", "ABANDONED"]:
            raise ValueError(f"Session is not active (status: {session.status})")

        # 2. Check session expiration
        if ensure_utc(now) > ensure_utc(session.expires_at):
            session.status = "EXPIRED"
            result_service.create_result_from_session(db, session)
            db.commit()
            audit_service.log_event(
                db,
                event_type="SESSION_EXPIRED_SUBMISSION",
                actor_type="PLAYER",
                actor_id=str(session.id),
                ip_address=client_ip,
                user_agent=user_agent,
                resource_type="SESSION",
                resource_id=str(session.id),
                details={"submitted_question_order": question_order},
            )
            raise ValueError("Session expired before answer submission")

        # 3. Check for idempotent re-submission
        existing_attempt = db.query(QuizAttempt).filter(
            QuizAttempt.session_id == session.id,
            (QuizAttempt.question_order == question_order) | (QuizAttempt.idempotency_key == idempotency_key),
        ).first()

        if existing_attempt:
            audit_service.log_event(
                db,
                event_type="REPLAY_ATTEMPT",
                actor_type="PLAYER",
                actor_id=str(session.id),
                ip_address=client_ip,
                user_agent=user_agent,
                resource_type="SESSION",
                resource_id=str(session.id),
                details={"idempotency_key": idempotency_key, "question_order": question_order},
            )
            question = existing_attempt.question
            total_questions = len(session.quiz.questions)
            is_completed = (session.status == "COMPLETED") or (session.current_question_order > total_questions)

            current_score = sum(
                a.points_earned for a in db.query(QuizAttempt.points_earned).filter(QuizAttempt.session_id == session.id).all()
            )

            next_q_resp = None
            if not is_completed:
                next_q_resp = SessionService.get_current_question(db, session)

            return SubmitAnswerResponse(
                is_correct=existing_attempt.is_correct,
                points_earned=existing_attempt.points_earned,
                response_time_ms=existing_attempt.response_time_ms,
                correct_option=question.correct_option,
                explanation=question.explanation,
                current_score=current_score,
                is_quiz_completed=is_completed,
                next_question_available=(next_q_resp is not None),
                next_question=next_q_resp,
            )

        # 4. Strict sequence validation: Out of order answering is rejected
        if question_order != session.current_question_order:
            audit_service.log_event(
                db,
                event_type="OUT_OF_ORDER_SUBMISSION",
                actor_type="PLAYER",
                actor_id=str(session.id),
                ip_address=client_ip,
                user_agent=user_agent,
                resource_type="SESSION",
                resource_id=str(session.id),
                details={"expected": session.current_question_order, "received": question_order},
            )
            raise ValueError(
                f"Invalid question sequence. Expected question #{session.current_question_order}, received #{question_order}"
            )

        # 5. Fetch current question from DB
        question = db.query(Question).filter(
            Question.quiz_id == session.quiz_id,
            Question.question_order == question_order,
        ).first()

        if not question:
            raise ValueError(f"Question #{question_order} does not exist for this quiz")

        # 6. Server-authoritative response time calculation (ms)
        elapsed_delta = ensure_utc(now) - ensure_utc(session.current_question_started_at)
        response_time_ms = max(50, int(elapsed_delta.total_seconds() * 1000))

        # 7. Check correctness and compute points
        is_correct = (selected_option.upper() == question.correct_option.upper())
        points_earned = scoring_service.calculate_points(
            is_correct=is_correct,
            response_time_ms=response_time_ms,
            scoring_config=session.quiz.scoring_config,
        )

        # 8. Record attempt atomically
        attempt = QuizAttempt(
            session_id=session.id,
            question_id=question.id,
            question_order=question_order,
            submitted_option=selected_option.upper(),
            is_correct=is_correct,
            response_time_ms=response_time_ms,
            points_earned=points_earned,
            submitted_at=now,
            idempotency_key=idempotency_key.strip(),
        )
        db.add(attempt)

        # 9. Advance session progression
        total_questions = len(session.quiz.questions)
        session.current_question_order += 1
        session.current_question_started_at = now
        session.last_activity_at = now

        is_quiz_completed = (session.current_question_order > total_questions)
        if is_quiz_completed:
            session.status = "COMPLETED"
            db.flush()
            result_service.create_result_from_session(db, session)
            audit_service.log_event(
                db,
                event_type="QUIZ_COMPLETED",
                actor_type="PLAYER",
                actor_id=str(session.id),
                ip_address=client_ip,
                user_agent=user_agent,
                resource_type="SESSION",
                resource_id=str(session.id),
                details={"quiz_id": session.quiz_id, "player_name": session.player_name},
            )

        db.commit()

        # 10. Fetch next question if available
        next_q_resp = None
        if not is_quiz_completed:
            next_q = db.query(Question).filter(
                Question.quiz_id == session.quiz_id,
                Question.question_order == session.current_question_order,
            ).first()
            if next_q:
                next_q_resp = QuestionPlayerResponse(
                    question_number=next_q.question_order,
                    total_questions=total_questions,
                    question_text=next_q.question_text,
                    options={
                        "A": next_q.option_a,
                        "B": next_q.option_b,
                        "C": next_q.option_c,
                        "D": next_q.option_d,
                    },
                    time_per_question=session.quiz.time_per_question,
                )

        # Compute total accumulated score
        current_score = sum(
            a.points_earned for a in db.query(QuizAttempt.points_earned).filter(QuizAttempt.session_id == session.id).all()
        )

        return SubmitAnswerResponse(
            is_correct=is_correct,
            points_earned=points_earned,
            response_time_ms=response_time_ms,
            correct_option=question.correct_option,
            explanation=question.explanation,
            current_score=current_score,
            is_quiz_completed=is_quiz_completed,
            next_question_available=(next_q_resp is not None),
            next_question=next_q_resp,
        )


session_service = SessionService()
