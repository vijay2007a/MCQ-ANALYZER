from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_admin
from app.models.admin import Admin
from app.schemas.auth import AdminResponse, CreateAdminRequest, AdminSetupRequest
from app.services.auth_service import auth_service
from app.core.config import settings

router = APIRouter(prefix="/admin", tags=["Admin Management"])


@router.post("/setup", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
def initial_admin_setup(setup_data: AdminSetupRequest, db: Session = Depends(get_db)):
    """
    Bootstrap the initial admin account.
    Allowed only if no active admins exist or in development mode.
    """
    admin_count = db.query(Admin).count()
    if admin_count > 0:
        # If admins already exist, reject setup
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Initial setup has already been completed. Contact an existing admin.",
        )

    try:
        admin = auth_service.create_admin(
            db,
            email=setup_data.email,
            password=setup_data.password,
            role="ADMIN",
        )
        return admin
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/admins", response_model=List[AdminResponse])
def list_admins(current_admin: Admin = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    List all admin users. Requires Admin authentication.
    """
    return db.query(Admin).order_by(Admin.created_at.desc()).all()


@router.post("/admins", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
def create_new_admin(
    admin_in: CreateAdminRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Create a new admin user account. Requires Admin authentication.
    """
    try:
        new_admin = auth_service.create_admin(
            db,
            email=admin_in.email,
            password=admin_in.password,
            role=admin_in.role,
        )
        return new_admin
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
