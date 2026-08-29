from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class LeaderboardEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    player_name: str
    quiz_id: int
    quiz_title: str
    total_score: int
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
