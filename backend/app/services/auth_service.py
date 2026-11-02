from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.admin import Admin
from app.core.security import hash_password, verify_password
from app.services.audit_service import audit_service


class AuthService:
    @staticmethod
    def get_admin_by_email(db: Session, email: str) -> Optional[Admin]:
        return db.query(Admin).filter(Admin.email == email.lower().strip()).first()

    @staticmethod
    def get_admin_by_id(db: Session, admin_id: int) -> Optional[Admin]:
        return db.query(Admin).filter(Admin.id == admin_id).first()

    @staticmethod
    def authenticate_admin(
        db: Session,
        email: str,
        password: str,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[Admin]:
        admin = AuthService.get_admin_by_email(db, email)
        if not admin:
            audit_service.log_event(
                db,
                event_type="ADMIN_LOGIN_FAILED",
                actor_type="ANONYMOUS",
                actor_id=email.lower().strip(),
                ip_address=client_ip,
                user_agent=user_agent,
                resource_type="ADMIN",
                details={"reason": "User not found"},
            )
            return None
        
        if not verify_password(password, admin.password_hash):
            audit_service.log_event(
                db,
                event_type="ADMIN_LOGIN_FAILED",
                actor_type="ADMIN",
                actor_id=str(admin.id),
                ip_address=client_ip,
                user_agent=user_agent,
                resource_type="ADMIN",
                resource_id=str(admin.id),
                details={"reason": "Invalid password verification"},
            )
            return None

        if not admin.is_active:
            audit_service.log_event(
                db,
                event_type="ADMIN_LOGIN_DEACTIVATED",
                actor_type="ADMIN",
                actor_id=str(admin.id),
                ip_address=client_ip,
                user_agent=user_agent,
                resource_type="ADMIN",
                resource_id=str(admin.id),
                details={"reason": "Account is deactivated"},
            )
            return None
        
        # Update last login timestamp
        admin.last_login_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(admin)

        audit_service.log_event(
            db,
            event_type="ADMIN_LOGIN_SUCCESS",
            actor_type="ADMIN",
            actor_id=str(admin.id),
            ip_address=client_ip,
            user_agent=user_agent,
            resource_type="ADMIN",
            resource_id=str(admin.id),
            details={"email": admin.email, "role": admin.role},
        )
        return admin

    @staticmethod
    def create_admin(
        db: Session,
        email: str,
        password: str,
        role: str = "ADMIN",
        creator_admin_id: Optional[int] = None,
    ) -> Admin:
        existing = AuthService.get_admin_by_email(db, email)
        if existing:
            raise ValueError("Admin with this email already exists")
        
        from app.core.config import settings
        if settings.DATABASE_BACKEND == "firestore":
            from app.core.firebase import provision_firebase_admin
            provision_firebase_admin(email.lower().strip(), password)
        hashed = hash_password(password)
        admin = Admin(
            email=email.lower().strip(),
            password_hash=hashed,
            role=role,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        audit_service.log_event(
            db,
            event_type="ADMIN_CREATED",
            actor_type="ADMIN" if creator_admin_id else "SYSTEM",
            actor_id=str(creator_admin_id) if creator_admin_id else "BOOTSTRAP",
            resource_type="ADMIN",
            resource_id=str(admin.id),
            details={"created_email": admin.email, "role": admin.role},
        )
        return admin

    @staticmethod
    def change_password(db: Session, admin: Admin, current_password: str, new_password: str) -> bool:
        if not verify_password(current_password, admin.password_hash):
            audit_service.log_event(
                db,
                event_type="ADMIN_PASSWORD_CHANGE_FAILED",
                actor_type="ADMIN",
                actor_id=str(admin.id),
                resource_type="ADMIN",
                resource_id=str(admin.id),
                details={"reason": "Incorrect current password"},
            )
            return False
        
        admin.password_hash = hash_password(new_password)
        admin.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(admin)

        audit_service.log_event(
            db,
            event_type="ADMIN_PASSWORD_CHANGE_SUCCESS",
            actor_type="ADMIN",
            actor_id=str(admin.id),
            resource_type="ADMIN",
            resource_id=str(admin.id),
        )
        return True


auth_service = AuthService()
