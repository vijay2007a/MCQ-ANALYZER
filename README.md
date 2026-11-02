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


## Firebase Authentication and Firestore deployment

The default backend is now `DATABASE_BACKEND=firestore`. Firebase verifies email/password
and Google sign-in. Admin requests require a verified, non-revoked Firebase ID token
with a server-issued `admin: true` claim AND an active application administrator record.
Student Google sign-in never auto-provisions administrator access.

The server stores quizzes, questions, sessions, answers, results, administrators, and
audit records in `_quizmaster_backend/v1/<collection>/<id>`. Browsers cannot directly
read or write that namespace. The backend controls answers, scoring, archiving and
deletions. Firestore writes are atomic and reject stale updates with HTTP 409.

### Required setup

1. Ensure Firebase project `mcq-analyzer-16a47` is accessible to your Google account
   and has a Firestore Native database. Enable Email/Password and Google providers
   in Firebase Authentication, and add the deployment hostname to authorized domains.
2. Give the backend service account Firestore read/write and Firebase Authentication
   administration permissions (needed for initial admin provisioning). Configure these
   private Vercel environment variables:
   - `DATABASE_BACKEND=firestore`
   - `FIREBASE_PROJECT_ID=mcq-analyzer-16a47`
   - `FIREBASE_SERVICE_ACCOUNT_JSON`: the service account JSON, stored as a secret
   - `INITIAL_ADMIN_PASSWORD`: your chosen initial password, required only on first setup
3. Local server access can instead use `gcloud auth application-default login`.
   Browser Firebase config and its API key do not grant server access.
4. Publish `firestore.rules`. Its explicit server namespace deny rule is intentional:
   Firebase Admin SDK access is authorized by Google Cloud IAM, not client rules.
5. Redeploy. First startup provisions `admin123@gmail.com` in Firebase Auth, assigns
   the admin claim, and writes the application admin record and audit guard. Subsequent
   startups preserve password changes. Sign out and sign in again after claim changes.

The local code and tests do not prove live deployment access. At implementation time,
Google denied `vijay2007a@gmail.com` access to the configured project even after a fresh
sign-in. Project access and production credentials must be resolved before deployment.

### Existing data

Existing SQLite data is not silently imported or deleted. From the repository root:

```powershell
$env:PYTHONPATH = "backend"
python -m app.migrate_firestore --source sqlite:///./quizmaster.db
# Review counts, then copy into an EMPTY Firestore destination:
python -m app.migrate_firestore --source sqlite:///./quizmaster.db --apply
```

The migration preserves record IDs and relationships, skips the old SQL bootstrap
marker, and refuses an occupied destination. The original database remains untouched.
Only records still present in the source can be copied. Old temporary Vercel data may
need to be re-imported from its original Word file. Run migration before first startup.
Very large imports may exceed Firestore transaction size limits and fail atomically.

### Validation and operating limits

```powershell
python -m pytest backend/tests -q
$env:TEST_DOCUMENT_STORE = "1"
python -m pytest backend/tests -q
Remove-Item Env:TEST_DOCUMENT_STORE
```

The second run exercises the Firestore unit of work with an in-memory document transport,
including cross-session persistence and conflict rejection. It is not a live Firestore
integration test. Verify import, refresh from a second browser, student submission,
close/export and result deletion against the real project before release.

The adapter pushes a single equality filter into Firestore and does remaining sorting,
joins and uniqueness validation on the server. Collection revision checks prioritize
correctness but can return retryable conflicts under concurrent writes. Large classes
or large historical datasets need narrower query/transaction scopes and native indexes
before scaling; collection scans incur Firestore reads.

Legacy SQL mode remains available with `DATABASE_BACKEND=sql`; Vercel SQL mode requires
persistent PostgreSQL. The Firebase frontend is intended for Firestore mode.
