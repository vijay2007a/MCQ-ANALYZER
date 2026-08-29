import html
from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, field_validator, ConfigDict


class QuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_text: str = Field(..., min_length=5, max_length=2000)
    option_a: str = Field(..., min_length=1, max_length=1000)
    option_b: str = Field(..., min_length=1, max_length=1000)
    option_c: str = Field(..., min_length=1, max_length=1000)
    option_d: str = Field(..., min_length=1, max_length=1000)
    correct_option: str = Field(..., min_length=1, max_length=1)
    explanation: str = Field(..., min_length=5, max_length=2000)
    question_order: Optional[int] = Field(None, ge=1)

    @field_validator("question_text", "option_a", "option_b", "option_c", "option_d", "explanation")
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        return html.escape(v.strip())

    @field_validator("correct_option")
    @classmethod
    def validate_correct_option(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in ["A", "B", "C", "D"]:
            raise ValueError("Correct option must be one of: A, B, C, D")
        return v_upper


class QuestionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_text: Optional[str] = Field(None, min_length=5, max_length=2000)
    option_a: Optional[str] = Field(None, min_length=1, max_length=1000)
    option_b: Optional[str] = Field(None, min_length=1, max_length=1000)
    option_c: Optional[str] = Field(None, min_length=1, max_length=1000)
    option_d: Optional[str] = Field(None, min_length=1, max_length=1000)
    correct_option: Optional[str] = Field(None, min_length=1, max_length=1)
    explanation: Optional[str] = Field(None, min_length=5, max_length=2000)
    question_order: Optional[int] = Field(None, ge=1)

    @field_validator("question_text", "option_a", "option_b", "option_c", "option_d", "explanation")
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        return html.escape(v.strip()) if v is not None else v

    @field_validator("correct_option")
    @classmethod
    def validate_correct_option(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_upper = v.upper()
            if v_upper not in ["A", "B", "C", "D"]:
                raise ValueError("Correct option must be one of: A, B, C, D")
            return v_upper
        return v


class QuestionAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    quiz_id: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    explanation: str
    question_order: int
    created_at: datetime
    updated_at: datetime


class QuestionPlayerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_number: int
    total_questions: int
    question_text: str
    options: Dict[str, str]
    time_per_question: int


class QuestionReorderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: int
    question_order: int = Field(..., ge=1)


class QuestionReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orders: List[QuestionReorderItem]
