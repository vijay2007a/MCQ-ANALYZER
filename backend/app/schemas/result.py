from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class PlayerResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: int
    player_name: str
    quiz_id: int
    quiz_title: str
    total_score: int
    correct_answers: int
    incorrect_answers: int
    total_questions: int
    accuracy: float
    total_time_ms: int
    average_response_time_ms: int
    completed_at: datetime
    rank: Optional[int] = None


class AdminResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    player_name: str
    quiz_id: int
    quiz_title: str
    total_score: int
    correct_answers: int
    incorrect_answers: int
    total_questions: int
    accuracy: float
    total_time_ms: int
    average_response_time_ms: int
    completed_at: datetime


class AdminResultsListResponse(BaseModel):
    items: List[AdminResultResponse]
    total: int
    page: int
    size: int
    total_pages: int
