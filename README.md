# SBK Quiz Analyzer — Academic MCQ Assessment Platform

A modern, full-stack MCQ Quiz Management & Real-Time Assessment Platform built for college faculty and students using **FastAPI**, **SQLAlchemy**, **Firebase Authentication**, **Cloud Firestore**, and **Tailwind CSS**.

---

## Key Features

### Faculty / Admin Portal
- **7-Section Control Center**:
  1. **Dashboard**: Total quizzes, active quizzes, completed quizzes, total participants, average marks, quiz participation charts, performance distribution, and recent submission feed.
  2. **Create Quiz & Word (`.docx`) Upload**: 7-step guided workflow to enter quiz title, upload a Microsoft Word (`.docx`) document, automatically extract numbered MCQs (`1.`, `Q1.`), options (`A–D`), and answers (`Answer: A`), preview/edit inline, configure timing/marks/access code, and publish.
  3. **My Quizzes**: Search and filter quizzes, preview/edit questions, toggle result visibility, share QR codes and join links, duplicate, publish/close, or delete quizzes.
  4. **Live Quiz Control Room**: Real-time monitoring of joined, attempting, submitted, and disconnected students, live standings, and instant start/close controls.
  5. **Results & Gradebook**: Tie-breaker ranked student results and one-click `.xlsx` Excel export.
  6. **Proctoring & Audit Logs**: Real-time anti-cheat warning logs (tab switches, fullscreen exits, clipboard attempts) and server security audit trail.
  7. **Settings**: Light/Dark/System theme controls and password management.

### Student Assessment Portal
- **Distraction-Free Quiz Player**:
  - Join with Full Name, Register Number, and optional Quiz Access Code (or Google Sign-In).
  - Interactive Question Navigation Palette (Answered, Unanswered, Marked for Review).
  - Automatic server-side draft saving on every selection and full browser refresh recovery.
  - Server-enforced countdown timer with automatic submission on timeout.
- **Deterministic Tie-Breaker Leaderboard**:
  1. Higher marks rank higher.
  2. Faster completion time breaks ties.
  3. Identical marks and completion time share the same rank.

### Firebase Integration (`mcq-analyzer-16a47`)
- **Firebase Authentication**: Email/Password Sign-In & Sign-Up and Google Sign-In.
- **Cloud Firestore**: Real-time synchronization and hardened security rules (`firestore.rules`).

---

## Project Structure

```text
├── backend/
│   ├── alembic/                  # Database migrations
│   ├── app/
│   │   ├── api/                  # FastAPI route handlers (auth, admin, quizzes, player, sessions, results, leaderboard, exports, audit)
│   │   ├── core/                 # Config, database, JWT/password security, rate limiting
│   │   ├── middleware/           # Security headers & request logging
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── schemas/              # Pydantic v2 request/response schemas
│   │   ├── services/             # Business logic, DOCX parser, Excel exporter, scoring & tie-breaker engine
│   │   └── main.py               # FastAPI application entrypoint
│   ├── static/
│   │   └── index.html            # Responsive Single-Page Application (Student & Faculty Portals)
│   ├── tests/                    # Automated Pytest suite (62 tests)
│   ├── Dockerfile                # Container build configuration
│   └── requirements.txt          # Python dependencies
├── .firebaserc                   # Firebase project configuration (mcq-analyzer-16a47)
├── firebase.json                 # Firebase Auth, Firestore, and Hosting configuration
├── firestore.rules               # Hardened Cloud Firestore Security Rules
└── pytest.ini                    # Pytest configuration
```

---

## Quick Start (Local Development)

1. **Install dependencies**:
   ```bash
   pip install -r backend/requirements.txt
   ```

2. **Start the server**:
   ```bash
   python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
   ```

3. **Open in browser**:
   - Application: `http://localhost:8000`

4. **Run the test suite**:
   ```bash
   python -m pytest backend/tests/ -v
   ```

