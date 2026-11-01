import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import Base, engine
from app.middleware.security import SecurityHeadersMiddleware, RequestLoggingMiddleware

from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.quizzes import router as quizzes_router
from app.api.player import router as player_router
from app.api.sessions import router as sessions_router
from app.api.results import router as results_router
from app.api.leaderboard import router as leaderboard_router
from app.api.exports import router as exports_router
from app.api.audit import router as audit_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sbk_quiz.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables exist in dev/sqlite and apply safe additive column migrations
    Base.metadata.create_all(bind=engine)
    _run_safe_column_migrations(engine)
    _ensure_default_admins()
    logger.info("SBK Quiz Analyzer backend successfully started.")
    yield
    # Shutdown logic if needed
    logger.info("SBK Quiz Analyzer backend shutting down.")


def _ensure_default_admins():
    """Ensure the primary admin account (vijay2007a@gmail.com / 12345678) exists and is active."""
    from app.core.database import SessionLocal
    from app.models.admin import Admin
    from app.core.security import hash_password, verify_password
    db = SessionLocal()
    try:
        target_email = "vijay2007a@gmail.com"
        target_pass = "12345678"
        admin = db.query(Admin).filter(Admin.email == target_email).first()
        if not admin:
            admin = Admin(
                email=target_email,
                password_hash=hash_password(target_pass),
                role="ADMIN",
                is_active=True,
            )
            db.add(admin)
            db.commit()
        else:
            updated = False
            if not verify_password(target_pass, admin.password_hash):
                admin.password_hash = hash_password(target_pass)
                updated = True
            if not admin.is_active:
                admin.is_active = True
                updated = True
            if updated:
                db.commit()
    except Exception as e:
        logger.warning(f"Default admin provisioning notice: {e}")
    finally:
        db.close()


def _run_safe_column_migrations(eng):
    """Safely adds any newly introduced columns to existing SQLite/PostgreSQL databases without data loss."""
    from sqlalchemy import inspect, text
    try:
        inspector = inspect(eng)
        migrations = {
            "quizzes": [
                ("duration_minutes", "INTEGER DEFAULT 15 NOT NULL"),
                ("marks_per_question", "INTEGER DEFAULT 1 NOT NULL"),
                ("negative_marks", "INTEGER DEFAULT 0 NOT NULL"),
                ("access_code", "VARCHAR(50)"),
                ("randomize_questions", "BOOLEAN DEFAULT 0 NOT NULL"),
                ("randomize_options", "BOOLEAN DEFAULT 0 NOT NULL"),
                ("results_published", "BOOLEAN DEFAULT 1 NOT NULL"),
            ],
            "quiz_sessions": [
                ("register_number", "VARCHAR(50)"),
                ("question_order_map", "JSON"),
                ("option_order_map", "JSON"),
                ("marked_for_review", "JSON"),
                ("warnings_count", "INTEGER DEFAULT 0 NOT NULL"),
            ],
            "quiz_results": [
                ("register_number", "VARCHAR(50)"),
                ("marks_obtained", "INTEGER DEFAULT 0 NOT NULL"),
                ("total_marks", "INTEGER DEFAULT 0 NOT NULL"),
                ("unanswered_questions", "INTEGER DEFAULT 0 NOT NULL"),
                ("warnings_count", "INTEGER DEFAULT 0 NOT NULL"),
                ("quiz_status", "VARCHAR(50) DEFAULT 'COMPLETED' NOT NULL"),
            ],
        }
        with eng.begin() as conn:
            for table_name, cols in migrations.items():
                if inspector.has_table(table_name):
                    existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
                    for col_name, col_def in cols:
                        if col_name not in existing_cols:
                            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))
    except Exception as e:
        logger.warning(f"Safe column migration notice: {e}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Zero-trust, server-authoritative backend engine for SBK Quiz Analyzer.",
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

# Custom Middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP_EXCEPTION",
            "message": exc.detail,
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        field_loc = " -> ".join([str(loc) for loc in err.get("loc", [])])
        errors.append(f"{field_loc}: {err.get('msg')}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "VALIDATION_ERROR",
            "message": "The submitted payload is invalid.",
            "details": errors,
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    logger.error(f"Database integrity violation: {str(exc.orig)}")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "DATABASE_CONFLICT",
            "message": "A database constraint or duplicate submission conflict occurred.",
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred. Please try again later.",
        },
    )


# API Routers
app.include_router(health_router, prefix=settings.API_V1_STR)
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(quizzes_router, prefix=settings.API_V1_STR)
app.include_router(player_router, prefix=settings.API_V1_STR)
app.include_router(sessions_router, prefix=settings.API_V1_STR)
app.include_router(results_router, prefix=settings.API_V1_STR)
app.include_router(leaderboard_router, prefix=settings.API_V1_STR)
app.include_router(exports_router, prefix=settings.API_V1_STR)
app.include_router(audit_router, prefix=settings.API_V1_STR)

# Static Files & Frontend SPA Mount
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    @app.get("/login")
    @app.get("/dashboard")
    @app.get("/admin")
    @app.get("/leaderboard")
    @app.get("/quizzes")
    def serve_frontend():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"service": settings.PROJECT_NAME, "version": settings.VERSION}
else:
    @app.get("/")
    def root():
        return {
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "health": "/api/health",
        }
