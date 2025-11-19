# Virtual Interviewer

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.3.3-000?logo=flask)](https://flask.palletsprojects.com/)
[![Deployed on Vercel](https://img.shields.io/badge/Deploy-Vercel-000?logo=vercel)](https://vercel.com/)

AI-assisted interview practice meets timed quizzes, personal analytics, and admin tooling — all powered by a Flask backend and a lightweight JavaScript front-end.

---

## Table of Contents
- [Overview](#overview)
- [Feature Highlights](#feature-highlights)
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
Virtual Interviewer is a full-stack practice platform that delivers AI-generated interview sessions and dataset-driven quizzes. Users can speak or type their answers, receive granular feedback and tone analysis, review detailed histories, and climb a gamified leaderboard. Admins can manage accounts, reset credentials, and inspect activity, while the system enforces session limits, timed questions, and cached question pools for resilience.

Live instance: <https://intervbot.vercel.app>

---

## Feature Highlights

### AI Interview Mode
- Generates role- and difficulty-aware questions via OpenRouter-powered prompts (`services/api_service.py`).
- Applies per-question timers (Easy 60s, Medium 90s, Hard 120s) and auto-submits on timeout (`static/js/app.js`).
- Supports both typed answers and live speech recognition (Web Speech API) with optional text-to-speech playback.
- Evaluates responses using OpenRouter, captures tone with TextBlob sentiment analysis, and stores expected answers, scores, and qualitative feedback.
- Persists session output for authenticated users, enabling longitudinal performance tracking (`Result` model in `app.py`).

### Timed Quiz Mode
- Pulls curated multiple-choice questions from the cached `questions.json` dataset with deduplication, role filtering, and client-side shuffle (`services/api_service.get_random_quiz_questions`).
- Mirrors the same 60/90/120 second timers per difficulty, auto-advancing questions and auto-submitting the final answer sheet.
- Produces rich result summaries, including donut charts, per-question breakdowns, and optional PDF exports (jsPDF + html2canvas in `static/js/quiz.js`).
- Saves quiz outcomes for logged-in users, contributing to analytics and leaderboard scoring.

### Analytics, Dashboard & Leaderboard
- Dashboard (`templates/dashboard.html`) visualizes interview/quiz history with Chart.js, result tables, and downloadable transcripts.
- Continuous time-on-platform tracking logs activity every 15 seconds while the dashboard is open (`/api/time_log`, `/api/time_stats`).
- Leaderboard (`templates/leaderboard.html`) ranks users by weighted points (difficulty-aware scoring in `app.calculate_points`) and decorates top performers with custom badges and avatars.

### Account & Identity
- Email/password authentication with bcrypt hashing, OTP verification, and resend protections (`OTPVerification` model, `_send_otp_email`).
- Optional Google and GitHub OAuth sign-in through Authlib, including automatic user provisioning and avatar imports.
- Profile management: update bio, socials, location, upload avatars (stored in `ProfileMedia`), and change passwords without leaving the dashboard.
- Session hardening: configurable TTL (`SESSION_TTL_SECONDS`), maximum concurrent sessions, and clean-up of expired interview sessions.

### Admin Controls
- Admin-only views ride on an explicit Flask blueprint (`/admin/*`) protected by access guards.
- Manage users: grant/revoke admin access, reset passwords, edit profile data, or delete accounts with cascading cleanup (Profiles, Results, TimeLogs, media).
- Dashboard metrics summarise total users and recorded time logs, respecting demo/test account exclusions defined via environment settings.

### Front-End Experience
- Responsive start page with dark/light theming, magnetic CTA buttons, and quick links to login/sign-up (`static/js/start.js`).
- Gooey button animations, cursor effects, and accessible toast notifications for auth flows.
- Pure JavaScript state management—no build step—keeps deployments lean and Vercel-friendly.

---

## Architecture Overview

| Layer | Responsibilities | Key Files |
| --- | --- | --- |
| **Backend (Flask)** | HTTP routing, session & auth, SQLAlchemy models, admin blueprint, REST APIs, leaderboard math, email OTP, OAuth integration | `app.py` |
| **Services** | OpenRouter prompts, answer evaluation, tone analytics, dataset caching/deduplication | `services/api_service.py` |
| **Frontend JS** | Interview & quiz controllers, timers, voice I/O, result rendering, dashboard interactivity | `static/js/app.js`, `static/js/quiz.js`, `static/js/dashboard.js` (inline), `static/js/start.js` |
| **Styling** | Core theme, quiz/interview layouts, admin UI, responsive adjustments | `static/css/style.css`, `static/css/quiz.css`, `static/css/start.css`, etc. |
| **Templates** | Landing/start flow, quiz shell, dashboard, leaderboard, admin panel, auth pages | `templates/index.html`, `templates/dashboard.html`, `templates/leaderboard.html`, others |
| **Data** | Persistent SQLite database (`users.db`), cached question JSON (`questions.json`), profile media blobs | root files & `ProfileMedia` table |
| **Testing** | Unittest suites for API helpers and Flask routes, including mocks for external services | `Tests/test_api_service.py`, `Tests/test_app.py` |

---

## API Surface

| Endpoint | Method(s) | Description |
| --- | --- | --- |
| `/api/start_interview` | POST | Start an interview session, generate questions, and create a server-tracked session ID. |
| `/api/submit_answer` | POST | Evaluate an answer, return feedback/score, and advance the interview session. |
| `/api/get_question/<session_id>/<int:index>` | GET | Fetch a specific interview question from an active session. |
| `/api/session/<session_id>` | GET | Inspect session state (role, difficulty, progress). |
| `/api/end_session/<session_id>` | DELETE | Explicitly end and clean up a running interview session. |
| `/api/questions` | GET | Retrieve quiz questions filtered by role/difficulty, with deduplication metadata. |
| `/questions.json` | GET | Serve the raw quiz dataset for client-side fallback. |
| `/api/save_quiz_result` | POST | Persist quiz scores, selections, and duration for authenticated users. |
| `/api/results` | GET | Return the authenticated user’s historic interview & quiz results. |
| `/api/results/<id>` | DELETE | Remove a stored result (dashboard bulk deletion uses this). |
| `/api/profile` | GET/POST | Fetch or update profile metadata (name, bio, socials, etc.). |
| `/api/profile_picture` | POST/DELETE | Upload or remove profile avatars (validated & size-limited). |
| `/api/profile_update` | POST | Update extended profile details handled by the dashboard forms. |
| `/api/change_password` | POST | Change the current user’s password (with bcrypt hashing). |
| `/api/time_log` | POST | Increment time-on-platform counters for the active user. |
| `/api/time_stats` | GET | Fetch recent time log series for charting. |
| `/api/profile_picture` | POST/DELETE | Manage avatar uploads stored in `ProfileMedia`. |

Authentication, OTP, signup, reset-password, and admin management endpoints are also exposed through conventional web routes rendered from `app.py` templates.

---

## Project Structure

```
Virtual-Interviewer/
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
└── users.db                   # SQLite database (auto-created in development)
```

---

## Getting Started

### Prerequisites
- Python 3.8 or newer
- pip (bundled with modern Python) 
- (Optional) A virtual environment tool such as `venv` or `virtualenv`

### Installation
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

# TextBlob requires corpora for sentiment analysis
python -m textblob.download_corpora
```

### Database bootstrap
On first run the app will automatically call `db.create_all()` and create `users.db`. No separate migration step is required for local development.

---

## Environment Variables

Create a `.env` file (loaded via `python-dotenv`) and provide the variables relevant to your deployment:

| Variable | Required | Description |
| --- | --- | --- |
| `SECRET_KEY` | ✅ | Flask session secret; set to a strong random string. |
| `OPENROUTER_API_KEY` | ✅ (for AI) | API key for OpenRouter question generation & answer evaluation. |
| `DEFAULT_ADMIN_EMAIL` | ⚙️ | Seed admin user email; auto-promoted on startup (requires password). |
| `DEFAULT_ADMIN_PASSWORD` | ⚙️ | Password for the seed admin (>=12 chars). |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | ⚙️ | Enable Google OAuth sign-in when both are present. |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | ⚙️ | Enable GitHub OAuth sign-in when both are present. |
| `SMTP_EMAIL_ADDRESS` / `SMTP_APP_PASSWORD` | ⚙️ | Credentials used to email OTP codes for signup/login verification. |
| `SESSION_TTL_SECONDS` | ⛭ | Override session expiry (default 1800 seconds, min 300). |
| `MAX_ACTIVE_SESSIONS` | ⛭ | Limits concurrent interview sessions in memory (default 200). |
| `MAX_SESSION_QUESTIONS` | ⛭ | Caps interview questions returned from the API (default 10). |
| `DEMO_USER_EMAILS` / `TEST_USER_EMAIL_PATTERNS` | ⛭ | Comma-separated allowlists used to exclude demo/test accounts from analytics. |

Values marked ⚙️ are optional but unlock functionality; ⛭ denotes operational tunables.

---

## Local Development

```powershell
# Ensure environment variables are loaded (via .env) then run
python app.py

# The server listens on http://127.0.0.1:5000 by default.
# Flask debug mode is enabled in the entrypoint for rapid iteration.
```

- Visiting `/` opens the start page where you can launch interviews or quizzes.
- Auth routes (`/login`, `/signup`, `/verify`) deliver OTP-guarded forms and OAuth entry points.
- Authenticated users can access `/dashboard` for analytics and `/leaderboard` for global rankings.
- Admin users gain `/admin` navigation once logged in.

---

## Running Tests

The repository ships with unittest suites that rely on extensive mocking of external services, so they can be executed without live API keys:

```powershell
python -m unittest discover -s Tests -p "*.py"
```

---

## Data & Assets
- **`questions.json`**: curated dataset used for quiz mode and as a fallback when OpenRouter is unavailable. Helper functions cache this file with mtime invalidation to avoid disk churn.
- **Profile media**: stored as BLOBs in SQLite (served via `/media/profile/<user_id>`). Upload size and type restrictions are enforced server-side.
- **Time logs**: recorded per day per user, enabling streak analytics and aggregated charts.

---

## Deployment
- **Vercel**: `vercel.json` routes all traffic to `app.py` using the `@vercel/python` runtime.
- **Stateless execution**: The application keeps interview sessions in memory; ensure workers use sticky sessions or configure alternative storage if scaling horizontally.
- **Persistent storage**: SQLite (`users.db`) suits single-instance deployments. For multi-instance setups, migrate to a managed SQL database and adjust `SQLALCHEMY_DATABASE_URI` accordingly.

---

## License
No license file is bundled with this repository. Please contact the project owner for licensing details.

---

**Author**: [Asim Husain](https://www.asimhusain.dev)
