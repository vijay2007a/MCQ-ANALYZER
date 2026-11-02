from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_admin
from app.core.rate_limit import rate_limit
from app.core.security import create_access_token
from app.models.admin import Admin
from app.schemas.auth import AdminLoginRequest, TokenResponse, AdminResponse, PasswordChangeRequest, FirebaseAuthLoginRequest
from app.services.auth_service import auth_service

router = APIRouter(prefix="/admin/auth", tags=["Admin Authentication"])


@router.post("/firebase-login", response_model=TokenResponse)
def admin_firebase_login(request: Request, login_data: FirebaseAuthLoginRequest, db: Session = Depends(get_db)):
    """Firebase student identities cannot authenticate as administrators."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access requires a provisioned email and password account.",
    )


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit("admin_login", max_requests=10, window_seconds=60))])
def admin_login(request: Request, login_data: AdminLoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate an admin user and return a signed JWT access token.
    Rate limited: 10 attempts per minute. Generic error to prevent email enumeration.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent")

    admin = auth_service.authenticate_admin(
        db,
        email=login_data.email,
        password=login_data.password,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(subject=admin.id, role=admin.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=admin.role,
        email=admin.email,
    )


@router.get("/me", response_model=AdminResponse)
def get_current_admin_profile(current_admin: Admin = Depends(get_current_admin)):
    """
    Get profile information of the currently authenticated admin.
    """
    return current_admin


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_admin_password(
    pwd_data: PasswordChangeRequest,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Change the current admin's password.
    """
    success = auth_service.change_password(
        db,
        admin=current_admin,
        current_password=pwd_data.current_password,
        new_password=pwd_data.new_password,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password verification failed",
        )
    return {"message": "Password updated successfully"}


@router.post("/logout")
def admin_logout(current_admin: Admin = Depends(get_current_admin)):
    """
    Acknowledge admin logout.
    """
    return {"message": "Logged out successfully"}
