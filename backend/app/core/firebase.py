"""Server-only Firebase SDK setup. Browser API keys are not server credentials."""
import json
from functools import lru_cache

from app.core.config import settings


@lru_cache(maxsize=1)
def firebase_app():
    import firebase_admin
    from firebase_admin import credentials

    credential = None
    if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        credential = credentials.Certificate(json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON.get_secret_value()))
    return firebase_admin.initialize_app(
        credential, {"projectId": settings.FIREBASE_PROJECT_ID}, name="quizmaster-backend"
    )


def firestore_client():
    from firebase_admin import firestore
    return firestore.client(app=firebase_app())


def verify_admin_identity(id_token):
    from firebase_admin import auth
    from fastapi import HTTPException

    try:
        identity = auth.verify_id_token(id_token, app=firebase_app(), check_revoked=True)
    except (auth.InvalidIdTokenError, auth.RevokedIdTokenError, auth.UserDisabledError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid Firebase sign-in")
    if identity.get("admin") is not True:
        raise HTTPException(status_code=403, detail="Administrator access required")
    if not identity.get("email") or not identity.get("uid"):
        raise HTTPException(status_code=403, detail="Administrator identity is incomplete")
    return identity


def provision_firebase_admin(email, password):
    from firebase_admin import auth
    firebase = firebase_app()
    try:
        user = auth.get_user_by_email(email, app=firebase)
        auth.update_user(user.uid, password=password, app=firebase)
    except auth.UserNotFoundError:
        user = auth.create_user(email=email, password=password, app=firebase)
    auth.set_custom_user_claims(user.uid, {**(user.custom_claims or {}), "admin": True}, app=firebase)
    return user.uid
