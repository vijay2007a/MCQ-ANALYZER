from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class PlayerResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: int
    player_name: str
    register_number: Optional[str] = None
    quiz_id: int
    quiz_title: str
    total_score: int
    marks_obtained: int = 0
    total_marks: int = 0
    correct_answers: int
    incorrect_answers: int
    unanswered_questions: int = 0
    total_questions: int
    accuracy: float
    total_time_ms: int
    average_response_time_ms: int
    warnings_count: int = 0
    quiz_status: str = "COMPLETED"
    results_published: bool = True
    completed_at: datetime
    rank: Optional[int] = None


class AdminResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    player_name: str
    register_number: Optional[str] = None
    quiz_id: int
    quiz_title: str
    total_score: int
    marks_obtained: int = 0
    total_marks: int = 0
    correct_answers: int
    incorrect_answers: int
    unanswered_questions: int = 0
    total_questions: int
    accuracy: float
    total_time_ms: int
    average_response_time_ms: int
    warnings_count: int = 0
    quiz_status: str = "COMPLETED"
    completed_at: datetime
    rank: Optional[int] = None


class AdminResultsListResponse(BaseModel):
    items: List[AdminResultResponse]
    total: int
    page: int
    size: int
    total_pages: int
