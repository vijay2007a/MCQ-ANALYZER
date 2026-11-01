from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class LeaderboardEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    player_name: str
    register_number: Optional[str] = None
    quiz_id: int
    quiz_title: str
    total_score: int
    marks_obtained: int = 0
    total_marks: int = 0
    correct_answers: int = 0
    total_questions: int = 0
    accuracy: float
    total_time_ms: int
    completed_at: datetime


class LeaderboardResponse(BaseModel):
    items: List[LeaderboardEntry]
    total: int
    quiz_id: Optional[int] = None
    quiz_title: Optional[str] = None
    page: int = 1
    size: int = 50
