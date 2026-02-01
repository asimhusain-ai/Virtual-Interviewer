# Virtual Interviewer

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.3.3-000?logo=flask)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-DB-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Deployed on Vercel](https://img.shields.io/badge/Deploy-Vercel-000?logo=vercel)](https://vercel.com/)

AI-assisted interview practice meets timed quizzes, real-time analytics, and admin tooling — all powered by a Flask backend and a lightweight JavaScript front-end.

---

## Table of Contents
- [Overview](#overview)
- [Feature Highlights](#feature-highlights)
- [Tech Stack](#tech-stack)
- [Architecture Overview](#architecture-overview)
- [API Surface](#api-surface)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Local Development](#local-development)
- [Running Tests](#running-tests)
- [Data & Assets](#data--assets)
- [Deployment](#deployment)
- [License](#license)

---

## Overview
Virtual Interviewer is a full-stack practice platform that delivers AI-generated interview sessions and dataset-driven quizzes. Users can speak or type their answers, receive structured feedback and tone analysis, review detailed histories, and climb a gamified leaderboard. Admins can manage accounts, reset credentials, and inspect activity, while the system enforces session limits, timed questions, and cached question pools for resilience.

Live instance: <https://intervbot.vercel.app>

---

## Feature Highlights

### AI Interview Mode
- Generates role- and difficulty-aware questions via OpenRouter prompts.
- Per-question timers (Easy 60s, Medium 90s, Hard 120s) with auto-submit on timeout.
- Typed answers, live speech recognition (Web Speech API), and optional text-to-speech playback.
- Evaluates responses with OpenRouter and captures tone using TextBlob sentiment analysis.
- Saves results for authenticated users to support longitudinal progress tracking.

### Timed Quiz Mode
- Curated multiple-choice questions from questions.json with deduplication and role/difficulty filters.
- API-first retrieval with automatic fallback to the local dataset if the API is unavailable.
- Auto-advance timers, score breakdowns, and optional PDF exports (jsPDF + html2canvas).
- Saves quiz outcomes for logged-in users, contributing to analytics and leaderboard scoring.

### Analytics, Dashboard & Leaderboard
- Dashboard charts (Chart.js), detailed result tables, and transcript downloads.
- Continuous time-on-platform logging every 15 seconds for daily activity insights.
- Leaderboard points weighted by difficulty tiers and decorated with custom badges.

### Account & Identity
- Email/password authentication with bcrypt hashing and OTP verification.
- Password reset flow that emails a temporary password through SMTP.
- Optional Google and GitHub OAuth sign-in with auto-provisioning and avatar import.
- Profile management: bio, socials, location, and avatar uploads stored in the database.

### Admin Controls
- Admin-only blueprint with guarded routes.
- User management: grant/revoke admin access, reset passwords, update profile data, delete accounts.
- Demo/test account exclusions for analytics and admin actions.

### UX & Safety
- Dark/light theming, animated CTA buttons, cursor effects, and accessible toast messaging.
- Session TTL enforcement, max active session limits, and cache-control hardening for protected pages.

---

## Tech Stack
- Backend: Flask, SQLAlchemy, Flask-Bcrypt, Authlib
- AI & NLP: OpenRouter API, TextBlob + NLTK
- Database: PostgreSQL (via DATABASE_URL); SQLite is supported if configured
- Frontend: Vanilla JavaScript, Chart.js, jsPDF, html2canvas
- Deployment: Vercel (@vercel/python)

---

## Architecture Overview

| Layer | Responsibilities | Key Files |
| --- | --- | --- |
| Backend (Flask) | HTTP routing, session/auth, SQLAlchemy models, admin blueprint, REST APIs, leaderboard math, OTP, OAuth integration | app.py |
| Services | OpenRouter prompts, answer evaluation, tone analytics, dataset caching/deduplication | services/api_service.py |
| Frontend JS | Interview & quiz controllers, timers, voice I/O, result rendering, dashboard interactivity | static/js/app.js, static/js/quiz.js, static/js/start.js |
| Styling | Core theme, quiz/interview layouts, admin UI, responsive adjustments | static/css/style.css, static/css/quiz.css, static/css/start.css, etc. |
| Templates | Landing/start flow, quiz shell, dashboard, leaderboard, admin panel, auth pages | templates/index.html, templates/dashboard.html, templates/leaderboard.html, others |
| Data | PostgreSQL/SQLite database, cached question JSON, profile media blobs | questions.json, ProfileMedia table |
| Testing | Unittest suites for API helpers and Flask routes, with external services mocked | Tests/test_api_service.py, Tests/test_app.py |

---

## API Surface

| Endpoint | Method(s) | Description |
| --- | --- | --- |
| /api/start_interview | POST | Start an interview session, generate questions, return a session ID. |
| /api/submit_answer | POST | Evaluate an answer, return feedback/score, advance the interview session. |
| /api/get_question/<session_id>/<int:index> | GET | Fetch a specific interview question from an active session. |
| /api/session/<session_id> | GET | Inspect session state (role, difficulty, progress). |
| /api/end_session/<session_id> | DELETE | End and clean up an interview session. |
| /api/questions | GET | Retrieve quiz questions filtered by role/difficulty, with deduplication metadata. |
| /questions.json | GET | Serve the raw quiz dataset for client-side fallback. |
| /api/save_quiz_result | POST | Persist quiz scores, selections, and duration for authenticated users. |
| /api/results | GET | Return the authenticated user’s interview & quiz history. |
| /api/results/<id> | DELETE | Remove a stored result (used for dashboard deletions). |
| /api/profile | GET/POST | Fetch or update profile metadata. |
| /api/profile_picture | POST/DELETE | Upload or remove profile avatars (validated & size-limited). |
| /api/profile_update | POST | Update extended profile details used by dashboard forms. |
| /api/change_password | POST | Change the current user’s password (bcrypt hashing). |
| /api/time_log | POST | Increment time-on-platform counters for the active user. |
| /api/time_stats | GET | Fetch recent time log series for charting. |

Auth, OTP, signup, password reset, and admin management endpoints are exposed via HTML routes rendered from app.py templates.

---

## Project Structure

```
Virtual-Interviewaer/
├── app.py                     # Flask application entry point and route handlers
├── services/
│   └── api_service.py         # OpenRouter integration, dataset helpers, evaluation logic
├── static/
│   ├── css/                   # Core styling (start, quiz, admin, error pages, etc.)
│   ├── js/                    # Vanilla JS controllers for interviews, quizzes, start page
│   └── assets/                # Icons, ambient imagery, badges
├── templates/
│   ├── index.html             # Landing page, interview screen, quiz shell, admin layout
│   ├── dashboard.html         # Authenticated user dashboard
│   ├── leaderboard.html       # Public leaderboard view
│   └── ...                    # Auth, error, admin-specific templates
├── Tests/
│   ├── test_api_service.py    # Unit tests for prompt builders and evaluation helpers
│   └── test_app.py            # Flask endpoint tests with extensive mocking
├── questions.json             # Cached fallback dataset for quizzes/interviews
├── requirements.txt           # Python dependencies
├── vercel.json                # Vercel deployment configuration
└── users.db                   # SQLite database (only when DATABASE_URL points to SQLite)
```

---

## Getting Started

### Prerequisites
- Python 3.8 or newer
- pip (bundled with modern Python)
- (Optional) A virtual environment tool such as venv or virtualenv

### Installation
```powershell
python -m venv .venv
\.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

# TextBlob requires corpora for sentiment analysis
python -m textblob.download_corpora
```

### Configure the database
The application reads its database connection string from DATABASE_URL. For local development you can use SQLite:

```
DATABASE_URL=sqlite:///users.db
```

---

## Environment Variables

Create a .env file (loaded via python-dotenv) and provide the variables relevant to your deployment:

| Variable | Required | Description |
| --- | --- | --- |
| SECRET_KEY | ✅ | Flask session secret; set to a strong random string. |
| DATABASE_URL | ✅ | SQLAlchemy database URL (PostgreSQL recommended; SQLite supported). |
| OPENROUTER_API_KEY | ✅ (for AI) | API key for OpenRouter question generation & answer evaluation. |
| DEFAULT_ADMIN_EMAIL | ⚙️ | Seed admin user email; auto-promoted on startup (requires password). |
| DEFAULT_ADMIN_PASSWORD | ⚙️ | Password for the seed admin (>=12 chars). |
| GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET | ⚙️ | Enable Google OAuth sign-in. |
| GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET | ⚙️ | Enable GitHub OAuth sign-in. |
| SMTP_EMAIL_ADDRESS / SMTP_APP_PASSWORD | ⚙️ | Gmail SMTP credentials for OTP + reset-password emails. |
| SESSION_TTL_SECONDS | ⛭ | Override session expiry (default 1800 seconds, min 300). |
| MAX_ACTIVE_SESSIONS | ⛭ | Limits concurrent interview sessions in memory (default 200). |
| MAX_SESSION_QUESTIONS | ⛭ | Caps interview questions returned from the API (default 10). |
| PROFILE_UPLOAD_MAX_MB | ⛭ | Max avatar upload size in MB (default 5). |
| OTP_MAX_ATTEMPTS | ⛭ | Maximum OTP verification attempts (default 5). |
| DEMO_USER_EMAILS / TEST_USER_EMAIL_PATTERNS | ⛭ | Comma-separated allowlists used to exclude demo/test accounts from analytics. |

Values marked ⚙️ are optional but unlock functionality; ⛭ denotes operational tunables.

---

## Local Development

```powershell
# Ensure environment variables are loaded (via .env) then run
python app.py

# The server listens on http://127.0.0.1:5000 by default.
# Flask debug mode is enabled in the entrypoint for rapid iteration.
```

- Visiting / opens the start page where you can launch interviews or quizzes.
- Auth routes (/login, /signup, /verify-otp) deliver OTP-guarded forms and OAuth entry points.
- Authenticated users can access /dashboard for analytics and /leaderboard for global rankings.
- Admin users gain /admin navigation once logged in.

---

## Running Tests

The repository ships with unittest suites that rely on extensive mocking of external services, so they can be executed without live API keys:

```powershell
python -m unittest discover -s Tests -p "*.py"
```

---

## Data & Assets
- questions.json: curated dataset used for quiz mode and as a fallback when OpenRouter is unavailable.
- Profile media: stored as BLOBs in the database and served via /media/profile/<user_id>.
- Time logs: recorded per day per user, enabling streak analytics and aggregated charts.

---

## Deployment
- Vercel: vercel.json routes all traffic to app.py using the @vercel/python runtime.
- Stateless execution: Interview sessions are held in memory; use sticky sessions or external storage if scaling horizontally.
- Persistent storage: configure DATABASE_URL for a managed Postgres instance in production.

---

## License
No license file is bundled with this repository. Please contact the project owner for licensing details.

---

Author: [Asim Husain](https://www.asimhusain.dev)
