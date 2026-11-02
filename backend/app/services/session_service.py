from datetime import datetime, timedelta, timezone
import random
from typing import Optional, Tuple, Dict, Any, List
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
    def _build_player_question(
        quiz: Quiz,
        session: QuizSession,
        slot_number: int,
        all_questions_by_order: Dict[int, Question],
    ) -> Optional[QuestionPlayerResponse]:
        total_questions = len(all_questions_by_order)
        if slot_number < 1 or slot_number > total_questions:
            return None

        order_map = session.question_order_map or list(range(1, total_questions + 1))
        actual_order = order_map[slot_number - 1] if (slot_number - 1) < len(order_map) else slot_number
        q = all_questions_by_order.get(actual_order)
        if not q:
            return None

        raw_opts = {
            "A": q.option_a,
            "B": q.option_b,
            "C": q.option_c,
            "D": q.option_d,
        }

        opt_map_all = session.option_order_map or {}
        slot_opt_map = opt_map_all.get(str(slot_number))
        if slot_opt_map and isinstance(slot_opt_map, dict):
            display_opts = {
                disp_k: raw_opts.get(orig_k, "")
                for disp_k, orig_k in slot_opt_map.items()
            }
        else:
            display_opts = raw_opts

        return QuestionPlayerResponse(
            question_number=slot_number,
            total_questions=total_questions,
            question_text=q.question_text,
            options=display_opts,
            time_per_question=quiz.time_per_question,
        )

    @staticmethod
    def get_all_session_questions(db: Session, session: QuizSession) -> List[QuestionPlayerResponse]:
        quiz = session.quiz
        questions = db.query(Question).filter(Question.quiz_id == session.quiz_id).order_by(Question.question_order.asc()).all()
        by_order = {q.question_order: q for q in questions}
        result_list: List[QuestionPlayerResponse] = []
        for slot in range(1, len(questions) + 1):
            qp = SessionService._build_player_question(quiz, session, slot, by_order)
            if qp:
                result_list.append(qp)
        return result_list

    @staticmethod
    def get_saved_answers_map(db: Session, session: QuizSession) -> Dict[int, str]:
        attempts = db.query(QuizAttempt).filter(QuizAttempt.session_id == session.id).all()
        opt_map_all = session.option_order_map or {}
        saved: Dict[int, str] = {}
        for a in attempts:
            slot = a.question_order
            slot_opt_map = opt_map_all.get(str(slot))
            if slot_opt_map and isinstance(slot_opt_map, dict):
                # Map canonical DB option back to display option for this session
                inv_map = {orig_k: disp_k for disp_k, orig_k in slot_opt_map.items()}
                saved[slot] = inv_map.get(a.submitted_option, a.submitted_option)
            else:
                saved[slot] = a.submitted_option
        return saved

    @staticmethod
    def start_quiz_session(
        db: Session,
        quiz_id: int,
        player_name: str,
        register_number: Optional[str] = None,
        access_code: Optional[str] = None,
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

        # Validate access code if quiz has one configured
        if quiz.access_code and quiz.access_code.strip():
            provided_code = (access_code or "").strip().upper()
            if provided_code != quiz.access_code.strip().upper():
                audit_service.log_event(
                    db,
                    event_type="INVALID_ACCESS_CODE",
                    actor_type="PLAYER",
                    actor_id=player_name,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    resource_type="QUIZ",
                    resource_id=str(quiz_id),
                )
                raise ValueError("Invalid quiz access code. Please check with your instructor.")

        total_questions = len(quiz.questions)
        if total_questions == 0:
            raise ValueError("Quiz has no questions available")

        clean_name = player_name.strip()
        if not clean_name:
            raise ValueError("Player name cannot be empty")

        clean_reg = register_number.strip().upper() if register_number and register_number.strip() else None

        # Check maximum attempts restriction (by register_number if provided, or player_name)
        if quiz.maximum_attempts > 0:
            if clean_reg:
                existing_attempts = db.query(QuizSession).filter(
                    QuizSession.quiz_id == quiz_id,
                    (QuizSession.register_number.ilike(clean_reg)) | (QuizSession.player_name.ilike(clean_name)),
                ).count()
            else:
                existing_attempts = db.query(QuizSession).filter(
                    QuizSession.quiz_id == quiz_id,
                    QuizSession.player_name.ilike(clean_name),
                ).count()
            if existing_attempts >= quiz.maximum_attempts:
                audit_service.log_event(
                    db,
                    event_type="MAX_ATTEMPTS_EXCEEDED",
                    actor_type="PLAYER",
                    actor_id=clean_reg or clean_name,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    resource_type="QUIZ",
                    resource_id=str(quiz_id),
                    details={"attempt_count": existing_attempts, "max_allowed": quiz.maximum_attempts},
                )
                raise ValueError(
                    f"Maximum attempt limit ({quiz.maximum_attempts}) reached for '{clean_reg or clean_name}' on this quiz"
                )

        # Build question_order_map and option_order_map for randomization
        base_orders = list(range(1, total_questions + 1))
        if getattr(quiz, "randomize_questions", False):
            random.shuffle(base_orders)

        option_map: Dict[str, Dict[str, str]] = {}
        if getattr(quiz, "randomize_options", False):
            letters = ["A", "B", "C", "D"]
            for slot in range(1, total_questions + 1):
                shuffled = letters[:]
                random.shuffle(shuffled)
                option_map[str(slot)] = {letters[i]: shuffled[i] for i in range(4)}

        raw_token = generate_player_session_token()
        token_hash = hash_session_token(raw_token)

        now = utc_now()
        # Allocate total quiz time plus 5-minute network buffer
        duration_sec = getattr(quiz, "duration_minutes", 0) * 60 if getattr(quiz, "duration_minutes", 0) else 0
        calculated_seconds = max(duration_sec, (quiz.time_per_question * total_questions)) + 300
        expires_at = now + timedelta(seconds=max(calculated_seconds, settings.SESSION_EXPIRE_MINUTES * 60))

        session = QuizSession(
            player_name=clean_name,
            register_number=clean_reg,
            session_token_hash=token_hash,
            quiz_id=quiz.id,
            started_at=now,
            expires_at=expires_at,
            current_question_order=1,
            current_question_started_at=now,
            status="ACTIVE",
            question_order_map=base_orders,
            option_order_map=option_map if option_map else None,
            marked_for_review=[],
            warnings_count=0,
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
            details={"quiz_id": quiz.id, "player_name": clean_name, "register_number": clean_reg},
        )

        questions = db.query(Question).filter(Question.quiz_id == quiz_id).all()
        by_order = {q.question_order: q for q in questions}
        first_q_response = SessionService._build_player_question(quiz, session, 1, by_order)

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

        questions = db.query(Question).filter(Question.quiz_id == session.quiz_id).all()
        by_order = {q.question_order: q for q in questions}
        return SessionService._build_player_question(session.quiz, session, session.current_question_order, by_order)

    @staticmethod
    def _resolve_actual_question_and_option(
        db: Session,
        session: QuizSession,
        slot_order: int,
        display_option: Optional[str],
    ) -> Tuple[Optional[Question], str]:
        questions = db.query(Question).filter(Question.quiz_id == session.quiz_id).all()
        by_order = {q.question_order: q for q in questions}
        total_questions = len(questions)
        order_map = session.question_order_map or list(range(1, total_questions + 1))
        actual_order = order_map[slot_order - 1] if 1 <= slot_order <= len(order_map) else slot_order
        question = by_order.get(actual_order)

        canonical_opt = (display_option or "A").upper()
        opt_map_all = session.option_order_map or {}
        slot_opt_map = opt_map_all.get(str(slot_order))
        if slot_opt_map and isinstance(slot_opt_map, dict) and display_option:
            canonical_opt = slot_opt_map.get(display_option.upper(), display_option.upper())

        return question, canonical_opt

    @staticmethod
    def save_draft_answer(
        db: Session,
        session: QuizSession,
        question_order: int,
        selected_option: Optional[str] = None,
        marked_for_review: Optional[bool] = None,
    ) -> Dict[str, Any]:
        now = utc_now()
        if session.status != "ACTIVE":
            raise ValueError(f"Session is not active (status: {session.status})")

        if ensure_utc(now) > ensure_utc(session.expires_at):
            session.status = "EXPIRED"
            result_service.create_result_from_session(db, session)
            db.commit()
            raise ValueError("Session has expired")

        total_questions = len(session.quiz.questions)
        if question_order < 1 or question_order > total_questions:
            raise ValueError(f"Question #{question_order} is out of bounds")

        # Update marked_for_review list if provided
        review_list = list(session.marked_for_review or [])
        if marked_for_review is not None:
            if marked_for_review and question_order not in review_list:
                review_list.append(question_order)
            elif not marked_for_review and question_order in review_list:
                review_list.remove(question_order)
            session.marked_for_review = sorted(review_list)

        # Save or update answer in QuizAttempt
        if selected_option:
            question, canonical_opt = SessionService._resolve_actual_question_and_option(
                db, session, question_order, selected_option
            )
            if not question:
                raise ValueError(f"Question #{question_order} not found")

            elapsed_delta = ensure_utc(now) - ensure_utc(session.current_question_started_at)
            response_time_ms = max(100, int(elapsed_delta.total_seconds() * 1000))
            is_correct = (canonical_opt.upper() == question.correct_option.upper())
            points_earned = scoring_service.calculate_points(
                is_correct=is_correct,
                response_time_ms=response_time_ms,
                scoring_config=session.quiz.scoring_config,
            )

            existing = db.query(QuizAttempt).filter(
                QuizAttempt.session_id == session.id,
                QuizAttempt.question_id == question.id,
            ).first()

            if existing:
                existing.submitted_option = canonical_opt.upper()
                existing.is_correct = is_correct
                existing.response_time_ms = response_time_ms
                existing.points_earned = points_earned
                existing.submitted_at = now
            else:
                attempt = QuizAttempt(
                    session_id=session.id,
                    question_id=question.id,
                    question_order=question_order,
                    submitted_option=canonical_opt.upper(),
                    is_correct=is_correct,
                    response_time_ms=response_time_ms,
                    points_earned=points_earned,
                    submitted_at=now,
                    idempotency_key=f"draft_{session.id}_q{question_order}",
                )
                db.add(attempt)

        session.current_question_order = question_order
        session.current_question_started_at = now
        session.last_activity_at = now
        db.commit()
        db.refresh(session)

        return {
            "status": "SAVED",
            "question_order": question_order,
            "selected_option": selected_option,
            "marked_for_review": session.marked_for_review or [],
            "saved_answers": SessionService.get_saved_answers_map(db, session),
            "saved_at": now,
        }

    @staticmethod
    def finish_quiz_session(
        db: Session,
        session: QuizSession,
        answers: Optional[Dict[str, str]] = None,
        marked_for_review: Optional[List[int]] = None,
        reason: str = "MANUAL_SUBMIT",
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        now = utc_now()
        if session.status == "RESULT_DELETED":
            raise ValueError("This result has been deleted by an administrator")
        if session.status == "COMPLETED":
            res, rank = result_service.get_player_result_with_rank(db, session.id)
            return res, rank

        if marked_for_review is not None:
            session.marked_for_review = marked_for_review

        # Persist any answers included in the final batch payload
        if answers and isinstance(answers, dict):
            total_questions = len(session.quiz.questions)
            elapsed_total_ms = max(500, int((ensure_utc(now) - ensure_utc(session.started_at)).total_seconds() * 1000))
            per_q_time_ms = max(100, elapsed_total_ms // max(1, len(answers)))

            for slot_str, disp_opt in answers.items():
                try:
                    slot_order = int(slot_str)
                except ValueError:
                    continue
                if slot_order < 1 or slot_order > total_questions:
                    continue
                if not disp_opt or str(disp_opt).upper() not in ["A", "B", "C", "D"]:
                    continue

                question, canonical_opt = SessionService._resolve_actual_question_and_option(
                    db, session, slot_order, str(disp_opt).upper()
                )
                if not question:
                    continue

                is_correct = (canonical_opt.upper() == question.correct_option.upper())
                points_earned = scoring_service.calculate_points(
                    is_correct=is_correct,
                    response_time_ms=per_q_time_ms,
                    scoring_config=session.quiz.scoring_config,
                )

                existing = db.query(QuizAttempt).filter(
                    QuizAttempt.session_id == session.id,
                    QuizAttempt.question_id == question.id,
                ).first()

                if existing:
                    existing.submitted_option = canonical_opt.upper()
                    existing.is_correct = is_correct
                    existing.points_earned = points_earned
                    existing.submitted_at = now
                else:
                    db.add(
                        QuizAttempt(
                            session_id=session.id,
                            question_id=question.id,
                            question_order=slot_order,
                            submitted_option=canonical_opt.upper(),
                            is_correct=is_correct,
                            response_time_ms=per_q_time_ms,
                            points_earned=points_earned,
                            submitted_at=now,
                            idempotency_key=f"final_{session.id}_q{slot_order}",
                        )
                    )

        session.status = "COMPLETED"
        session.last_activity_at = now
        db.flush()

        result = result_service.create_result_from_session(db, session)
        audit_service.log_event(
            db,
            event_type="QUIZ_COMPLETED",
            actor_type="PLAYER",
            actor_id=str(session.id),
            ip_address=client_ip,
            user_agent=user_agent,
            resource_type="SESSION",
            resource_id=str(session.id),
            details={"quiz_id": session.quiz_id, "player_name": session.player_name, "reason": reason},
        )
        db.commit()
        _, rank = result_service.get_player_result_with_rank(db, session.id)
        return result, rank

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
        if session.status in ["EXPIRED", "ABANDONED", "RESULT_DELETED"]:
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
