from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.quiz import Quiz
from app.models.question import Question
from app.schemas.quiz import QuizCreate, QuizUpdate
from app.schemas.question import QuestionCreate, QuestionUpdate, QuestionReorderItem


class QuizService:
    @staticmethod
    def get_quizzes(
        db: Session,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        include_deleted: bool = False,
    ) -> Tuple[List[Quiz], int]:
        query = db.query(Quiz)
        if not include_deleted:
            query = query.filter(Quiz.is_deleted == False)
        if status:
            query = query.filter(Quiz.status == status.upper())
        
        total = query.count()
        quizzes = query.order_by(Quiz.created_at.desc()).offset(skip).limit(limit).all()
        return quizzes, total

    @staticmethod
    def get_quiz_by_id(db: Session, quiz_id: int, include_deleted: bool = False) -> Optional[Quiz]:
        query = db.query(Quiz).filter(Quiz.id == quiz_id)
        if not include_deleted:
            query = query.filter(Quiz.is_deleted == False)
        return query.first()

    @staticmethod
    def create_quiz(db: Session, quiz_in: QuizCreate, admin_id: Optional[int] = None) -> Quiz:
        scoring_dict = quiz_in.scoring_config.model_dump() if quiz_in.scoring_config else None
        quiz = Quiz(
            title=quiz_in.title.strip(),
            description=quiz_in.description.strip() if quiz_in.description else None,
            difficulty=quiz_in.difficulty,
            status="DRAFT",
            time_per_question=quiz_in.time_per_question,
            maximum_attempts=quiz_in.maximum_attempts,
            scoring_config=scoring_dict,
            created_by=admin_id,
        )
        db.add(quiz)
        db.commit()
        db.refresh(quiz)
        return quiz

    @staticmethod
    def update_quiz(db: Session, quiz: Quiz, quiz_in: QuizUpdate) -> Quiz:
        update_data = quiz_in.model_dump(exclude_unset=True)
        if "scoring_config" in update_data and update_data["scoring_config"] is not None:
            update_data["scoring_config"] = quiz_in.scoring_config.model_dump()
        
        if "title" in update_data and update_data["title"]:
            update_data["title"] = update_data["title"].strip()
        if "description" in update_data and update_data["description"]:
            update_data["description"] = update_data["description"].strip()

        for field, value in update_data.items():
            setattr(quiz, field, value)
        
        quiz.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(quiz)
        return quiz

    @staticmethod
    def delete_quiz(db: Session, quiz: Quiz, soft_delete: bool = True) -> bool:
        if soft_delete:
            quiz.is_deleted = True
            quiz.status = "ARCHIVED"
            quiz.updated_at = datetime.now(timezone.utc)
            db.commit()
        else:
            db.delete(quiz)
            db.commit()
        return True

    @staticmethod
    def duplicate_quiz(db: Session, quiz_id: int, admin_id: Optional[int] = None) -> Optional[Quiz]:
        original = QuizService.get_quiz_by_id(db, quiz_id)
        if not original:
            return None

        # Create duplicate quiz
        duplicated = Quiz(
            title=f"{original.title} (Copy)",
            description=original.description,
            difficulty=original.difficulty,
            status="DRAFT",
            time_per_question=original.time_per_question,
            maximum_attempts=original.maximum_attempts,
            scoring_config=original.scoring_config,
            created_by=admin_id or original.created_by,
        )
        db.add(duplicated)
        db.flush()

        # Copy all questions
        for q in original.questions:
            copied_q = Question(
                quiz_id=duplicated.id,
                question_text=q.question_text,
                option_a=q.option_a,
                option_b=q.option_b,
                option_c=q.option_c,
                option_d=q.option_d,
                correct_option=q.correct_option,
                explanation=q.explanation,
                question_order=q.question_order,
            )
            db.add(copied_q)

        db.commit()
        db.refresh(duplicated)
        return duplicated

    @staticmethod
    def validate_for_publishing(quiz: Quiz) -> Tuple[bool, List[str]]:
        errors = []
        if not quiz.title or len(quiz.title.strip()) < 3:
            errors.append("Quiz title must be at least 3 characters long.")
        
        if not quiz.questions or len(quiz.questions) == 0:
            errors.append("Quiz must have at least 1 question to be published.")
            return False, errors

        orders = []
        for idx, q in enumerate(quiz.questions, start=1):
            if not q.question_text or not q.question_text.strip():
                errors.append(f"Question #{idx} text cannot be empty.")
            if not q.option_a or not q.option_a.strip():
                errors.append(f"Question #{idx} option A cannot be empty.")
            if not q.option_b or not q.option_b.strip():
                errors.append(f"Question #{idx} option B cannot be empty.")
            if not q.option_c or not q.option_c.strip():
                errors.append(f"Question #{idx} option C cannot be empty.")
            if not q.option_d or not q.option_d.strip():
                errors.append(f"Question #{idx} option D cannot be empty.")
            if q.correct_option not in ["A", "B", "C", "D"]:
                errors.append(f"Question #{idx} has invalid correct option '{q.correct_option}'. Must be A, B, C, or D.")
            if not q.explanation or not q.explanation.strip():
                errors.append(f"Question #{idx} must have an explanation.")
            orders.append(q.question_order)

        # Check continuous ordering 1..N
        orders.sort()
        expected_orders = list(range(1, len(quiz.questions) + 1))
        if orders != expected_orders:
            errors.append(f"Questions must have continuous ordering from 1 to {len(quiz.questions)}.")

        if quiz.time_per_question < 5:
            errors.append("Time per question must be at least 5 seconds.")

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def publish_quiz(db: Session, quiz: Quiz) -> Tuple[bool, List[str]]:
        is_valid, errors = QuizService.validate_for_publishing(quiz)
        if not is_valid:
            return False, errors
        
        quiz.status = "PUBLISHED"
        quiz.published_at = datetime.now(timezone.utc)
        quiz.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(quiz)
        return True, []

    @staticmethod
    def unpublish_quiz(db: Session, quiz: Quiz) -> Quiz:
        quiz.status = "UNPUBLISHED"
        quiz.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(quiz)
        return quiz

    # Question management
    @staticmethod
    def add_question(db: Session, quiz_id: int, question_in: QuestionCreate) -> Question:
        quiz = QuizService.get_quiz_by_id(db, quiz_id)
        if not quiz:
            raise ValueError("Quiz not found")

        # Determine question order if not specified
        if question_in.question_order is None:
            max_order = db.query(Question.question_order).filter(Question.quiz_id == quiz_id).order_by(
                Question.question_order.desc()
            ).first()
            next_order = (max_order[0] + 1) if max_order else 1
        else:
            next_order = question_in.question_order

        question = Question(
            quiz_id=quiz_id,
            question_text=question_in.question_text.strip(),
            option_a=question_in.option_a.strip(),
            option_b=question_in.option_b.strip(),
            option_c=question_in.option_c.strip(),
            option_d=question_in.option_d.strip(),
            correct_option=question_in.correct_option.upper(),
            explanation=question_in.explanation.strip(),
            question_order=next_order,
        )
        db.add(question)
        db.commit()
        db.refresh(question)
        return question

    @staticmethod
    def update_question(db: Session, question_id: int, question_in: QuestionUpdate) -> Optional[Question]:
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            return None

        update_data = question_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if isinstance(value, str):
                value = value.strip()
                if field == "correct_option":
                    value = value.upper()
            setattr(question, field, value)

        question.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(question)
        return question

    @staticmethod
    def delete_question(db: Session, question_id: int) -> bool:
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            return False

        quiz_id = question.quiz_id
        db.delete(question)
        db.flush()

        # Re-index remaining questions to ensure continuous 1..N order
        remaining = db.query(Question).filter(Question.quiz_id == quiz_id).order_by(
            Question.question_order.asc()
        ).all()
        for idx, q in enumerate(remaining, start=1):
            q.question_order = idx

        db.commit()
        return True

    @staticmethod
    def reorder_questions(db: Session, quiz_id: int, orders: List[QuestionReorderItem]) -> bool:
        # Validate that all questions belong to the quiz
        question_ids = [item.question_id for item in orders]
        questions = db.query(Question).filter(
            Question.quiz_id == quiz_id,
            Question.id.in_(question_ids)
        ).all()

        if len(questions) != len(orders):
            raise ValueError("Some question IDs do not belong to this quiz")

        # Temporarily shift orders to avoid unique constraint collision
        for q in questions:
            q.question_order = q.question_order + 100000
        db.flush()

        order_map = {item.question_id: item.question_order for item in orders}
        for q in questions:
            q.question_order = order_map[q.id]
        
        db.commit()
        return True


quiz_service = QuizService()
