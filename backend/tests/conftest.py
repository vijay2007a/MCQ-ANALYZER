import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment
os.environ["ENVIRONMENT"] = "testing"
os.environ["RATE_LIMIT_ENABLED"] = "false"

from app.core.database import Base, get_db
from app.core.security import hash_password, create_access_token
from app.models.admin import Admin
from app.models.quiz import Quiz
from app.models.question import Question
from app.main import app

# Use in-memory SQLite database with StaticPool so all connections share the same memory DB
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_admin(db) -> Admin:
    admin = Admin(
        email="admin@test.com",
        password_hash=hash_password("AdminSecret123!"),
        role="ADMIN",
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@pytest.fixture
def admin_token(test_admin) -> str:
    return create_access_token(subject=test_admin.id, role=test_admin.role)


@pytest.fixture
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def published_quiz(db, test_admin) -> Quiz:
    quiz = Quiz(
        title="Computer Science Fundamentals",
        description="Core CS concepts and algorithms",
        difficulty="MEDIUM",
        status="PUBLISHED",
        time_per_question=30,
        maximum_attempts=3,
        created_by=test_admin.id,
    )
    db.add(quiz)
    db.flush()

    q1 = Question(
        quiz_id=quiz.id,
        question_text="What is the time complexity of binary search on a sorted array?",
        option_a="O(n)",
        option_b="O(log n)",
        option_c="O(n^2)",
        option_d="O(1)",
        correct_option="B",
        explanation="Binary search halves the search space each step, giving logarithmic time complexity O(log n).",
        question_order=1,
    )
    q2 = Question(
        quiz_id=quiz.id,
        question_text="Which data structure operates on a First-In, First-Out (FIFO) basis?",
        option_a="Stack",
        option_b="Tree",
        option_c="Queue",
        option_d="Graph",
        correct_option="C",
        explanation="A Queue operates on a First-In, First-Out (FIFO) principle.",
        question_order=2,
    )
    db.add_all([q1, q2])
    db.commit()
    db.refresh(quiz)
    return quiz
