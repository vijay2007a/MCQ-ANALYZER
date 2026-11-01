import html
from datetime import datetime
from typing import Optional, Dict, List
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.schemas.question import QuestionPlayerResponse


class StartQuizRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_name: str = Field(..., min_length=2, max_length=50)
    register_number: Optional[str] = Field(default=None, max_length=50)
    access_code: Optional[str] = Field(default=None, max_length=50)

    @field_validator("player_name")
    @classmethod
    def sanitize_player_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Player name cannot be empty or only spaces")
        # Sanitize HTML tags to prevent stored XSS
        return html.escape(cleaned)

    @field_validator("register_number")
    @classmethod
    def sanitize_register_number(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().upper()
        return html.escape(cleaned) if cleaned else None


class StartQuizResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int
    session_token: str
    quiz_id: int
    quiz_title: str
    register_number: Optional[str] = None
    time_per_question: int
    duration_minutes: int = 15
    marks_per_question: int = 1
    negative_marks: int = 0
    started_at: datetime
    expires_at: datetime
    total_questions: int
    first_question: Optional[QuestionPlayerResponse] = None
    questions: List[QuestionPlayerResponse] = Field(default_factory=list)
    saved_answers: Dict[int, str] = Field(default_factory=dict)
    marked_for_review: List[int] = Field(default_factory=list)


class SubmitAnswerRequest(BaseModel):
    """
    CRITICAL: Untrusted payload.
    Enforces extra='forbid' so students cannot send fake score, points, or elapsed_time fields.
    """
    model_config = ConfigDict(extra="forbid")

    question_order: int = Field(..., ge=1)
    selected_option: str = Field(..., min_length=1, max_length=1)
    idempotency_key: str = Field(..., min_length=8, max_length=100)

    @field_validator("selected_option")
    @classmethod
    def validate_option(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in ["A", "B", "C", "D"]:
            raise ValueError("Selected option must be one of: A, B, C, D")
        return v_upper


class SubmitAnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_correct: bool
    points_earned: int
    response_time_ms: int
    correct_option: str
    explanation: str
    current_score: int
    is_quiz_completed: bool
    next_question_available: bool
    next_question: Optional[QuestionPlayerResponse] = None


class SessionStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int
    status: str
    player_name: str
    register_number: Optional[str] = None
    quiz_id: int
    quiz_title: str
    current_question_order: int
    total_questions: int
    time_per_question: int = 30
    duration_minutes: int = 15
    marks_per_question: int = 1
    negative_marks: int = 0
    is_completed: bool
    started_at: datetime
    expires_at: datetime
    remaining_seconds: int = 300
    questions: List[QuestionPlayerResponse] = Field(default_factory=list)
    saved_answers: Dict[int, str] = Field(default_factory=dict)
    marked_for_review: List[int] = Field(default_factory=list)
    warnings_count: int = 0


class SaveAnswerDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_order: int = Field(..., ge=1)
    selected_option: Optional[str] = Field(default=None, max_length=1)
    marked_for_review: Optional[bool] = None

    @field_validator("selected_option")
    @classmethod
    def validate_option(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v_upper = v.upper()
        if v_upper not in ["A", "B", "C", "D"]:
            raise ValueError("Selected option must be one of: A, B, C, D")
        return v_upper


class FinishQuizRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answers: Optional[Dict[str, str]] = None
    marked_for_review: Optional[List[int]] = None
    reason: Optional[str] = "MANUAL_SUBMIT"


class PlayerEventRequest(BaseModel):
    """
    Schema for logging anti-cheating, clipboard, and security telemetry events.
    """
    model_config = ConfigDict(extra="ignore")

    event_type: str = Field(..., min_length=2, max_length=100)
    question_order: Optional[int] = Field(None, ge=1)
    details: Optional[dict] = Field(default_factory=dict)


class PlayerEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    event_type: str
    recorded_at: datetime
