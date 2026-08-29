from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_admin
from app.models.admin import Admin
from app.services.audit_service import audit_service

router = APIRouter(prefix="/admin/audit-logs", tags=["Admin Audit & Security Logs"])


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    actor_type: str
    actor_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Optional[dict]
    created_at: datetime


class AuditLogsListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    size: int
    total_pages: int


@router.get("", response_model=AuditLogsListResponse)
def list_audit_logs(
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g. ADMIN_LOGIN_FAILED, REPLAY_ATTEMPT)"),
    actor_type: Optional[str] = Query(None, description="Filter by actor type (ADMIN, PLAYER, SYSTEM)"),
    actor_id: Optional[str] = Query(None, description="Filter by actor ID"),
    start_date: Optional[datetime] = Query(None, description="Filter logs starting from datetime"),
    end_date: Optional[datetime] = Query(None, description="Filter logs up to datetime"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Query security and administrative audit logs. Requires Admin authentication.
    """
    skip = (page - 1) * size
    logs, total = audit_service.get_audit_logs(
        db,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=size,
    )

    items = [AuditLogResponse.model_validate(log) for log in logs]
    total_pages = (total + size - 1) // size if total > 0 else 1

    return AuditLogsListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        total_pages=total_pages,
    )
