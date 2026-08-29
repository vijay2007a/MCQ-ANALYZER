from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_admin
from app.core.rate_limit import rate_limit
from app.models.admin import Admin
from app.models.quiz import Quiz
from app.services.export_service import export_service

router = APIRouter(prefix="/admin", tags=["Admin Exports"])


@router.get(
    "/results/export",
    dependencies=[Depends(rate_limit("export_results", max_requests=10, window_seconds=60))]
)
def export_all_quiz_results(
    quiz_id: Optional[int] = Query(None, description="Optional quiz ID filter"),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Download a formatted multi-sheet Excel (.xlsx) file containing summary KPIs,
    player results, and question breakdown for all or filtered quiz results.
    """
    if quiz_id:
        quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    excel_stream = export_service.generate_quiz_results_excel(db, quiz_id=quiz_id)
    
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"quiz_results_{quiz_id or 'all'}_{date_str}.xlsx"

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/quizzes/{quiz_id}/results/export",
    dependencies=[Depends(rate_limit("export_results", max_requests=10, window_seconds=60))]
)
def export_specific_quiz_results(
    quiz_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Download a formatted Excel file for a specific quiz.
    """
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    excel_stream = export_service.generate_quiz_results_excel(db, quiz_id=quiz_id)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"quiz_results_{quiz_id}_{date_str}.xlsx"

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
