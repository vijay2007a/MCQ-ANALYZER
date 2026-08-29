import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog

logger = logging.getLogger("sbk_quiz.audit")

SENSITIVE_KEYS = {"password", "new_password", "current_password", "token", "session_token", "secret", "secret_key", "password_hash"}


def sanitize_details(details: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not details:
        return None
    cleaned = {}
    for k, v in details.items():
        if k.lower() in SENSITIVE_KEYS:
            cleaned[k] = "[REDACTED]"
        elif isinstance(v, dict):
            cleaned[k] = sanitize_details(v)
        else:
            cleaned[k] = v
    return cleaned


class AuditService:
    @staticmethod
    def log_event(
        db: Session,
        event_type: str,
        actor_type: str = "SYSTEM",
        actor_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Record a security or administrative audit event.
        Ensures all sensitive data is sanitized before saving.
        """
        safe_details = sanitize_details(details)
        log_entry = AuditLog(
            event_type=event_type,
            actor_type=actor_type,
            actor_id=str(actor_id) if actor_id is not None else None,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else None,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=safe_details,
            created_at=datetime.now(timezone.utc),
        )
        db.add(log_entry)
        try:
            db.commit()
            db.refresh(log_entry)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to write audit log: {e}")

        logger.info(f"AUDIT_EVENT: type={event_type} actor={actor_type}:{actor_id} resource={resource_type}:{resource_id}")
        return log_entry

    @staticmethod
    def get_audit_logs(
        db: Session,
        event_type: Optional[str] = None,
        actor_type: Optional[str] = None,
        actor_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[AuditLog], int]:
        query = db.query(AuditLog)
        if event_type:
            query = query.filter(AuditLog.event_type == event_type)
        if actor_type:
            query = query.filter(AuditLog.actor_type == actor_type)
        if actor_id:
            query = query.filter(AuditLog.actor_id == actor_id)
        if start_date:
            query = query.filter(AuditLog.created_at >= start_date)
        if end_date:
            query = query.filter(AuditLog.created_at <= end_date)

        total = query.count()
        logs = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
        return logs, total


audit_service = AuditService()
