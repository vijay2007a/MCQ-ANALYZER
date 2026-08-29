# SBK QUIZ ANALYZER — Production Backend Engine

A robust, zero-trust, server-authoritative assessment engine built with **FastAPI**, **PostgreSQL / SQLAlchemy 2.x**, **Alembic**, **openpyxl**, and **Pydantic v2**.

Designed with the **Zero-Trust Frontend** principle: the client is never trusted for scores, response times, answer correctness, timer calculations, or session states.

---

## Key Features

- 🛡️ **Zero-Trust Anti-Cheat**: Server-authoritative timer; questions never leak correct options or explanations to players; out-of-order and replayed requests are strictly rejected.
- ⚡ **Dynamic Speed Scoring Engine**: Server-calculated response time down to milliseconds with customizable tiered rewards (e.g. 0–2s: 100pts, 2–5s: 90pts, 5–10s: 75pts, etc.).
- 🔒 **Security & Authentication**: Argon2id/Bcrypt password hashing, signed JWT tokens for admins, cryptographically random player session tokens with SHA-256 database hashing.
- 📊 **Deterministic Leaderboard**: Multi-tier tie-breaking algorithm (`Score DESC` $\rightarrow$ `Time ASC` $\rightarrow$ `Completed Timestamp ASC`).
- 📑 **Professional Excel (.xlsx) Exports**: Multi-sheet workbooks (Summary KPIs, Player Results, Question Breakdown) formatted with `openpyxl`.
- 🔄 **Idempotency & Concurrency**: Unique constraints and idempotent handling on `(session_id, question_id)` and `(session_id, idempotency_key)`.
- 🚦 **Rate Limiting**: Sliding-window rate limiter with Redis support and in-memory fallback.
- 🗄️ **Database Migrations**: Complete Alembic integration with PostgreSQL and SQLite support.

---

## Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI (Asynchronous ASGI)
- **Database**: PostgreSQL (Production) / SQLite (Development/Tests) via SQLAlchemy 2.0
- **Migrations**: Alembic
- **Validation**: Pydantic v2
- **Auth & Security**: Bcrypt / Argon2id, PyJWT, Secrets
- **Spreadsheet Generation**: openpyxl
- **Testing**: pytest, pytest-asyncio, httpx

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                     # FastAPI application factory, middlewares & exception handlers
│   ├── cli.py                      # Administrative CLI commands
│   ├── core/
│   │   ├── config.py               # Pydantic BaseSettings
│   │   ├── database.py             # SQLAlchemy 2.0 engine & session maker
│   │   ├── security.py             # Password hashing, JWT & session token hashing
│   │   └── rate_limit.py           # Sliding-window rate limiter (Redis / Memory)
│   ├── middleware/
│   │   └── security.py             # Security headers & structured JSON request logger
│   ├── models/
│   │   ├── admin.py                # Admin model
│   │   ├── quiz.py                 # Quiz model
│   │   ├── question.py             # Question model
│   │   ├── quiz_session.py         # QuizSession model
│   │   ├── answer.py               # QuizAttempt model
│   │   └── result.py               # QuizResult model
│   ├── schemas/
│   │   ├── auth.py                 # Auth schemas
│   │   ├── quiz.py                 # Quiz schemas
│   │   ├── question.py             # Question schemas (Admin vs Sanitized Player)
│   │   ├── session.py              # Session, Question & Answer submission schemas
│   │   ├── result.py               # Result schemas
│   │   └── leaderboard.py          # Leaderboard schemas
│   ├── services/
│   │   ├── auth_service.py         # Admin authentication & credentials
│   │   ├── quiz_service.py         # Quiz lifecycle, publishing validation, questions
│   │   ├── scoring_service.py      # Speed-based points calculation
│   │   ├── session_service.py      # Player session lifecycle & anti-cheat engine
│   │   ├── result_service.py       # Aggregated results calculation
│   │   ├── leaderboard_service.py  # Deterministic leaderboard rankings
│   │   └── export_service.py       # openpyxl multi-sheet workbook generation
│   └── api/
│       ├── deps.py                 # Dependency injection (Auth, DB, Sessions)
│       ├── health.py               # /api/health
│       ├── auth.py                 # /api/admin/auth/*
│       ├── admin.py                # /api/admin/*
│       ├── quizzes.py              # /api/admin/quizzes/*
│       ├── player.py               # /api/player/quizzes/*
│       ├── sessions.py             # /api/player/sessions/*
│       ├── results.py              # /api/results & /api/player/sessions/{id}/result
│       ├── leaderboard.py          # /api/leaderboard
│       └── exports.py              # /api/admin/results/export
├── alembic/                        # Alembic migrations
├── tests/                          # Automated pytest suite
├── requirements.txt
├── .env.example
└── README.md
```

---

## Installation & Setup

### 1. Clone & Install Dependencies
```bash
cd backend
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Environment Configuration
Copy `.env.example` to `.env` and configure your settings:
```bash
cp .env.example .env
```

### 3. Database Migrations
Run Alembic migrations to create tables:
```bash
alembic upgrade head
```

### 4. Create Initial Admin User
Use the built-in CLI to securely initialize your first admin account without hardcoded credentials:
```bash
python -m app.cli create-admin --email admin@example.com --password "SecurePassword123!"
```

### 5. Start Development Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- Health Check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

## Running the Automated Test Suite

Run the full test suite with verbose reporting:
```bash
pytest tests/ -v
```

---

## API Overview

### Player Endpoints
- `GET /api/player/quizzes`: List published quizzes
- `GET /api/player/quizzes/{id}`: Get quiz rules & time limits
- `POST /api/player/quizzes/{id}/start`: Start session $\rightarrow$ returns session token & sanitized first question
- `GET /api/player/sessions/{id}/question`: Get current active question (sanitized)
- `POST /api/player/sessions/{id}/answer`: Submit answer $\rightarrow$ returns server score, correctness & explanation
- `GET /api/player/sessions/{id}/status`: Get session progress
- `GET /api/player/sessions/{id}/result`: Get player's final result & rank
- `GET /api/leaderboard`: Public deterministic leaderboard

### Admin Endpoints
- `POST /api/admin/auth/login`: Admin login
- `GET /api/admin/auth/me`: Profile
- `POST /api/admin/auth/change-password`: Update password
- `GET /api/admin/quizzes`: List all quizzes
- `POST /api/admin/quizzes`: Create quiz draft
- `GET /api/admin/quizzes/{id}`: Quiz details with full question key
- `PUT /api/admin/quizzes/{id}`: Edit quiz & scoring rules
- `DELETE /api/admin/quizzes/{id}`: Delete / Archive quiz
- `POST /api/admin/quizzes/{id}/publish`: Validate & publish quiz
- `POST /api/admin/quizzes/{id}/unpublish`: Unpublish quiz
- `POST /api/admin/quizzes/{id}/duplicate`: Clone quiz
- `POST /api/admin/quizzes/{id}/questions`: Add question
- `PUT /api/admin/quizzes/questions/{id}`: Edit question
- `DELETE /api/admin/quizzes/questions/{id}`: Delete question
- `POST /api/admin/quizzes/{id}/questions/reorder`: Reorder questions
- `GET /api/admin/results`: Paginated & filtered results
- `GET /api/admin/results/export`: Download Excel (.xlsx) report
- `GET /api/admin/quizzes/{id}/results/export`: Download Quiz-specific Excel report

---

## Excel Export Structure

The exported `.xlsx` workbook includes 3 formatted sheets:
1. **Summary**: Overall KPI dashboard (Total attempts, unique participants, average score, accuracy, completion time).
2. **Results**: Complete ranked participant records with scores, times, and completion dates.
3. **Question Performance**: Question-by-question analytics (accuracy %, total answers, average response time).

---

## Security & Anti-Cheat Guarantees

1. **Answer Key Protection**: Correct answers and explanations are stored server-side and never sent in question payloads before submission.
2. **Server-Authoritative Timing**: Elapsed time is computed directly on the backend using UTC server timestamps (`now - question_start_time`).
3. **Replay & Concurrency Prevention**: Database-level unique constraints and idempotency keys ensure no duplicate points or race conditions.
4. **Sequence Enforcement**: Questions must be answered in strict sequential order (1, 2, 3...); jumping or skipping questions is rejected.
5. **Session Expiry**: Submissions after the allocated session expiration window are rejected.
