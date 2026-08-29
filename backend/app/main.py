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
    # Startup: ensure tables exist in dev/sqlite
    Base.metadata.create_all(bind=engine)
    logger.info("SBK Quiz Analyzer backend successfully started.")
    yield
    # Shutdown logic if needed
    logger.info("SBK Quiz Analyzer backend shutting down.")


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
