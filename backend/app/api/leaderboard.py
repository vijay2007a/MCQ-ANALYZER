from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.schemas.leaderboard import LeaderboardResponse
from app.services.leaderboard_service import leaderboard_service

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])


@router.get("", response_model=LeaderboardResponse)
def get_leaderboard(
    quiz_id: Optional[int] = Query(None, description="Filter leaderboard by specific quiz ID"),
    date_from: Optional[datetime] = Query(None, description="Include scores from this datetime onwards"),
    date_to: Optional[datetime] = Query(None, description="Include scores up to this datetime"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Get deterministic quiz leaderboard.
    Ranking criteria:
    1. Highest total score
    2. Lowest total time in milliseconds
    3. Earliest completion timestamp
    """
    skip = (page - 1) * size
    entries, total, quiz_title = leaderboard_service.get_leaderboard(
        db,
        quiz_id=quiz_id,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=size,
    )

    return LeaderboardResponse(
        items=entries,
        total=total,
        quiz_id=quiz_id,
        quiz_title=quiz_title,
        page=page,
        size=size,
    )
