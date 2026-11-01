import html
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class ScoringTier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_time_s: float = Field(..., ge=0)
    max_time_s: float = Field(..., gt=0)
    points: int = Field(..., ge=0)


class ScoringConfigSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_points: int = Field(default=100, ge=10, le=1000)
    speed_scoring_enabled: bool = True
    wrong_answer_points: int = Field(default=0, le=0)
    tiers: List[ScoringTier] = Field(
        default_factory=lambda: [
            ScoringTier(min_time_s=0.0, max_time_s=2.0, points=100),
            ScoringTier(min_time_s=2.0, max_time_s=5.0, points=90),
            ScoringTier(min_time_s=5.0, max_time_s=10.0, points=75),
            ScoringTier(min_time_s=10.0, max_time_s=15.0, points=50),
            ScoringTier(min_time_s=15.0, max_time_s=20.0, points=25),
            ScoringTier(min_time_s=20.0, max_time_s=9999.0, points=10),
        ]
    )


class QuizCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    difficulty: str = Field(default="MEDIUM")
    time_per_question: int = Field(default=30, ge=5, le=300)
    duration_minutes: int = Field(default=15, ge=1, le=300)
    marks_per_question: int = Field(default=1, ge=1, le=100)
    negative_marks: int = Field(default=0, ge=0, le=100)
    access_code: Optional[str] = Field(default=None, max_length=50)
    randomize_questions: bool = Field(default=False)
    randomize_options: bool = Field(default=False)
    results_published: bool = Field(default=True)
    maximum_attempts: int = Field(default=0, ge=0, le=100)  # 0 for unlimited
    scoring_config: Optional[ScoringConfigSchema] = None

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str) -> str:
        return html.escape(v.strip())

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: Optional[str]) -> Optional[str]:
        return html.escape(v.strip()) if v else v

    @field_validator("access_code")
    @classmethod
    def sanitize_access_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().upper()
        return html.escape(cleaned) if cleaned else None

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        valid = ["EASY", "MEDIUM", "HARD", "EXPERT"]
        if v.upper() not in valid:
            raise ValueError(f"Difficulty must be one of {valid}")
        return v.upper()


class QuizUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    difficulty: Optional[str] = None
    time_per_question: Optional[int] = Field(None, ge=5, le=300)
    duration_minutes: Optional[int] = Field(None, ge=1, le=300)
    marks_per_question: Optional[int] = Field(None, ge=1, le=100)
    negative_marks: Optional[int] = Field(None, ge=0, le=100)
    access_code: Optional[str] = Field(None, max_length=50)
    randomize_questions: Optional[bool] = None
    randomize_options: Optional[bool] = None
    results_published: Optional[bool] = None
    maximum_attempts: Optional[int] = Field(None, ge=0, le=100)
    scoring_config: Optional[ScoringConfigSchema] = None

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: Optional[str]) -> Optional[str]:
        return html.escape(v.strip()) if v is not None else v

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: Optional[str]) -> Optional[str]:
        return html.escape(v.strip()) if v is not None else v

    @field_validator("access_code")
    @classmethod
    def sanitize_access_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().upper()
        return html.escape(cleaned) if cleaned else None

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid = ["EASY", "MEDIUM", "HARD", "EXPERT"]
            if v.upper() not in valid:
                raise ValueError(f"Difficulty must be one of {valid}")
            return v.upper()
        return v


class QuizAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    title: str
    description: Optional[str]
    difficulty: str
    status: str
    time_per_question: int
    duration_minutes: int = 15
    marks_per_question: int = 1
    negative_marks: int = 0
    access_code: Optional[str] = None
    randomize_questions: bool = False
    randomize_options: bool = False
    results_published: bool = True
    maximum_attempts: int
    scoring_config: Optional[Dict[str, Any]]
    created_by: Optional[int]
    question_count: int = 0
    participant_count: int = 0
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None


class QuizPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    title: str
    description: Optional[str]
    difficulty: str
    time_per_question: int
    duration_minutes: int = 15
    marks_per_question: int = 1
    negative_marks: int = 0
    requires_access_code: bool = False
    results_published: bool = True
    total_questions: int


class QuizPublishValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    errors: List[str] = []


class DocxParsedQuestionSchema(BaseModel):
    question_order: int = 1
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    explanation: str
    is_valid: bool = True
    validation_errors: List[str] = []


class DocxParseResponse(BaseModel):
    quiz_title: str
    total_parsed: int
    valid_questions_count: int
    errors: List[str] = []
    questions: List[DocxParsedQuestionSchema] = []
    is_valid: bool


class QuizImportDocxRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    difficulty: str = Field(default="MEDIUM")
    time_per_question: int = Field(default=30, ge=5, le=300)
    duration_minutes: int = Field(default=15, ge=1, le=300)
    marks_per_question: int = Field(default=1, ge=1, le=100)
    negative_marks: int = Field(default=0, ge=0, le=100)
    access_code: Optional[str] = Field(default=None, max_length=50)
    randomize_questions: bool = Field(default=False)
    randomize_options: bool = Field(default=False)
    results_published: bool = Field(default=True)
    maximum_attempts: int = Field(default=0, ge=0, le=100)
    publish_immediately: bool = Field(default=False)
    questions: List[DocxParsedQuestionSchema]
