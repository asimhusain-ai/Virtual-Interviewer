# This code is written by - Asim Husain
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    flash,
    redirect,
    url_for,
    render_template_string,
    Blueprint,
    send_from_directory,
    send_file,
    abort,
    has_request_context,
)
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import os
import io
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from services.api_service import (
    fetch_unique_interview_questions,
    evaluate_answer,
    analyze_tone,
    get_random_quiz_questions,
    ALLOWED_ROLES as SERVICE_ALLOWED_ROLES,
)

import json
import uuid
import time
import random
import re
import smtplib
import string
from email.mime.text import MIMEText
import secrets
import math
from datetime import datetime, date, timedelta
from sqlalchemy import text, or_, func, case, LargeBinary
from werkzeug.security import generate_password_hash as wz_generate_password_hash, check_password_hash as wz_check_password_hash
from werkzeug.http import http_date

load_dotenv()

app = Flask(__name__)

def _normalized_database_url():
    raw_url = (os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        return raw_url

    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif raw_url.startswith("postgresql://") and not raw_url.startswith("postgresql+psycopg2://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    return raw_url


app.config["SQLALCHEMY_DATABASE_URI"] = _normalized_database_url()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


def _safe_env_int(name, default_value):
    raw = os.getenv(name)
    if raw is None:
        return default_value
    try:
        parsed = int(raw)
        return parsed if parsed > 0 else default_value
    except ValueError:
        return default_value


SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    # Generate a per-process secret instead of using a predictable fallback
    SECRET_KEY = secrets.token_urlsafe(64)

app.secret_key = SECRET_KEY
CORS(app)


@app.after_request
def _apply_secure_cache_headers(response):
    if request.endpoint == 'static':
        return response

    is_protected_path = (
        request.path.startswith('/admin')
        or request.path.startswith('/dashboard')
        or request.path.startswith('/api')
        or request.path == '/logout'
    )

    if session.get('user_id') or is_protected_path:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response

DEFAULT_ADMIN_EMAIL = (os.getenv('DEFAULT_ADMIN_EMAIL') or '').strip().lower()
DEFAULT_ADMIN_PASSWORD = (os.getenv('DEFAULT_ADMIN_PASSWORD') or '').strip() or None
DEMO_USER_EMAILS = {
    email.strip().lower()
    for email in (os.getenv('DEMO_USER_EMAILS') or '').split(',')
    if email.strip()
}
if DEFAULT_ADMIN_EMAIL:
    DEMO_USER_EMAILS.add(DEFAULT_ADMIN_EMAIL)

TEST_USER_EMAIL_PATTERNS = [
    pattern.strip().lower()
    for pattern in (os.getenv('TEST_USER_EMAIL_PATTERNS') or '').split(',')
    if pattern.strip()
]

SESSION_TTL_SECONDS = max(300, _safe_env_int('SESSION_TTL_SECONDS', 1800))
MAX_ACTIVE_SESSIONS = max(25, _safe_env_int('MAX_ACTIVE_SESSIONS', 200))
MAX_SESSION_QUESTIONS = min(25, max(1, _safe_env_int('MAX_SESSION_QUESTIONS', 10)))
ALLOWED_ROLES = set(SERVICE_ALLOWED_ROLES)
ALLOWED_DIFFICULTIES = {'Easy', 'Medium', 'Hard'}
PROFILE_UPLOAD_MAX_MB = max(1, _safe_env_int('PROFILE_UPLOAD_MAX_MB', 5))
PROFILE_UPLOAD_MAX_BYTES = PROFILE_UPLOAD_MAX_MB * 1024 * 1024
ALLOWED_IMAGE_MIMETYPES = {
    'image/png',
    'image/jpeg',
    'image/gif',
    'image/webp',
}
OTP_MAX_ATTEMPTS = max(1, _safe_env_int('OTP_MAX_ATTEMPTS', 5))

app.config['MAX_CONTENT_LENGTH'] = PROFILE_UPLOAD_MAX_BYTES

LEADERBOARD_BADGES = [
    {'label': 'Interview Hero', 'asset': 'assets/interviewhero.png'},
    {'label': 'Skilled Performer', 'asset': 'assets/skilledperformer.png'},
    {'label': 'Rising Lerner', 'asset': 'assets/risinglerner.png'},
]

DIFFICULTY_POINT_MULTIPLIERS = {
    'beginner': 1,
    'intermediate': 2,
    'professional': 3,
}

DIFFICULTY_ALIASES = {
    'beginner': 'beginner',
    'easy': 'beginner',
    'intermediate': 'intermediate',
    'medium': 'intermediate',
    'professional': 'professional',
    'advanced': 'professional',
    'pro': 'professional',
    'hard': 'professional',
}

_DEFAULT_DIFFICULTY_KEY = 'beginner'


def _normalize_difficulty_label(label):
    """Map human-readable difficulty labels to internal scoring keys."""
    if not label:
        return _DEFAULT_DIFFICULTY_KEY
    normalized = str(label).strip().lower()
    return DIFFICULTY_ALIASES.get(normalized, _DEFAULT_DIFFICULTY_KEY)


def _coerce_percentage(value):
    """Convert stored percentage values (ints, floats, strings) into a safe float."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        pct = float(value)
    else:
        try:
            pct = float(str(value).strip().rstrip('%'))
        except (TypeError, ValueError):
            return 0.0
    if math.isnan(pct) or math.isinf(pct):
        return 0.0
    return max(0.0, min(100.0, pct))


def calculate_points(mode, percentage_score, difficulty):
    """Compute leaderboard points for a given mode, percentage score, and difficulty."""
    _ = (mode or '').strip().lower()
    pct = _coerce_percentage(percentage_score)
    blocks = int(math.floor(pct / 10.0))
    if blocks <= 0:
        return 0
    multiplier = DIFFICULTY_POINT_MULTIPLIERS.get(
        _normalize_difficulty_label(difficulty),
        DIFFICULTY_POINT_MULTIPLIERS[_DEFAULT_DIFFICULTY_KEY],
    )
    return int(blocks * multiplier)


def _extract_difficulty_from_details(details):
    """Best-effort extraction of difficulty label from stored result details."""
    if not details:
        return None
    if isinstance(details, dict):
        raw = details.get('difficulty')
        return raw if raw else None
    if isinstance(details, str):
        try:
            payload = json.loads(details)
        except (TypeError, ValueError):
            return None
        if isinstance(payload, dict):
            raw = payload.get('difficulty')
            return raw if raw else None
    return None


def _aggregate_points_for_users(user_ids):
    """Return per-user point totals split by mode for leaderboard aggregation."""
    if not user_ids:
        return {}

    initial = {uid: {'total': 0, 'ai': 0, 'quiz': 0} for uid in user_ids}

    try:
        rows = (
            db.session.query(
                Result.user_id,
                Result.score,
                Result.kind,
                Result.details,
            )
            .filter(Result.user_id.in_(list(user_ids)))
            .filter(Result.score.isnot(None))
            .all()
        )
    except Exception as exc:
        app.logger.exception('Failed to aggregate leaderboard points: %s', exc)
        return initial

    for user_id, score, kind, details in rows:
        mode = 'quiz' if (kind or '').lower() == 'quiz' else 'ai'
        difficulty = _extract_difficulty_from_details(details) or 'Beginner'
        points_value = calculate_points(mode, score, difficulty)
        if points_value <= 0:
            continue
        bucket = initial.setdefault(user_id, {'total': 0, 'ai': 0, 'quiz': 0})
        bucket['total'] += points_value
        if mode == 'quiz':
            bucket['quiz'] += points_value
        else:
            bucket['ai'] += points_value

    return initial


def _avatar_url_for(profile_pic_value, user_id, *, cache_bust=False):
    """Resolve stored profile picture value to a usable URL."""
    value = (profile_pic_value or '').strip()
    if not value:
        return None
    if value.startswith(('http://', 'https://', 'data:')):
        return value
    if value.startswith('media/profile/'):
        if has_request_context():
            base = url_for('profile_media', user_id=user_id)
        else:
            base = f"/media/profile/{user_id}"
        if cache_bust:
            separator = '&' if '?' in base else '?'
            return f"{base}{separator}v={int(time.time())}"
        return base
    if value.startswith('/'):
        return value
    return f"/static/{value}".replace('\\', '/')

bcrypt = Bcrypt(app)

oauth = OAuth(app)


def _register_oauth_clients():
    """Configure available OAuth providers based on environment variables."""
    registered = {}

    google_client_id = os.getenv('GOOGLE_CLIENT_ID')
    google_client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    if google_client_id and google_client_secret:
        oauth.register(
            name='google',
            client_id=google_client_id,
            client_secret=google_client_secret,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )
        registered['google'] = True
    else:
        registered['google'] = False

    github_client_id = os.getenv('GITHUB_CLIENT_ID')
    github_client_secret = os.getenv('GITHUB_CLIENT_SECRET')
    if github_client_id and github_client_secret:
        oauth.register(
            name='github',
            client_id=github_client_id,
            client_secret=github_client_secret,
            access_token_url='https://github.com/login/oauth/access_token',
            authorize_url='https://github.com/login/oauth/authorize',
            api_base_url='https://api.github.com/',
            client_kwargs={'scope': 'read:user user:email'},
        )
        registered['github'] = True
    else:
        registered['github'] = False

    return registered


OAUTH_PROVIDERS = _register_oauth_clients()

# Serve favicon.ico (browsers request this path automatically) by redirecting to existing PNG
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'assets'), 'favicon.png')

# Store user sessions 
user_sessions = {}


def _is_session_expired(data):
    if not isinstance(data, dict):
        return False
    started_at = data.get('started_at')
    if not started_at:
        return False
    now = datetime.utcnow()
    if isinstance(started_at, datetime):
        return (now - started_at).total_seconds() > SESSION_TTL_SECONDS
    if isinstance(started_at, (int, float)):
        return (time.time() - float(started_at)) > SESSION_TTL_SECONDS
    return False


def _cleanup_sessions():
    if not user_sessions:
        return
    expired_ids = [sid for sid, payload in user_sessions.items() if _is_session_expired(payload)]
    for sid in expired_ids:
        user_sessions.pop(sid, None)


SMTP_EMAIL = (os.getenv('SMTP_EMAIL_ADDRESS') or '').strip()
_raw_smtp_password = os.getenv('SMTP_APP_PASSWORD') or ''
SMTP_APP_PASSWORD = ''.join(_raw_smtp_password.split())


# --- User model for auth ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    gender = db.Column(db.String(32), nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    def check_password(self, password):
        stored = self.password_hash or ''
        if not stored:
            return False

        if stored.startswith(('$2a$', '$2b$', '$2y$')):
            try:
                return bcrypt.check_password_hash(stored, password)
            except ValueError:
                return False

        if ':' in stored:
            try:
                return wz_check_password_hash(stored, password)
            except ValueError:
                return False

        return False


# Optional: store past interview/quiz results
class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    score = db.Column(db.Float, nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    kind = db.Column(db.String(32), nullable=True)  # 'interview' or 'quiz'

def _ensure_result_details_column():
    """Best-effort migration to add 'details' column to result table if missing.

    Uses SQLAlchemy session.execute with sqlite PRAGMA for compatibility with SQLAlchemy 2.x.
    """
    try:
        res = db.session.execute(text("PRAGMA table_info('result')")).fetchall()
        cols = [r[1] for r in res]
        if 'details' not in cols:
            try:
                db.session.execute(text("ALTER TABLE result ADD COLUMN details TEXT"))
                db.session.commit()
            except Exception:
                db.session.rollback()
    except Exception:
        # if anything goes wrong, rollback to leave session clean and continue
        try:
            db.session.rollback()
        except Exception:
            pass


def _ensure_user_admin_column():
    """Make sure the user table has an is_admin flag for access control."""
    try:
        res = db.session.execute(text("PRAGMA table_info('user')")).fetchall()
        cols = [r[1] for r in res]
        if 'is_admin' not in cols:
            try:
                db.session.execute(text("ALTER TABLE user ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"))
                db.session.commit()
            except Exception:
                db.session.rollback()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

# Optional: per-user metadata (contact, profile picture)
class UserMeta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    contact = db.Column(db.String(64), nullable=True)
    profile_pic = db.Column(db.String(255), nullable=True)
    github = db.Column(db.String(255), nullable=True)
    linkedin = db.Column(db.String(255), nullable=True)
    website = db.Column(db.String(255), nullable=True)
    address = db.Column(db.Text, nullable=True)
    course = db.Column(db.String(255), nullable=True)
    dob = db.Column(db.String(32), nullable=True)


# Separate table for dashboard profile fields to avoid altering legacy UserMeta schema
class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    username = db.Column(db.String(120), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    university = db.Column(db.String(255), nullable=True)
    location = db.Column(db.String(255), nullable=True)
    pronouns = db.Column(db.String(64), nullable=True)


class ProfileMedia(db.Model):
    user_id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(128), nullable=True)
    data = db.Column(LargeBinary, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OTPVerification(db.Model):
    email = db.Column(db.String(255), primary_key=True)
    otp = db.Column(db.String(6), nullable=False)
    expiry_time = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
def _ensure_usermeta_columns():
    """Ensure recently added columns exist on user_meta for backward compatibility."""
    try:
        res = db.session.execute(text("PRAGMA table_info('user_meta')")).fetchall()
        cols = {row[1] for row in res}
        if 'dob' not in cols:
            try:
                db.session.execute(text("ALTER TABLE user_meta ADD COLUMN dob TEXT"))
                db.session.commit()
            except Exception:
                db.session.rollback()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def _ensure_otp_attempts_column():
    """Add attempts column to otp_verification table when missing."""
    try:
        res = db.session.execute(text("PRAGMA table_info('otp_verification')")).fetchall()
        cols = {row[1] for row in res}
        if 'attempts' not in cols:
            try:
                db.session.execute(
                    text("ALTER TABLE otp_verification ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
                )
                db.session.commit()
            except Exception:
                db.session.rollback()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def _get_excluded_user_ids():
    """Return user IDs that should be hidden from admin views (demo/test accounts)."""
    ids = set()

    if DEMO_USER_EMAILS:
        try:
            rows = User.query.filter(User.email.in_(list(DEMO_USER_EMAILS))).all()
            ids.update({row.id for row in rows if row and row.id is not None})
        except Exception:
            pass

    if TEST_USER_EMAIL_PATTERNS:
        try:
            filters = [User.email.ilike(f"%{pattern}%") for pattern in TEST_USER_EMAIL_PATTERNS]
            if filters:
                for row in User.query.filter(or_(*filters)).all():
                    if row and row.id is not None:
                        ids.add(row.id)
        except Exception:
            pass

    return ids


def _build_leaderboard(limit=20):
    """Return aggregated leaderboard entries ordered by point totals."""
    excluded_ids = _get_excluded_user_ids()

    try:
        score_query = (
            db.session.query(
                Result.user_id.label('user_id'),
                func.avg(Result.score).label('avg_score'),
                func.avg(case((Result.kind == 'quiz', Result.score), else_=None)).label('quiz_avg_score'),
                func.avg(case((Result.kind == 'interview', Result.score), else_=None)).label('interview_avg_score'),
                func.sum(case((Result.kind == 'quiz', 1), else_=0)).label('quiz_count'),
                func.sum(case((Result.kind == 'interview', 1), else_=0)).label('interview_count'),
                func.count(Result.id).label('attempt_count'),
                func.max(Result.timestamp).label('last_activity'),
            )
            .filter(Result.score.isnot(None))
        )

        if excluded_ids:
            score_query = score_query.filter(~Result.user_id.in_(list(excluded_ids)))

        score_subquery = score_query.group_by(Result.user_id).subquery()

        rows = (
            db.session.query(
                User,
                Profile,
                UserMeta,
                score_subquery.c.avg_score,
                score_subquery.c.quiz_avg_score,
                score_subquery.c.interview_avg_score,
                score_subquery.c.quiz_count,
                score_subquery.c.interview_count,
                score_subquery.c.attempt_count,
                score_subquery.c.last_activity,
            )
            .join(score_subquery, score_subquery.c.user_id == User.id)
            .outerjoin(Profile, Profile.user_id == User.id)
            .outerjoin(UserMeta, UserMeta.user_id == User.id)
            .all()
        )
    except Exception as exc:
        app.logger.exception('Failed to build leaderboard: %s', exc)
        return []

    if not rows:
        return []

    user_ids = [user.id for (user, *_rest) in rows]
    points_by_user = _aggregate_points_for_users(user_ids)

    entries = []
    for (
        user,
        profile,
        meta,
        avg_score,
        quiz_avg_score,
        interview_avg_score,
        quiz_count,
        interview_count,
        attempt_count,
        last_activity,
    ) in rows:
        profile_username = (profile.username if profile and profile.username else None)
        fallback_name = user.name or ''
        fallback_email = (user.email.split('@')[0] if user and user.email else f'User {user.id}')
        display_name_raw = profile_username or fallback_name or fallback_email
        display_name = display_name_raw.strip() or fallback_email

        initials_source = display_name or fallback_name or fallback_email
        initials = ''.join(part[0] for part in initials_source.split()[:2] if part).upper()
        if not initials:
            initials = 'U'

        avatar_url = None
        if meta and meta.profile_pic:
            needs_bust = (meta.profile_pic or '').strip().startswith('media/profile/')
            avatar_url = _avatar_url_for(meta.profile_pic, user.id, cache_bust=needs_bust)

        quiz_pct = int(round(quiz_avg_score)) if quiz_avg_score is not None else 0
        interview_pct = int(round(interview_avg_score)) if interview_avg_score is not None else 0

        quiz_attempts = int(quiz_count or 0)
        interview_attempts = int(interview_count or 0)

        points_data = points_by_user.get(user.id, {'total': 0, 'ai': 0, 'quiz': 0})

        entries.append({
            'user_id': user.id,
            'display_name': display_name,
            'name': user.name,
            'username': profile_username,
            'average_score': float(avg_score) if avg_score is not None else 0.0,
            'score': int(round(avg_score)) if avg_score is not None else 0,
            'attempts': int(attempt_count or 0),
            'last_activity': last_activity,
            'avatar_url': avatar_url,
            'initials': initials,
            'badge_label': None,
            'badge_asset': None,
            'quiz_percentage': quiz_pct,
            'interview_percentage': interview_pct,
            'quiz_count': quiz_attempts,
            'interview_count': interview_attempts,
            'points_total': int(points_data.get('total', 0)),
            'points_ai': int(points_data.get('ai', 0)),
            'points_quiz': int(points_data.get('quiz', 0)),
        })

    if not entries:
        return []

    entries.sort(
        key=lambda e: (
            e.get('points_total', 0),
            e.get('average_score', 0.0),
            e.get('last_activity') or datetime.min,
        ),
        reverse=True,
    )

    top_limit = max(1, int(limit or 0))
    trimmed = entries[:top_limit]

    for idx, entry in enumerate(trimmed, start=1):
        entry['rank'] = idx
        badge = LEADERBOARD_BADGES[idx - 1] if idx <= len(LEADERBOARD_BADGES) else None
        entry['badge_label'] = badge['label'] if badge else None
        entry['badge_asset'] = badge['asset'] if badge else None

    return trimmed


def _ensure_seed_admin():
    """Create or promote a default admin user when env credentials are provided."""
    admin_email = DEFAULT_ADMIN_EMAIL
    admin_password = DEFAULT_ADMIN_PASSWORD
    if not admin_email or not admin_password:
        return

    if len(admin_password) < 12 or admin_password == '9@$$Word!123':
        raise RuntimeError('DEFAULT_ADMIN_PASSWORD must be set to a strong value (>=12 chars) and differ from the default placeholder.')

    user = User.query.filter_by(email=admin_email).first()
    if user is None:
        try:
            pw_hash = wz_generate_password_hash(admin_password)
            user = User(name='Administrator', email=admin_email, password_hash=pw_hash, is_admin=True)
            db.session.add(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
    else:
        if not user.is_admin:
            try:
                user.is_admin = True
                db.session.commit()
            except Exception:
                db.session.rollback()


def _start_user_session(user, avatar_override=None, extras=None):
    """Populate the Flask session with user details after login."""
    extras = extras or {}
    session['user_id'] = user.id
    session['user_email'] = user.email
    session['is_admin'] = bool(user.is_admin)
    session['user_name'] = extras.get('name') or user.name
    session['user_location'] = extras.get('location')
    session['user_dob'] = extras.get('dob')

    meta = None
    profile = None
    try:
        meta = UserMeta.query.filter_by(user_id=user.id).first()
        profile = Profile.query.filter_by(user_id=user.id).first()
    except Exception:
        meta = None
        profile = None

    if avatar_override:
        session['avatar_url'] = avatar_override
    else:
        pic_value = meta.profile_pic if meta and meta.profile_pic else None
        if pic_value:
            needs_bust = (pic_value or '').startswith('media/profile/')
            session['avatar_url'] = _avatar_url_for(pic_value, user.id, cache_bust=needs_bust)
        else:
            session['avatar_url'] = None

    if not session.get('user_location'):
        if profile and profile.location:
            session['user_location'] = profile.location
        elif meta and meta.address:
            session['user_location'] = meta.address
    if not session.get('user_dob') and meta and meta.dob:
        session['user_dob'] = meta.dob
    if not session.get('user_name'):
        session['user_name'] = user.name


def _get_or_create_oauth_user(email, name, provider, provider_user_id, *, avatar_url=None, birthdate=None, location=None):
    """Fetch an existing user or create one from OAuth profile data."""
    if not email:
        raise ValueError('Email is required for OAuth sign-in.')

    normalized_email = email.strip().lower()
    display_name = (name or '').strip() or normalized_email.split('@')[0]
    user = User.query.filter_by(email=normalized_email).first()
    created = False

    if user is None:
        placeholder_hash = f"oauth:{provider}:{provider_user_id or secrets.token_hex(8)}"
        user = User(
            name=display_name,
            email=normalized_email,
            password_hash=placeholder_hash,
        )
        db.session.add(user)
        db.session.flush()
        username = _generate_unique_username(display_name)
        profile = Profile(user_id=user.id, username=username)
        db.session.add(profile)
        created = True
    else:
        if not user.name and display_name:
            user.name = display_name

    # Ensure a profile exists for existing social sign-ins
    profile = Profile.query.filter_by(user_id=user.id).first()
    if not profile:
        username = _generate_unique_username(display_name)
        profile = Profile(user_id=user.id, username=username)
        db.session.add(profile)

    meta = UserMeta.query.filter_by(user_id=user.id).first()
    if not meta:
        meta = UserMeta(user_id=user.id)
        db.session.add(meta)

    if display_name and not (user.name and user.name.strip()):
        user.name = display_name

    if birthdate:
        birthdate_clean = birthdate.strip()
        if birthdate_clean and not (meta and meta.dob):
            meta.dob = birthdate_clean

    if location:
        location_clean = location.strip()
        if location_clean:
            if profile and not profile.location:
                profile.location = location_clean
            if meta and not meta.address:
                meta.address = location_clean

    if avatar_url and avatar_url.startswith(('http://', 'https://')):
        if not meta.profile_pic or meta.profile_pic.startswith(('http://', 'https://')):
            meta.profile_pic = avatar_url

    return user, created


def _generate_unique_username(name):
    """Generate a unique, lowercase username derived from the provided name."""
    base = re.sub(r'[^a-z0-9]+', '', (name or '').lower())
    if not base:
        base = 'user'

    candidate = base
    exists = Profile.query.filter_by(username=candidate).first()
    if exists:
        attempts = 0
        while True:
            suffix = f"{random.randint(1, 99):02d}"
            candidate = f"{base}{suffix}"
            if not Profile.query.filter_by(username=candidate).first():
                break
            attempts += 1
            if attempts >= 25:
                candidate = f"{base}{uuid.uuid4().hex[:4]}"
                if not Profile.query.filter_by(username=candidate).first():
                    break
                attempts = 0
    return candidate


def _sanitize_username(value):
    if value is None:
        return None
    username = re.sub(r'[^a-z0-9]+', '', value.strip().lower())
    return username or None


def _find_user_by_login_identifier(identifier):
    ident = (identifier or '').strip()
    if not ident:
        return None

    email_candidate = ident.lower()
    user = User.query.filter_by(email=email_candidate).first()
    if user:
        return user

    sanitized = _sanitize_username(ident)
    if not sanitized:
        return None

    profile = Profile.query.filter_by(username=sanitized).first()
    if profile:
        try:
            return User.query.get(profile.user_id)
        except Exception:
            return None
    return None


def _username_taken(username, exclude_user_id=None):
    if not username:
        return False
    query = Profile.query.filter_by(username=username)
    if exclude_user_id is not None:
        query = query.filter(Profile.user_id != exclude_user_id)
    return query.first() is not None


def _send_otp_email(recipient_email, otp_code):
    """Send a one-time password to the provided email address using Gmail SMTP."""
    if not SMTP_EMAIL or not SMTP_APP_PASSWORD:
        raise RuntimeError('SMTP credentials are not configured. Set SMTP_EMAIL_ADDRESS and SMTP_APP_PASSWORD.')

    subject = 'Your IntervBot verification code'
    body = (
        f"Hello,\n\n"
        f"Your One Time Password is: {otp_code}\n"
        f"This code expires in 5 minutes. If you did not request it, you can ignore this message.\n\n"
        f"Thanks,\nIntervBot"
    )

    message = MIMEText(body)
    message['Subject'] = subject
    message['From'] = SMTP_EMAIL
    message['To'] = recipient_email

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
        server.sendmail(SMTP_EMAIL, [recipient_email], message.as_string())


def _generate_temp_password(length=8):
    """Create a cryptographically secure temporary password."""
    alphabet = string.ascii_letters + string.digits
    if not alphabet:
        raise ValueError('Alphabet for password generation is empty.')
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _send_reset_password_email(recipient_email, temp_password):
    """Send a temporary password to the provided email address using Gmail SMTP."""
    if not SMTP_EMAIL or not SMTP_APP_PASSWORD:
        raise RuntimeError('SMTP credentials are not configured. Set SMTP_EMAIL_ADDRESS and SMTP_APP_PASSWORD.')

    subject = 'Your IntervBot temporary password'
    body = (
        "Hello,\n\n"
        "We received a request to reset your IntervBot account password.\n\n"
        f"Your new temporary password is: {temp_password}\n"
        "Please sign in using this password and change it after logging in.\n\n"
        "If you did not request a password reset, you can safely ignore this email.\n\n"
        "Thanks,\nIntervBot"
    )

    message = MIMEText(body)
    message['Subject'] = subject
    message['From'] = SMTP_EMAIL
    message['To'] = recipient_email

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
        server.sendmail(SMTP_EMAIL, [recipient_email], message.as_string())


# Track time spent (per-user, per-day, in seconds)
class TimeLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    day = db.Column(db.Date, nullable=False, index=True)
    seconds = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'day', name='uq_timelog_user_day'),
    )


def _is_sqlite_database():
    try:
        return db.engine.url.get_backend_name() == 'sqlite'
    except Exception:
        return False


# Ensure DB and tables exist
with app.app_context():
    db.create_all()
    # SQLite-only compatibility migrations for older local databases
    if _is_sqlite_database():
        _ensure_result_details_column()
        _ensure_user_admin_column()
        _ensure_usermeta_columns()
        _ensure_otp_attempts_column()
    # Ensure Profile table exists
    try:
        db.create_all()
    except Exception:
        pass
    _ensure_seed_admin()
    # Manual question management preferred; auto-generator removed

@app.route('/')
def start_page():
    """Serve the new start page."""
    logout_message = ''
    if request.args.get('logged_out') == '1':
        logout_message = 'Logged Out'
    return render_template('index.html', page='start', logout_message=logout_message)

@app.route('/landing')
def landing():
    if not session.get('user_id'):
        flash('Please Login to View Dashboard')
        return redirect(url_for('login'))
    return render_template('index.html', page='landing')

@app.route('/quiz')
def quiz():
    return render_template('index.html', page='quiz')


# ----------------- Auth routes -----------------
_signup_form = """
<!doctype html>
<html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>Signup • IntervBot</title>
        <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}" />
        <link rel="stylesheet" href="{{ url_for('static', filename='css/start.css') }}" />
        <link rel="stylesheet" href="{{ url_for('static', filename='css/auth.css') }}" />
        <link rel="icon" href="{{ url_for('static', filename='assets/favicon.png') }}" />
    </head>
    <body class="auth-page">
        <script>
            (function () {
                try {
                    var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
                    var theme = prefersDark ? 'theme-dark' : 'theme-light';
                    document.documentElement.dataset.theme = theme;
                    document.documentElement.style.colorScheme = theme === 'theme-dark' ? 'dark' : 'light';
                    if (document.body) {
                        document.body.classList.remove('theme-light', 'theme-dark');
                        document.body.classList.add(theme);
                        document.body.dataset.theme = theme;
                    }
                } catch (e) {
                    // ignore theme storage errors
                }
            })();
        </script>
        {% with messages = get_flashed_messages() %}
        {% set ns = namespace(hero=None, danger=None, fallback=None) %}
        {% if messages %}
        {% set hero_messages = ['Account Created Successfully', 'Verification Code Sent to Your Email', 'Temporary Password Sent to Your Email'] %}
        {% set danger_messages = [
            'Name, Email and Password are Required',
            'Email and OTP are Required',
            'No Code Found. Please Signup Again',
            'Your Code is Expired. Resend Code',
            'Incorrect Verification Code. Please Try Again',
            'Your Signup Session Expired. Resend Code',
            'Failed to Create Account. Please try Again',
            'Failed to Send OTP. Please try Again',
            'Account Already Exists',
            'Email is Required',
            'No Account Exists with this Email',
            'Unable to Reset Password. Try Again',
            'Failed to Send Password. Please try Again',
            'Email and Password are Required',
            'Invalid credentials',
            'Unsupported Login Provider',
            'Google Login is not Configured Yet',
            'GitHub Login is not Configured Yet',
            'Server Misconfiguration. Please Contact Support',
            "Couldn't Signin. Please Try Again",
            "Couldn't Retrieve Your Profile From Provider",
            'Your Account Must Have Public Email to Signin',
            'Unable to Sign You In Right Now. Please Try Again Later',
            'Please Login to View Dashboard',
            'Admin Access Required',
            'Demo/test accounts are not managed from this panel.',
            'You cannot change your own admin status from this panel.',
            'User Not Found',
            'Temporary Password is Required to Reset User Password',
            'Email Already in Use. Try Another',
            'Admin Cannot Delete own Account from Panel'
        ] %}
        {% for message in messages %}
        {% if not ns.danger and message in danger_messages %}
        {% set ns.danger = message %}
        {% elif not ns.hero and message in hero_messages %}
        {% set ns.hero = message %}
        {% elif not ns.fallback %}
        {% set ns.fallback = message %}
        {% endif %}
        {% endfor %}
        {% endif %}
        {% if ns.hero %}
        <div id="logout-toast" class="logout-toast" role="alert" aria-live="polite" aria-hidden="false" data-logout-active="1" tabindex="-1" aria-labelledby="logout-toast-message">
            <div class="logout-toast-content">
                <p id="logout-toast-message" class="logout-toast-message">{{ ns.hero }}</p>
                <button type="button" class="logout-toast-close" aria-label="Close" data-dismiss-toast>
                    <span class="sr-only">Close</span>
                    <svg class="logout-toast-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M18 6 6 18"></path>
                        <path d="m6 6 12 12"></path>
                    </svg>
                </button>
            </div>
        </div>
        {% elif ns.danger %}
        <div id="logout-toast" class="logout-toast logout-toast--danger" role="alert" aria-live="assertive" aria-hidden="false" data-logout-active="1" tabindex="-1" aria-labelledby="logout-toast-message">
            <div class="logout-toast-content">
                <p id="logout-toast-message" class="logout-toast-message logout-toast-message--danger">&#9888;&#65039; {{ ns.danger }}</p>
                <button type="button" class="logout-toast-close" aria-label="Close" data-dismiss-toast>
                    <span class="sr-only">Close</span>
                    <svg class="logout-toast-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M18 6 6 18"></path>
                        <path d="m6 6 12 12"></path>
                    </svg>
                </button>
            </div>
        </div>
        {% elif ns.fallback %}
        <div class="auth-toast show" role="status" aria-live="polite" aria-hidden="false">
            <span class="auth-toast-text">{{ ns.fallback }}</span>
        </div>
        {% endif %}
        {% endwith %}
        <main class="auth-card">
            <div class="auth-header">
                <h1 class="auth-title">Create Your Account</h1>
            </div>
            

                    <form class="auth-form auth-form-modern" method="post">
                        <div class="auth-field">
                            <label for="signupName">Name</label>
                            <div class="auth-input-shell">
                                <span class="auth-input-icon" aria-hidden="true">
                                    <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path>
                                        <circle cx="12" cy="7" r="4"></circle>
                                    </svg>
                                </span>
                                <input class="auth-input" type="text" name="name" id="signupName" placeholder="Enter name" required />
                            </div>
                        </div>
                        <div class="auth-field">
                            <label for="signupEmail">Email</label>
                            <div class="auth-input-shell">
                                <span class="auth-input-icon" aria-hidden="true">
                                    <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"></path>
                                        <polyline points="22,6 12,13 2,6"></polyline>
                                    </svg>
                                </span>
                                <input class="auth-input" type="email" name="email" id="signupEmail" placeholder="Enter email" required />
                            </div>
                        </div>
                        <div class="auth-field auth-password-field">
                            <label for="signupPassword">Password</label>
                            <div class="auth-input-shell">
                                <span class="auth-input-icon" aria-hidden="true">
                                    <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M2 18v3c0 .6.4 1 1 1h4v-3h3v-3h2l1.4-1.4a6.5 6.5 0 1 0-4-4Z"></path>
                                        <circle cx="16.5" cy="7.5" r=".5"></circle>
                                    </svg>
                                </span>
                                <input class="auth-input" type="password" name="password" id="signupPassword" placeholder="Enter password" required />
                                <button class="password-toggle" type="button" data-password-toggle="signupPassword" data-visible="false" aria-label="Show password" aria-pressed="false">
                                    <svg class="icon-eye" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7" />
                                        <circle cx="12" cy="12" r="3" />
                                    </svg>
                                    <svg class="icon-eye-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        <path d="M17.94 17.94A10.94 10.94 0 0 1 12 19c-7 0-11-7-11-7a21.77 21.77 0 0 1 2.84-3.88" />
                                        <path d="M9.88 9.88a3 3 0 0 0 4.24 4.24" />
                                        <path d="M1 1l22 22" />
                                        <path d="M22.17 16.88A11.05 11.05 0 0 0 23 12S19 5 12 5a10.94 10.94 0 0 0-4.26.9" />
                                    </svg>
                                </button>
                            </div>
                            <p class="auth-error auth-password-error" data-password-error aria-live="polite">⚠️ Password must be at least 8 characters</p>
                        </div>

                                        <div class="auth-actions">
                                            <button class="goo-button" type="submit" data-goo-magnet="off" data-submit-progress>
                                                <span class="auth-spinner" aria-hidden="true"></span>
                                                <span class="auth-submit-text">SIGN UP</span>
                                            </button>
                                        </div>
                                        <div style="text-align:center; margin-top:0; font-weight:600;">
                                            <a href="{{ url_for('login') }}" class="auth-footer-link">Already have an account. Login</a>
                                        </div>
                    </form>
                            <!-- inline goo SVG filter (required by .goo-button before pseudo) -->
                            <svg width="0" height="0" style="position: absolute;">
                                <filter id="goo" x="-50%" y="-50%" width="200%" height="200%">
                                    <feComponentTransfer>
                                        <feFuncA type="discrete" tableValues="0 1"></feFuncA>
                                    </feComponentTransfer>
                                    <feGaussianBlur stdDeviation="5"></feGaussianBlur>
                                    <feComponentTransfer>
                                        <feFuncA type="table" tableValues="-5 11"></feFuncA>
                                    </feComponentTransfer>
                                </filter>
                            </svg>

        </main>
        <script>
            (function() {
                document.querySelectorAll('[data-password-toggle]').forEach(function(btn) {
                    var targetId = btn.getAttribute('data-password-toggle');
                    var input = document.getElementById(targetId);
                    if (!input) {
                        return;
                    }
                    btn.addEventListener('click', function() {
                        var isVisible = btn.getAttribute('data-visible') === 'true';
                        input.setAttribute('type', isVisible ? 'password' : 'text');
                        btn.setAttribute('data-visible', isVisible ? 'false' : 'true');
                        btn.setAttribute('aria-pressed', isVisible ? 'false' : 'true');
                        btn.setAttribute('aria-label', isVisible ? 'Show password' : 'Hide password');
                    });
                });

                var signupForm = document.querySelector('form.auth-form');
                if (signupForm) {
                    signupForm.addEventListener('submit', function() {
                        var button = signupForm.querySelector('[data-submit-progress]');
                        if (!button || button.dataset.loading === 'true') {
                            return;
                        }
                        button.dataset.loading = 'true';
                        button.setAttribute('aria-busy', 'true');
                        button.setAttribute('disabled', 'disabled');
                        var textNode = button.querySelector('.auth-submit-text');
                        if (textNode) {
                            textNode.textContent = 'Sending';
                        }
                    });
                }
            })();
        </script>
        <script src="{{ url_for('static', filename='js/cursor.js') }}"></script>
        <script src="{{ url_for('static', filename='js/theme.js') }}"></script>
        <script src="{{ url_for('static', filename='js/goo-buttons.js') }}"></script>
        <script src="{{ url_for('static', filename='js/start.js') }}"></script>
    </body>
</html>
"""

_login_form = """
<!doctype html>
<html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>Login • IntervBot</title>
        <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}" />
        <link rel="stylesheet" href="{{ url_for('static', filename='css/start.css') }}" />
        <link rel="stylesheet" href="{{ url_for('static', filename='css/auth.css') }}" />
        <link rel="icon" href="{{ url_for('static', filename='assets/favicon.png') }}" />
    </head>
    <body class="auth-page">
        <script>
            (function () {
                try {
                    var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
                    var theme = prefersDark ? 'theme-dark' : 'theme-light';
                    document.documentElement.dataset.theme = theme;
                    document.documentElement.style.colorScheme = theme === 'theme-dark' ? 'dark' : 'light';
                    if (document.body) {
                        document.body.classList.remove('theme-light', 'theme-dark');
                        document.body.classList.add(theme);
                        document.body.dataset.theme = theme;
                    }
                } catch (e) {
                    // ignore theme storage errors
                }
            })();
        </script>
        {% with messages = get_flashed_messages() %}
        {% set ns = namespace(hero=None, danger=None, fallback=None) %}
        {% if messages %}
        {% set hero_messages = ['Account Created Successfully', 'Verification Code Sent to Your Email', 'Temporary Password Sent to Your Email'] %}
        {% set danger_messages = [
            'Name, Email and Password are Required',
            'Email and OTP are Required',
            'No Code Found. Please Signup Again',
            'Your Code is Expired. Resend Code',
            'Incorrect Verification Code. Please Try Again',
            'Your Signup Session Expired. Resend Code',
            'Failed to Create Account. Please try Again',
            'Failed to Send OTP. Please try Again',
            'Account Already Exists',
            'Email is Required',
            'No Account Exists with this Email',
            'Unable to Reset Password. Try Again',
            'Failed to Send Password. Please try Again',
            'Email and Password are Required',
            'Invalid credentials',
            'Unsupported Login Provider',
            'Google Login is not Configured Yet',
            'GitHub Login is not Configured Yet',
            'Server Misconfiguration. Please Contact Support',
            "Couldn't Signin. Please Try Again",
            "Couldn't Retrieve Your Profile From Provider",
            'Your Account Must Have Public Email to Signin',
            'Unable to Sign You In Right Now. Please Try Again Later',
            'Please Login to View Dashboard',
            'Admin Access Required',
            'Demo/test accounts are not managed from this panel.',
            'You cannot change your own admin status from this panel.',
            'User Not Found',
            'Temporary Password is Required to Reset User Password',
            'Email Already in Use. Try Another',
            'Admin Cannot Delete own Account from Panel'
        ] %}
        {% for message in messages %}
        {% if not ns.danger and message in danger_messages %}
        {% set ns.danger = message %}
        {% elif not ns.hero and message in hero_messages %}
        {% set ns.hero = message %}
        {% elif not ns.fallback %}
        {% set ns.fallback = message %}
        {% endif %}
        {% endfor %}
        {% endif %}
        {% if ns.hero %}
        <div id="logout-toast" class="logout-toast" role="alert" aria-live="polite" aria-hidden="false" data-logout-active="1" tabindex="-1" aria-labelledby="logout-toast-message">
            <div class="logout-toast-content">
                <p id="logout-toast-message" class="logout-toast-message">{{ ns.hero }}</p>
                <button type="button" class="logout-toast-close" aria-label="Close" data-dismiss-toast>
                    <span class="sr-only">Close</span>
                    <svg class="logout-toast-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M18 6 6 18"></path>
                        <path d="m6 6 12 12"></path>
                    </svg>
                </button>
            </div>
        </div>
        {% elif ns.danger %}
        <div id="logout-toast" class="logout-toast logout-toast--danger" role="alert" aria-live="assertive" aria-hidden="false" data-logout-active="1" tabindex="-1" aria-labelledby="logout-toast-message">
            <div class="logout-toast-content">
                <p id="logout-toast-message" class="logout-toast-message logout-toast-message--danger">&#9888;&#65039; {{ ns.danger }}</p>
                <button type="button" class="logout-toast-close" aria-label="Close" data-dismiss-toast>
                    <span class="sr-only">Close</span>
                    <svg class="logout-toast-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M18 6 6 18"></path>
                        <path d="m6 6 12 12"></path>
                    </svg>
                </button>
            </div>
        </div>
        {% elif ns.fallback %}
        <div class="auth-toast show" role="status" aria-live="polite" aria-hidden="false">
            <span class="auth-toast-text">{{ ns.fallback }}</span>
        </div>
        {% endif %}
        {% endwith %}
        <div id="demo-credentials-popup" class="demo-credentials-popup" role="dialog" aria-modal="false" aria-hidden="false" aria-labelledby="demo-credentials-title" data-visible="true" tabindex="-1">
            <div class="demo-credentials-header">
                <h2 id="demo-credentials-title">Demo Account</h2>
                <button type="button" class="demo-credentials-close" aria-label="Close demo credentials" data-demo-close>X</button>
            </div>
            <div class="demo-credentials-body">
                <dl class="demo-credentials-list">
                    <div class="demo-credentials-row">
                        <dt>Email</dt>
                        <dd data-demo-email>donihid579@coswz.com</dd>
                    </div>
                    <div class="demo-credentials-row">
                        <dt>Password</dt>
                        <dd data-demo-password>testuser1</dd>
                    </div>
                </dl>
            </div>
            <div class="demo-credentials-actions">
                <button type="button" class="demo-credentials-link" data-demo-fill>Fill Credentials</button>
            </div>
        </div>
        <main class="auth-card">
            <div class="auth-header">
                <h1 class="auth-title">Welcome Back</h1>
            </div>
            

                    <form class="auth-form auth-form-modern" method="post">
                        <div class="auth-field login-field">
                            <label for="loginEmail">Email or Username</label>
                            <div class="auth-input-shell">
                                <span class="auth-input-icon" aria-hidden="true">
                                    <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path>
                                        <circle cx="12" cy="7" r="4"></circle>
                                    </svg>
                                </span>
                                <input class="auth-input" type="text" name="email" id="loginEmail" placeholder="Enter email or username" autocomplete="username" required />
                            </div>
                        </div>
                        <div class="auth-field login-field auth-password-field">
                            <label for="loginPassword">Password</label>
                            <div class="auth-input-shell">
                                <span class="auth-input-icon" aria-hidden="true">
                                    <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M2 18v3c0 .6.4 1 1 1h4v-3h3v-3h2l1.4-1.4a6.5 6.5 0 1 0-4-4Z"></path>
                                        <circle cx="16.5" cy="7.5" r=".5"></circle>
                                    </svg>
                                </span>
                                <input class="auth-input" type="password" name="password" id="loginPassword" placeholder="Enter password" required />
                                <button class="password-toggle" type="button" data-password-toggle="loginPassword" data-visible="false" aria-label="Show password" aria-pressed="false">
                                    <svg class="icon-eye" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7" />
                                        <circle cx="12" cy="12" r="3" />
                                    </svg>
                                    <svg class="icon-eye-off" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                        <path d="M17.94 17.94A10.94 10.94 0 0 1 12 19c-7 0-11-7-11-7a21.77 21.77 0 0 1 2.84-3.88" />
                                        <path d="M9.88 9.88a3 3 0 0 0 4.24 4.24" />
                                        <path d="M1 1l22 22" />
                                        <path d="M22.17 16.88A11.05 11.05 0 0 0 23 12S19 5 12 5a10.94 10.94 0 0 0-4.26.9" />
                                    </svg>
                                </button>
                            </div>
                        </div>
                        <div class="auth-forgot-wrapper">
                            <a href="{{ url_for('forgot_password') }}" class="auth-footer-link auth-forgot-link">Forgot Password?</a>
                        </div>

                                        <div class="auth-actions">
                                            <button class="goo-button" type="submit" data-goo-magnet="off" data-login-progress>
                                                <span class="auth-spinner" aria-hidden="true"></span>
                                                <span class="auth-submit-text">LOGIN</span>
                                            </button>
                                        </div>
                                        <div class="auth-social-icons" role="group" aria-label="Login with a social account">
                                            <span class="auth-social-label">Sign In With</span>
                                            <a class="auth-social-icon auth-social-icon--google" href="{{ url_for('oauth_login', provider='google') }}" aria-label="Login with Google">
                                                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                                                    <path fill="#EA4335" d="M21.35 11.1H12v2.9h5.35c-.23 1.27-.96 2.35-2.05 3.07v2.56h3.31c1.94-1.78 3.07-4.41 3.07-7.53 0-.73-.07-1.43-.21-2.1Z"></path>
                                                    <path fill="#34A853" d="M12 21c2.77 0 5.09-.92 6.78-2.47l-3.31-2.56c-.92.62-2.1.99-3.47.99-2.67 0-4.94-1.8-5.75-4.22H2.84v2.65C4.52 18.98 7.97 21 12 21Z"></path>
                                                    <path fill="#FBBC05" d="M6.25 12c0-.72.12-1.41.34-2.06V7.29H2.84A9 9 0 0 0 3 12c0 1.41.34 2.75.93 3.94l3.36-2.65A5.38 5.38 0 0 1 6.25 12Z"></path>
                                                    <path fill="#4285F4" d="M12 6.15c1.51 0 2.86.52 3.92 1.55l2.93-2.93C17.09 3.2 14.77 2 12 2 7.97 2 4.52 4.02 3.07 8.06l3.52 2.65C7.06 7.95 9.33 6.15 12 6.15Z"></path>
                                                </svg>
                                            </a>
                                            <a class="auth-social-icon auth-social-icon--github" href="{{ url_for('oauth_login', provider='github') }}" aria-label="Login with GitHub">
                                                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                                                    <path d="M10.9,2.1c-4.6,0.5-8.3,4.2-8.8,8.7c-0.6,5,2.5,9.3,6.9,10.7v-2.3c0,0-0.4,0.1-0.9,0.1c-1.4,0-2-1.2-2.1-1.9 c-0.1-0.4-0.3-0.7-0.6-1C5.1,16.3,5,16.3,5,16.2C5,16,5.3,16,5.4,16c0.6,0,1.1,0.7,1.3,1c0.5,0.8,1.1,1,1.4,1c0.4,0,0.7-0.1,0.9-0.2 c0.1-0.7,0.4-1.4,1-1.8c-2.3-0.5-4-1.8-4-4c0-1.1,0.5-2.2,1.2-3C7.1,8.8,7,8.3,7,7.6C7,7.2,7,6.6,7.3,6c0,0,1.4,0,2.8,1.3 C10.6,7.1,11.3,7,12,7s1.4,0.1,2,0.3C15.3,6,16.8,6,16.8,6C17,6.6,17,7.2,17,7.6c0,0.8-0.1,1.2-0.2,1.4c0.7,0.8,1.2,1.8,1.2,3 c0,2.2-1.7,3.5-4,4c0.6,0.5,1,1.4,1,2.3v3.3c4.1-1.3,7-5.1,7-9.5C22,6.1,16.9,1.4,10.9,2.1z"></path>
                                                </svg>
                                            </a>
                                        </div>
                                        <div style="text-align:center; margin-top:0; font-weight:600;">
                                            <a href="{{ url_for('signup') }}" class="auth-footer-link">Don't have account. Sign Up</a>
                                        </div>
                            <!-- inline goo SVG filter (required by .goo-button before pseudo) -->
                            <svg width="0" height="0" style="position: absolute;">
                                <filter id="goo" x="-50%" y="-50%" width="200%" height="200%">
                                    <feComponentTransfer>
                                        <feFuncA type="discrete" tableValues="0 1"></feFuncA>
                                    </feComponentTransfer>
                                    <feGaussianBlur stdDeviation="5"></feGaussianBlur>
                                    <feComponentTransfer>
                                        <feFuncA type="table" tableValues="-5 11"></feFuncA>
                                    </feComponentTransfer>
                                </filter>
                            </svg>
                    </form>

        </main>
        <script>
            (function() {
                document.querySelectorAll('[data-password-toggle]').forEach(function(btn) {
                    var targetId = btn.getAttribute('data-password-toggle');
                    var input = document.getElementById(targetId);
                    if (!input) { return; }
                    btn.addEventListener('click', function() {
                        var isVisible = btn.getAttribute('data-visible') === 'true';
                        input.setAttribute('type', isVisible ? 'password' : 'text');
                        btn.setAttribute('data-visible', isVisible ? 'false' : 'true');
                        btn.setAttribute('aria-pressed', isVisible ? 'false' : 'true');
                        btn.setAttribute('aria-label', isVisible ? 'Show password' : 'Hide password');
                    });
                });
                var loginForm = document.querySelector('form.auth-form');
                if (loginForm) {
                    loginForm.addEventListener('submit', function() {
                        var btn = loginForm.querySelector('[data-login-progress]');
                        if (!btn || btn.dataset.loading === 'true') { return; }
                        btn.dataset.loading = 'true';
                        btn.setAttribute('aria-busy', 'true');
                        btn.setAttribute('disabled','disabled');
                        var t = btn.querySelector('.auth-submit-text');
                        if (t) t.textContent = 'Logging';
                    });
                    var demoPopup = document.getElementById('demo-credentials-popup');
                    if (demoPopup) {
                        var closeBtn = demoPopup.querySelector('[data-demo-close]');
                        var fillBtn = demoPopup.querySelector('[data-demo-fill]');
                        var emailDisplay = demoPopup.querySelector('[data-demo-email]');
                        var passwordDisplay = demoPopup.querySelector('[data-demo-password]');
                        var emailInput = document.getElementById('loginEmail');
                        var passwordInput = document.getElementById('loginPassword');

                        var focusPopup = function () {
                            var target = closeBtn || fillBtn || demoPopup;
                            if (target && typeof target.focus === 'function') {
                                target.focus({ preventScroll: true });
                            }
                        };

                        var hidePopup = function () {
                            demoPopup.dataset.visible = 'false';
                            demoPopup.setAttribute('aria-hidden', 'true');
                            document.removeEventListener('keydown', onPopupEsc);
                        };

                        var showPopup = function () {
                            demoPopup.dataset.visible = 'true';
                            demoPopup.setAttribute('aria-hidden', 'false');
                            document.addEventListener('keydown', onPopupEsc);
                            focusPopup();
                        };

                        var onPopupEsc = function (event) {
                            if (event.key === 'Escape') {
                                event.preventDefault();
                                hidePopup();
                            }
                        };

                        if (closeBtn) {
                            closeBtn.addEventListener('click', function (event) {
                                event.preventDefault();
                                hidePopup();
                            });
                        }

                        if (fillBtn) {
                            fillBtn.addEventListener('click', function (event) {
                                event.preventDefault();
                                var emailValue = (emailDisplay && emailDisplay.textContent || '').trim();
                                var passwordValue = (passwordDisplay && passwordDisplay.textContent || '').trim();
                                if (emailInput) {
                                    emailInput.value = emailValue;
                                }
                                if (passwordInput) {
                                    passwordInput.value = passwordValue;
                            showPopup();
                                }
                                hidePopup();
                                if (emailInput && typeof emailInput.focus === 'function') {
                                    emailInput.focus({ preventScroll: true });
                                }
                            });
                        }

                        // Show popup immediately on page load
                        showPopup();
                    }
                }
            })();
        </script>
        <script src="{{ url_for('static', filename='js/cursor.js') }}"></script>
        <script src="{{ url_for('static', filename='js/theme.js') }}"></script>
        <script src="{{ url_for('static', filename='js/goo-buttons.js') }}"></script>
        <script src="{{ url_for('static', filename='js/start.js') }}"></script>
    </body>
</html>
"""


_verify_otp_form = """
<!doctype html>
<html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>Verify Email • IntervBot</title>
        <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}" />
        <link rel="stylesheet" href="{{ url_for('static', filename='css/start.css') }}" />
        <link rel="stylesheet" href="{{ url_for('static', filename='css/auth.css') }}" />
    </head>
    <body class="auth-page">
        <script>
            (function () {
                try {
                    var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
                    var theme = prefersDark ? 'theme-dark' : 'theme-light';
                    document.documentElement.dataset.theme = theme;
                    document.documentElement.style.colorScheme = theme === 'theme-dark' ? 'dark' : 'light';
                    if (document.body) {
                        document.body.classList.remove('theme-light', 'theme-dark');
                        document.body.classList.add(theme);
                        document.body.dataset.theme = theme;
                    }
                } catch (e) {
                    // ignore theme storage errors
                }
            })();
        </script>
        {% set flash_messages = get_flashed_messages() %}
        {% set ns = namespace(hero=None, danger=None, fallback=None) %}
        {% if flash_messages %}
        {% set hero_messages = ['Account Created Successfully', 'Verification Code Sent to Your Email', 'Temporary Password Sent to Your Email'] %}
        {% set danger_messages = [
            'Name, Email and Password are Required',
            'Email and OTP are Required',
            'No Code Found. Please Signup Again',
            'Your Code is Expired. Resend Code',
            'Incorrect Verification Code. Please Try Again',
            'Your Signup Session Expired. Resend Code',
            'Failed to Create Account. Please try Again',
            'Failed to Send OTP. Please try Again',
            'Account Already Exists',
            'Email is Required',
            'No Account Exists with this Email',
            'Unable to Reset Password. Try Again',
            'Failed to Send Password. Please try Again',
            'Email and Password are Required',
            'Invalid credentials',
            'Unsupported Login Provider',
            'Google Login is not Configured Yet',
            'GitHub Login is not Configured Yet',
            'Server Misconfiguration. Please Contact Support',
            "Couldn't Signin. Please Try Again",
            "Couldn't Retrieve Your Profile From Provider",
            'Your Account Must Have Public Email to Signin',
            'Unable to Sign You In Right Now. Please Try Again Later',
            'Please Login to View Dashboard',
            'Admin Access Required',
            'Demo/test accounts are not managed from this panel.',
            'You cannot change your own admin status from this panel.',
            'User Not Found',
            'Temporary Password is Required to Reset User Password',
            'Email Already in Use. Try Another',
            'Admin Cannot Delete own Account from Panel'
        ] %}
        {% for message in flash_messages %}
        {% if not ns.danger and message in danger_messages %}
        {% set ns.danger = message %}
        {% elif not ns.hero and message in hero_messages %}
        {% set ns.hero = message %}
        {% elif not ns.fallback %}
        {% set ns.fallback = message %}
        {% endif %}
        {% endfor %}
        {% endif %}
        {% if ns.hero %}
        <div id="logout-toast" class="logout-toast" role="alert" aria-live="polite" aria-hidden="false" data-logout-active="1" tabindex="-1" aria-labelledby="logout-toast-message">
            <div class="logout-toast-content">
                <p id="logout-toast-message" class="logout-toast-message">{{ ns.hero }}</p>
                <button type="button" class="logout-toast-close" aria-label="Close" data-dismiss-toast>
                    <span class="sr-only">Close</span>
                    <svg class="logout-toast-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M18 6 6 18"></path>
                        <path d="m6 6 12 12"></path>
                    </svg>
                </button>
            </div>
        </div>
        {% elif ns.danger %}
        <div id="logout-toast" class="logout-toast logout-toast--danger" role="alert" aria-live="assertive" aria-hidden="false" data-logout-active="1" tabindex="-1" aria-labelledby="logout-toast-message">
            <div class="logout-toast-content">
                <p id="logout-toast-message" class="logout-toast-message logout-toast-message--danger">&#9888;&#65039; {{ ns.danger }}</p>
                <button type="button" class="logout-toast-close" aria-label="Close" data-dismiss-toast>
                    <span class="sr-only">Close</span>
                    <svg class="logout-toast-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M18 6 6 18"></path>
                        <path d="m6 6 12 12"></path>
                    </svg>
                </button>
            </div>
        </div>
        {% elif ns.fallback %}
        <div class="auth-toast show" role="status" aria-live="polite" aria-hidden="false">
            <span class="auth-toast-text">{{ ns.fallback }}</span>
        </div>
        {% endif %}
        <main class="auth-card">
            <div class="auth-header">
                <h1 class="auth-title">Verify Your Email</h1>
            </div>
            

            <form class="auth-form auth-form-modern" method="post">
                <input type="hidden" name="email" value="{{ email or '' }}" />
                <div class="auth-field auth-otp-field">
                    <label for="verifyOtp">One-Time Password</label>
                    <div class="auth-input-shell">
                        <span class="auth-input-icon" aria-hidden="true">
                            <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                <path d="M7 7h0"></path>
                                <path d="M12 7h0"></path>
                                <path d="M17 7h0"></path>
                                <path d="M7 12h0"></path>
                                <path d="M12 12h0"></path>
                                <path d="M17 12h0"></path>
                                <path d="M7 17h0"></path>
                                <path d="M12 17h0"></path>
                                <path d="M17 17h0"></path>
                            </svg>
                        </span>
                        <input class="auth-input" type="text" name="otp" id="verifyOtp" maxlength="6" minlength="6" pattern="\\d{6}" inputmode="numeric" autocomplete="one-time-code" placeholder="Enter 6-digit code" required />
                    </div>
                </div>
                <div class="auth-actions">
                    <button class="goo-button" type="submit" data-goo-magnet="off" data-verify-progress>
                        <span class="auth-spinner" aria-hidden="true"></span>
                        <span class="auth-submit-text">VERIFY</span>
                    </button>
                </div>
            </form>
            <div class="auth-footer">
                Didn't get the code?
                <a href="{{ url_for('signup') }}" class="auth-footer-link">Try Signing Up Again</a>
            </div>
            <svg width="0" height="0" style="position: absolute;">
                <filter id="goo" x="-50%" y="-50%" width="200%" height="200%">
                    <feComponentTransfer>
                        <feFuncA type="discrete" tableValues="0 1"></feFuncA>
                    </feComponentTransfer>
                    <feGaussianBlur stdDeviation="5"></feGaussianBlur>
                    <feComponentTransfer>
                        <feFuncA type="table" tableValues="-5 11"></feFuncA>
                    </feComponentTransfer>
                </filter>
            </svg>
        </main>
        <script>
            (function(){
                var verifyForm = document.querySelector('form.auth-form');
                if (verifyForm) {
                    verifyForm.addEventListener('submit', function() {
                        var btn = verifyForm.querySelector('[data-verify-progress]');
                        if (!btn || btn.dataset.loading === 'true') { return; }
                        btn.dataset.loading = 'true';
                        btn.setAttribute('aria-busy', 'true');
                        btn.setAttribute('disabled','disabled');
                        var t = btn.querySelector('.auth-submit-text');
                        if (t) t.textContent = 'Verifying';
                    });
                }
            })();
        </script>
        <script src="{{ url_for('static', filename='js/cursor.js') }}"></script>
        <script src="{{ url_for('static', filename='js/theme.js') }}"></script>
        <script src="{{ url_for('static', filename='js/goo-buttons.js') }}"></script>
        <script src="{{ url_for('static', filename='js/start.js') }}"></script>
    </body>
</html>
"""


_forgot_password_form = """
<!doctype html>
<html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>Forgot Password • IntervBot</title>
        <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}" />
        <link rel="stylesheet" href="{{ url_for('static', filename='css/start.css') }}" />
        <link rel="stylesheet" href="{{ url_for('static', filename='css/auth.css') }}" />
    </head>
    <body class="auth-page">
        <script>
            (function () {
                try {
                    var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
                    var theme = prefersDark ? 'theme-dark' : 'theme-light';
                    document.documentElement.dataset.theme = theme;
                    document.documentElement.style.colorScheme = theme === 'theme-dark' ? 'dark' : 'light';
                    if (document.body) {
                        document.body.classList.remove('theme-light', 'theme-dark');
                        document.body.classList.add(theme);
                        document.body.dataset.theme = theme;
                    }
                } catch (e) {
                    // ignore theme storage errors
                }
            })();
        </script>
        <main class="auth-card">
            <div class="auth-header">
                <h1 class="auth-title">Reset Password</h1>
            </div>
            <p class="auth-desc">Enter Your Email to Get Temp Password</p>
            {% with messages = get_flashed_messages() %}
            {% set ns = namespace(hero=None, danger=None, fallback=None) %}
            {% if messages %}
            {% set hero_messages = ['Account Created Successfully', 'Verification Code Sent to Your Email', 'Temporary Password Sent to Your Email'] %}
            {% set danger_messages = [
                'Name, Email and Password are Required',
                'Email and OTP are Required',
                'No Code Found. Please Signup Again',
                'Your Code is Expired. Resend Code',
                'Incorrect Verification Code. Please Try Again',
                'Your Signup Session Expired. Resend Code',
                'Failed to Create Account. Please try Again',
                'Failed to Send OTP. Please try Again',
                'Account Already Exists',
                'Email is Required',
                'No Account Exists with this Email',
                'Unable to Reset Password. Try Again',
                'Failed to Send Password. Please try Again',
                'Email and Password are Required',
                'Invalid credentials',
                'Unsupported Login Provider',
                'Google Login is not Configured Yet',
                'GitHub Login is not Configured Yet',
                'Server Misconfiguration. Please Contact Support',
                "Couldn't Signin. Please Try Again",
                "Couldn't Retrieve Your Profile From Provider",
                'Your Account Must Have Public Email to Signin',
                'Unable to Sign You In Right Now. Please Try Again Later',
                'Please Login to View Dashboard',
                'Admin Access Required',
                'Demo/test accounts are not managed from this panel.',
                'You cannot change your own admin status from this panel.',
                'User Not Found',
                'Temporary Password is Required to Reset User Password',
                'Email Already in Use. Try Another',
                'Admin Cannot Delete own Account from Panel'
            ] %}
            {% for message in messages %}
            {% if not ns.danger and message in danger_messages %}
            {% set ns.danger = message %}
            {% elif not ns.hero and message in hero_messages %}
            {% set ns.hero = message %}
            {% elif not ns.fallback %}
            {% set ns.fallback = message %}
            {% endif %}
            {% endfor %}
            {% endif %}
            {% if ns.hero %}
            <div id="logout-toast" class="logout-toast" role="alert" aria-live="polite" aria-hidden="false" data-logout-active="1" tabindex="-1" aria-labelledby="logout-toast-message">
                <div class="logout-toast-content">
                    <p id="logout-toast-message" class="logout-toast-message">{{ ns.hero }}</p>
                    <button type="button" class="logout-toast-close" aria-label="Close" data-dismiss-toast>
                        <span class="sr-only">Close</span>
                        <svg class="logout-toast-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M18 6 6 18"></path>
                            <path d="m6 6 12 12"></path>
                        </svg>
                    </button>
                </div>
            </div>
            {% elif ns.danger %}
            <div id="logout-toast" class="logout-toast logout-toast--danger" role="alert" aria-live="assertive" aria-hidden="false" data-logout-active="1" tabindex="-1" aria-labelledby="logout-toast-message">
                <div class="logout-toast-content">
                    <p id="logout-toast-message" class="logout-toast-message logout-toast-message--danger">&#9888;&#65039; {{ ns.danger }}</p>
                    <button type="button" class="logout-toast-close" aria-label="Close" data-dismiss-toast>
                        <span class="sr-only">Close</span>
                        <svg class="logout-toast-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M18 6 6 18"></path>
                            <path d="m6 6 12 12"></path>
                        </svg>
                    </button>
                </div>
            </div>
            {% elif ns.fallback %}
            <div class="auth-toast show" role="status" aria-live="polite" aria-hidden="false">
                <span class="auth-toast-text">{{ ns.fallback }}</span>
            </div>
            {% endif %}
            {% endwith %}

            <form class="auth-form auth-form-modern" method="post">
                <div class="auth-field">
                    <label for="resetEmail">Email</label>
                    <div class="auth-input-shell">
                        <span class="auth-input-icon" aria-hidden="true">
                            <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"></path>
                                <polyline points="22,6 12,13 2,6"></polyline>
                            </svg>
                        </span>
                        <input class="auth-input" type="email" name="email" id="resetEmail" value="{{ email or '' }}" placeholder="Enter email" required />
                    </div>
                </div>
                <div class="auth-actions">
                    <button class="goo-button" type="submit" data-goo-magnet="off" aria-live="polite" data-reset-progress>
                        <span class="auth-spinner" aria-hidden="true"></span>
                        <span class="auth-submit-text">SEND</span>
                    </button>
                </div>
            </form>
            <div class="auth-footer">
                Try Your Password?
                <a href="{{ url_for('login') }}" class="auth-footer-link">Back to login</a>
            </div>
            <svg width="0" height="0" style="position: absolute;">
                <filter id="goo" x="-50%" y="-50%" width="200%" height="200%">
                    <feComponentTransfer>
                        <feFuncA type="discrete" tableValues="0 1"></feFuncA>
                    </feComponentTransfer>
                    <feGaussianBlur stdDeviation="5"></feGaussianBlur>
                    <feComponentTransfer>
                        <feFuncA type="table" tableValues="-5 11"></feFuncA>
                    </feComponentTransfer>
                </filter>
            </svg>
        </main>
        <script src="{{ url_for('static', filename='js/cursor.js') }}"></script>
        <script src="{{ url_for('static', filename='js/theme.js') }}"></script>
        <script src="{{ url_for('static', filename='js/goo-buttons.js') }}"></script>
        <script src="{{ url_for('static', filename='js/start.js') }}"></script>
        <script>
            // Disable the submit button and show a spinner while sending
            (function() {
                const form = document.querySelector('.auth-form');
                if (!form) return;
                const btn = form.querySelector('[data-reset-progress]');
                if (!btn) return;
                form.addEventListener('submit', function() {
                    // Prevent double submissions while providing text feedback
                    btn.dataset.loading = 'true';
                    btn.setAttribute('aria-busy', 'true');
                    btn.disabled = true;
                    const txt = btn.querySelector('.auth-submit-text');
                    if (txt) txt.textContent = 'Sending';
                }, { once: true });
            })();
        </script>
    </body>
</html>
"""


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        gender = request.form.get('gender', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # Basic validation
        if not name or not email or not password:
            flash('Name, Email and Password are Required')
            return render_template_string(_signup_form)

        # Check existing user
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('Account Already Exists')
            return render_template_string(_signup_form)

        otp_code = f"{secrets.randbelow(1_000_000):06d}"
        expiry_time = datetime.utcnow() + timedelta(minutes=5)
        password_hash = wz_generate_password_hash(password)
        session['pending_signup'] = {
            'email': email,
            'name': name,
            'gender': gender,
            'password_hash': password_hash,
        }
        session['pending_signup_email'] = email

        try:
            OTPVerification.query.filter_by(email=email).delete()
            entry = OTPVerification(email=email, otp=otp_code, expiry_time=expiry_time, attempts=0)
            db.session.add(entry)
            db.session.flush()
            _send_otp_email(email, otp_code)
            db.session.commit()
        except Exception:
            db.session.rollback()
            session.pop('pending_signup', None)
            session.pop('pending_signup_email', None)
            flash('Failed to Send OTP. Please try Again')
            return render_template_string(_signup_form)

        flash('Verification Code Sent to Your Email')
        return redirect(url_for('verify_otp'))

    return render_template_string(_signup_form)


@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    prefill_email = session.get('pending_signup_email', '')

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        otp_value = (request.form.get('otp') or '').strip()

        if not email or not otp_value:
            flash('Email and OTP are Required')
            return render_template_string(_verify_otp_form, email=email)

        record = OTPVerification.query.filter_by(email=email).first()
        if not record:
            flash('No Code Found. Please Signup Again')
            return render_template_string(_verify_otp_form, email=email)

        if record.attempts >= OTP_MAX_ATTEMPTS:
            try:
                OTPVerification.query.filter_by(email=email).delete()
                db.session.commit()
            except Exception:
                db.session.rollback()
            session.pop('pending_signup', None)
            session.pop('pending_signup_email', None)
            flash('Too Many Incorrect Attempts. Please Signup Again')
            return render_template_string(_verify_otp_form, email=email)

        if record.expiry_time < datetime.utcnow():
            try:
                OTPVerification.query.filter_by(email=email).delete()
                db.session.commit()
            except Exception:
                db.session.rollback()
            session.pop('pending_signup', None)
            session.pop('pending_signup_email', None)
            flash('Your Code is Expired. Resend Code')
            return render_template_string(_verify_otp_form, email=email)

        if record.otp != otp_value:
            try:
                record.attempts = int(record.attempts or 0) + 1
                db.session.add(record)
                db.session.commit()
            except Exception:
                db.session.rollback()
            if record.attempts >= OTP_MAX_ATTEMPTS:
                try:
                    OTPVerification.query.filter_by(email=email).delete()
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                session.pop('pending_signup', None)
                session.pop('pending_signup_email', None)
                flash('Too Many Incorrect Attempts. Please Signup Again')
                return render_template_string(_verify_otp_form, email=email)
            flash('Incorrect Verification Code. Please Try Again')
            return render_template_string(_verify_otp_form, email=email)

        pending = session.get('pending_signup')
        if not pending or pending.get('email') != email:
            flash('Your Signup Session Expired. Resend Code')
            return render_template_string(_verify_otp_form, email=email)

        try:
            user = User(
                name=pending.get('name'),
                gender=pending.get('gender'),
                email=email,
                password_hash=pending.get('password_hash')
            )
            db.session.add(user)
            db.session.flush()

            username = _generate_unique_username(pending.get('name'))
            profile = Profile(user_id=user.id, username=username)
            db.session.add(profile)

            OTPVerification.query.filter_by(email=email).delete()
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Failed to Create Account. Please try Again')
            return render_template_string(_verify_otp_form, email=email)

        session.pop('pending_signup', None)
        session.pop('pending_signup_email', None)
        flash('Account Created Successfully')
        return redirect(url_for('login'))

    return render_template_string(_verify_otp_form, email=prefill_email)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    prefill_email = request.args.get('email', '')

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Email is Required')
            return render_template_string(_forgot_password_form, email=email)

        user = User.query.filter_by(email=email).first()
        if not user:
            flash('No Account Exists with this Email')
            return render_template_string(_forgot_password_form, email=email)

        temp_password = _generate_temp_password()
        new_hash = wz_generate_password_hash(temp_password)
        old_hash = user.password_hash

        try:
            user.password_hash = new_hash
            db.session.add(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Unable to Reset Password. Try Again')
            return render_template_string(_forgot_password_form, email=email)

        try:
            _send_reset_password_email(email, temp_password)
        except Exception:
            try:
                user.password_hash = old_hash
                db.session.add(user)
                db.session.commit()
            except Exception:
                db.session.rollback()
            flash('Failed to Send Password. Please try Again')
            return render_template_string(_forgot_password_form, email=email)

        flash('Temporary Password Sent to Your Email')
        return redirect(url_for('login'))

    if request.method == 'GET' and prefill_email:
        prefill_email = prefill_email.strip().lower()

    return render_template_string(_forgot_password_form, email=prefill_email)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not identifier or not password:
            flash('Email and Password are Required')
            return render_template_string(_login_form)

        user = _find_user_by_login_identifier(identifier)
        if not user or not user.check_password(password):
            flash('Invalid credentials')
            return render_template_string(_login_form)

        # Login success
        _start_user_session(user)

        # redirect to landing page as requested
        return redirect(url_for('landing'))

    return render_template_string(_login_form)


@app.route('/auth/<provider>')
def oauth_login(provider):
    provider = (provider or '').lower()
    if provider not in ('google', 'github'):
        flash('Unsupported Login Provider')
        return redirect(url_for('login'))

    if not OAUTH_PROVIDERS.get(provider):
        display_provider = 'GitHub' if provider == 'github' else provider.title()
        flash(f"{display_provider} Login is not Configured Yet")
        return redirect(url_for('login'))

    client = oauth.create_client(provider)
    if client is None:
        flash('Server Misconfiguration. Please Contact Support')
        return redirect(url_for('login'))

    redirect_uri = url_for('oauth_callback', provider=provider, _external=True)
    if provider == 'github':
        return client.authorize_redirect(redirect_uri, scope='read:user user:email')
    return client.authorize_redirect(redirect_uri)


@app.route('/auth/<provider>/callback')
def oauth_callback(provider):
    provider = (provider or '').lower()
    if provider not in ('google', 'github'):
        flash('Unsupported Login Provider')
        return redirect(url_for('login'))

    if not OAUTH_PROVIDERS.get(provider):
        display_provider = 'GitHub' if provider == 'github' else provider.title()
        flash(f"{display_provider} Login is not Configured Yet")
        return redirect(url_for('login'))

    client = oauth.create_client(provider)
    if client is None:
        flash('Server Misconfiguration. Please Contact Support')
        return redirect(url_for('login'))

    try:
        token = client.authorize_access_token()
    except Exception as exc:
        app.logger.exception('OAuth token exchange failed for %s: %s', provider, exc)
        flash("Couldn't Signin. Please Try Again")
        return redirect(url_for('login'))

    try:
        email = None
        name = None
        avatar_url = None
        provider_user_id = None
        birthdate = None
        location = None

        if provider == 'google':
            user_info = None
            try:
                user_info = client.parse_id_token(token)
            except Exception:
                user_info = None
            if not user_info:
                response = None
                try:
                    response = client.get('userinfo', token=token)
                except Exception:
                    # Fallback to explicit OpenID Connect endpoint
                    response = client.get('https://openidconnect.googleapis.com/v1/userinfo', token=token)
                response.raise_for_status()
                user_info = response.json()
            email = (user_info or {}).get('email')
            name = (user_info or {}).get('name')
            avatar_url = (user_info or {}).get('picture')
            provider_user_id = (user_info or {}).get('sub')
            birthdate = (user_info or {}).get('birthdate')
            location = (user_info or {}).get('locale') or (user_info or {}).get('zoneinfo')
        else:  # github
            response = client.get('user')
            response.raise_for_status()
            user_info = response.json()
            email = user_info.get('email')
            if not email:
                emails_resp = client.get('user/emails')
                if emails_resp.status_code == 200:
                    for entry in emails_resp.json():
                        if entry.get('verified') and entry.get('primary'):
                            email = entry.get('email')
                            break
                    if not email:
                        email_entries = emails_resp.json()
                        if email_entries:
                            email = email_entries[0].get('email')
            name = user_info.get('name') or user_info.get('login')
            avatar_url = user_info.get('avatar_url')
            provider_user_id = user_info.get('id')
            location = user_info.get('location')
    except Exception as exc:
        app.logger.exception('Failed to retrieve user info from %s: %s', provider, exc)
        flash("Couldn't Retrieve Your Profile From Provider")
        return redirect(url_for('login'))

    if not email:
        flash('Your Account Must Have Public Email to Signin')
        return redirect(url_for('login'))

    try:
        user, _created = _get_or_create_oauth_user(
            email,
            name,
            provider,
            provider_user_id,
            avatar_url=avatar_url,
            birthdate=birthdate,
            location=location,
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        app.logger.exception('Failed to persist OAuth login for %s: %s', provider, exc)
        flash('Unable to Sign You In Right Now. Please Try Again Later')
        return redirect(url_for('login'))

    _start_user_session(
        user,
        avatar_override=avatar_url,
        extras={'name': name, 'location': location, 'dob': birthdate},
    )
    session['auth_provider'] = provider
    return redirect(url_for('landing'))


@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        flash('Please Login to View Dashboard')
        return redirect(url_for('login'))
    # Prefer session email; fallback to DB if needed
    user_email = session.get('user_email')
    if not user_email and session.get('user_id'):
        try:
            u = User.query.get(session['user_id'])
            user_email = u.email if u else None
        except Exception:
            user_email = None
    # Determine avatar url quickly from session or fallback to DB
    avatar_url = session.get('avatar_url')
    if not avatar_url and session.get('user_id'):
        try:
            meta = UserMeta.query.filter_by(user_id=session['user_id']).first()
            if meta and meta.profile_pic:
                avatar_url = _avatar_url_for(meta.profile_pic, session['user_id'], cache_bust=False)
        except Exception:
            avatar_url = None
    leaderboard_entries = _build_leaderboard(limit=50)
    leaderboard_entry = None
    current_user_id = session.get('user_id')
    if current_user_id:
        for entry in leaderboard_entries:
            if entry.get('user_id') == current_user_id:
                leaderboard_entry = entry
                break

    return render_template(
        'dashboard.html',
        user_email=user_email,
        avatar_url=avatar_url,
        leaderboard_entry=leaderboard_entry,
    )


@app.route('/leaderboard')
def leaderboard():
    entries = _build_leaderboard(limit=50)
    return render_template('leaderboard.html', leaderboard_entries=entries)


@app.route('/logout')
def logout():
    session.clear()
    response = redirect(url_for('start_page', logged_out=1))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Clear-Site-Data'] = '"cache", "cookies", "storage", "executionContexts"'
    return response


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
def _require_admin():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    if not session.get('is_admin'):
        flash('Admin Access Required')
        return redirect(url_for('landing'))


@admin_bp.route('/')
def admin_dashboard():
    excluded_ids = _get_excluded_user_ids()

    user_query = User.query
    timelog_query = TimeLog.query

    if excluded_ids:
        excluded_list = list(excluded_ids)
        user_query = user_query.filter(~User.id.in_(excluded_list))
        timelog_query = timelog_query.filter(~TimeLog.user_id.in_(excluded_list))

    total_users = user_query.count()
    total_time_logs = timelog_query.count()

    recent_users = user_query.order_by(User.id.desc()).limit(5).all()

    return render_template(
        'index.html',
        page='admin',
        title='Admin Overview',
        current_view='dashboard',
        total_users=total_users,
        total_time_logs=total_time_logs,
        recent_users=recent_users,
    )


@admin_bp.route('/users')
def admin_users():
    excluded_ids = _get_excluded_user_ids()
    users_query = User.query
    if excluded_ids:
        users_query = users_query.filter(~User.id.in_(list(excluded_ids)))
    users = users_query.order_by(User.id.desc()).all()
    profile_map = {}
    user_ids = [u.id for u in users]
    if user_ids:
        profile_map = {
            p.user_id: p
            for p in Profile.query.filter(Profile.user_id.in_(user_ids)).all()
        }
    return render_template(
        'index.html',
        page='admin',
        title='Manage Users',
        current_view='users',
        users=users,
        profile_map=profile_map,
    )


@admin_bp.post('/users/<int:user_id>/toggle-admin')
def admin_toggle_admin(user_id):
    if user_id in _get_excluded_user_ids():
        flash('Demo/test accounts are not managed from this panel.')
        return redirect(url_for('admin.admin_users'))

    if user_id == session.get('user_id'):
        flash('You cannot change your own admin status from this panel.')
        return redirect(url_for('admin.admin_users'))

    user = User.query.filter_by(id=user_id).first()
    if not user:
        flash('User Not Found')
        return redirect(url_for('admin.admin_users'))

    try:
        user.is_admin = not bool(user.is_admin)
        db.session.commit()
        flash(f"{'Granted' if user.is_admin else 'Revoked'} admin access for {user.email}")
    except Exception as exc:
        db.session.rollback()
        flash(f'Failed to update admin access: {exc}')

    return redirect(url_for('admin.admin_users'))


@admin_bp.post('/users/<int:user_id>/reset-password')
def admin_reset_password(user_id):
    temp_password = request.form.get('temporary_password', '').strip()
    if not temp_password:
        flash('Temporary Password is Required to Reset User Password')
        return redirect(url_for('admin.admin_users'))

    if user_id in _get_excluded_user_ids():
        flash('Demo/test accounts are not managed from this panel.')
        return redirect(url_for('admin.admin_users'))

    user = User.query.filter_by(id=user_id).first()
    if not user:
        flash('User Not Found')
        return redirect(url_for('admin.admin_users'))

    try:
        user.password_hash = wz_generate_password_hash(temp_password)
        db.session.commit()
        flash(f'Password Resets For {user.name}')
    except Exception as exc:
        db.session.rollback()
        flash(f'Failed to reset password: {exc}')

    return redirect(url_for('admin.admin_users'))


@admin_bp.post('/users/<int:user_id>/update')
def admin_update_user(user_id):
    if user_id in _get_excluded_user_ids():
        flash('Demo/test accounts are not managed from this panel.')
        return redirect(url_for('admin.admin_users'))

    user = User.query.filter_by(id=user_id).first()
    if not user:
        flash('User Not Found')
        return redirect(url_for('admin.admin_users'))

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    location = request.form.get('location', '').strip()

    if email and email != user.email:
        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != user_id:
            flash('Email Already in Use. Try Another')
            return redirect(url_for('admin.admin_users'))

    try:
        if name:
            user.name = name
        if email:
            user.email = email

        meta = UserMeta.query.filter_by(user_id=user_id).first()
        if not meta:
            meta = UserMeta(user_id=user_id)
            db.session.add(meta)

        profile = Profile.query.filter_by(user_id=user_id).first()
        if not profile:
            profile = Profile(user_id=user_id)
            db.session.add(profile)

        if 'location' in request.form:
            profile.location = location or None

        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Failed to update user: {exc}')

    return redirect(url_for('admin.admin_users'))


@admin_bp.post('/users/<int:user_id>/delete')
def admin_delete_user(user_id):
    if user_id == session.get('user_id'):
        flash('Admin Cannot Delete own Account from Panel')
        return redirect(url_for('admin.admin_users'))

    if user_id in _get_excluded_user_ids():
        flash('Demo/test accounts are not managed from this panel.')
        return redirect(url_for('admin.admin_users'))

    user = User.query.filter_by(id=user_id).first()
    if not user:
        flash('User Not Found')
        return redirect(url_for('admin.admin_users'))

    try:
        for record in Profile.query.filter_by(user_id=user_id).all():
            db.session.delete(record)
        for record in UserMeta.query.filter_by(user_id=user_id).all():
            db.session.delete(record)
        for record in Result.query.filter_by(user_id=user_id).all():
            db.session.delete(record)
        for record in TimeLog.query.filter_by(user_id=user_id).all():
            db.session.delete(record)
        media_entry = ProfileMedia.query.filter_by(user_id=user_id).first()
        if media_entry:
            db.session.delete(media_entry)

        db.session.delete(user)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f'Failed to delete user: {exc}')

    return redirect(url_for('admin.admin_users'))

app.register_blueprint(admin_bp)


@app.route('/media/profile/<int:user_id>')
def profile_media(user_id):
    media = ProfileMedia.query.filter_by(user_id=user_id).first()
    if not media or not media.data:
        abort(404)
    buffer = io.BytesIO(media.data)
    buffer.seek(0)
    response = send_file(
        buffer,
        mimetype=media.content_type or 'image/png',
        as_attachment=False,
        download_name=f"avatar-{user_id}.png",
    )
    response.headers['Cache-Control'] = 'private, max-age=86400'
    if media.updated_at:
        response.headers['Last-Modified'] = http_date(media.updated_at)
    return response


@app.route('/api/profile_picture', methods=['POST', 'DELETE'])
def profile_picture():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = session['user_id']

    # Upload new picture
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        f = request.files['file']
        if f.filename == '':
            return jsonify({'success': False, 'error': 'Empty filename'}), 400
        mimetype = (f.mimetype or '').lower()
        if mimetype and mimetype not in ALLOWED_IMAGE_MIMETYPES:
            return jsonify({'success': False, 'error': 'Unsupported image type'}), 400
        f.stream.seek(0)
        blob = f.read()
        if not blob:
            return jsonify({'success': False, 'error': 'Empty file'}), 400
        if len(blob) > PROFILE_UPLOAD_MAX_BYTES:
            return jsonify({'success': False, 'error': 'File too large'}), 400
        try:
            meta = UserMeta.query.filter_by(user_id=user_id).first()
        except Exception:
            # if migration not applied, try to add columns and retry
            _ensure_usermeta_columns()
            meta = UserMeta.query.filter_by(user_id=user_id).first()
        if not meta:
            meta = UserMeta(user_id=user_id)
            db.session.add(meta)
        legacy_path = None
        if meta.profile_pic and not meta.profile_pic.startswith('media/profile/'):
            legacy_path = os.path.join(app.root_path, 'static', meta.profile_pic.replace('\\', '/'))
        media = ProfileMedia.query.filter_by(user_id=user_id).first()
        if not media:
            media = ProfileMedia(user_id=user_id)
        media.content_type = mimetype or 'image/png'
        media.data = blob
        db.session.add(media)
        meta.profile_pic = f"media/profile/{user_id}"
        db.session.commit()
        if legacy_path and os.path.exists(legacy_path):
            try:
                os.remove(legacy_path)
            except Exception:
                pass
        resolved_url = _avatar_url_for(meta.profile_pic, user_id, cache_bust=True)
        # Update session avatar for immediate persistence across navigation
        try:
            session['avatar_url'] = resolved_url
        except Exception:
            pass
        return jsonify({'success': True, 'path': meta.profile_pic, 'url': resolved_url})

    # Remove existing picture
    if request.method == 'DELETE':
        try:
            try:
                meta = UserMeta.query.filter_by(user_id=user_id).first()
            except Exception:
                _ensure_usermeta_columns()
                meta = UserMeta.query.filter_by(user_id=user_id).first()
            if meta and meta.profile_pic:
                # attempt to delete file
                rel = meta.profile_pic.replace('\\','/')
                if not rel.startswith('media/profile/'):
                    file_path = os.path.join(app.root_path, 'static', rel)
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except Exception:
                        # ignore file delete errors
                        pass
                meta.profile_pic = None
                db.session.add(meta)
            media = ProfileMedia.query.filter_by(user_id=user_id).first()
            if media:
                db.session.delete(media)
            db.session.commit()
            # Clear session avatar on delete
            try:
                session['avatar_url'] = None
            except Exception:
                pass
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/profile_update', methods=['POST'])
def profile_update():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = session['user_id']
    data = request.get_json() or {}
    name = data.get('name')
    contact = data.get('contact')
    try:
        user = User.query.get(user_id)
        if name:
            user.name = name
        db.session.add(user)
        try:
            meta = UserMeta.query.filter_by(user_id=user_id).first()
        except Exception:
            _ensure_usermeta_columns()
            meta = UserMeta.query.filter_by(user_id=user_id).first()
        if not meta:
            meta = UserMeta(user_id=user_id, contact=contact)
            db.session.add(meta)
        else:
            meta.contact = contact
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/update_profile', methods=['POST'])
def update_profile():
    """Accepts POST form or JSON to update extended profile fields and returns JSON."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = session['user_id']
    # accept JSON or form data
    data = {}
    if request.is_json:
        data = request.get_json() or {}
    else:
        # combine form and files (we ignore files here; picture upload handled at /api/profile_picture)
        for k, v in request.form.items():
            data[k] = v
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        # update simple fields
        name = (data.get('name') or '').strip()
        if name:
            user.name = name
        if 'gender' in data:
            gender_val = (data.get('gender') or '').strip()
            user.gender = gender_val or None
        # update metadata
        meta = UserMeta.query.filter_by(user_id=user_id).first()
        if not meta:
            meta = UserMeta(user_id=user_id)
            db.session.add(meta)
        # assign allowed keys (UserMeta)
        for k in ('contact', 'github', 'linkedin', 'website', 'address', 'course'):
            if k in data:
                setattr(meta, k, (data.get(k) or '').strip() if data.get(k) is not None else None)
        if 'dob' in data:
            dob_val = (data.get('dob') or '').strip()
            meta.dob = dob_val or None
        # profile-specific fields live in Profile table
        prof = Profile.query.filter_by(user_id=user_id).first()
        if not prof:
            prof = Profile(user_id=user_id)
            db.session.add(prof)
        if 'username' in data:
            desired_username = _sanitize_username(data.get('username'))
            if desired_username and _username_taken(desired_username, exclude_user_id=user_id):
                return jsonify({'success': False, 'error': 'Username already taken. Choose another.'}), 400
            prof.username = desired_username
        for k in ('bio', 'university', 'location', 'pronouns'):
            if k in data:
                setattr(prof, k, (data.get(k) or '').strip() if data.get(k) is not None else None)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# New unified profile API for dashboard persistence
@app.route('/api/profile', methods=['GET', 'POST'])
def api_profile():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = session['user_id']

    if request.method == 'GET':
        try:
            user = User.query.get(user_id)
            meta = UserMeta.query.filter_by(user_id=user_id).first()
            prof = Profile.query.filter_by(user_id=user_id).first()
            data = {
                'name': user.name if user else '',
                'email': user.email if user else '',
                'username': prof.username if prof and prof.username else '',
                'bio': prof.bio if prof and prof.bio else '',
                'university': prof.university if prof and prof.university else '',
                'location': prof.location if prof and prof.location else '',
                'website': meta.website if meta and meta.website else '',
                'linkedin': meta.linkedin if meta and meta.linkedin else '',
                'github': meta.github if meta and meta.github else '',
                'gender': user.gender if user and user.gender else '',
                'dob': meta.dob if meta and meta.dob else '',
                'pronouns': prof.pronouns if prof and prof.pronouns else '',
                'avatar_path': meta.profile_pic if meta and meta.profile_pic else None,
            }
            # convenience URL for front-end
            data['avatar_url'] = _avatar_url_for(data['avatar_path'], user_id) if data['avatar_path'] else None
            return jsonify({'success': True, 'profile': data})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # POST -> update
    try:
        payload = request.get_json() or {}
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        # Update name if provided
        if 'name' in payload and isinstance(payload.get('name'), str):
            user.name = payload.get('name').strip()
            db.session.add(user)

        meta = UserMeta.query.filter_by(user_id=user_id).first()
        if not meta:
            meta = UserMeta(user_id=user_id)
            db.session.add(meta)
        prof = Profile.query.filter_by(user_id=user_id).first()
        if not prof:
            prof = Profile(user_id=user_id)
            db.session.add(prof)

        # Assign accepted fields safely
        for key in ['website', 'linkedin', 'github', 'contact', 'address', 'course']:
            if key in payload:
                val = payload.get(key)
                setattr(meta, key, (val or '').strip() if isinstance(val, str) else val)
        if 'dob' in payload:
            dob_val = payload.get('dob')
            meta.dob = (dob_val or '').strip() if isinstance(dob_val, str) and dob_val.strip() else None
        if 'gender' in payload:
            gender_val = payload.get('gender')
            user.gender = (gender_val or '').strip() if isinstance(gender_val, str) and gender_val.strip() else None
        if 'username' in payload:
            desired_username = _sanitize_username(payload.get('username'))
            if desired_username and _username_taken(desired_username, exclude_user_id=user_id):
                return jsonify({'success': False, 'error': 'Username already taken. Choose another.'}), 400
            prof.username = desired_username
        for key in ['bio', 'university', 'location', 'pronouns']:
            if key in payload:
                val = payload.get(key)
                setattr(prof, key, (val or '').strip() if isinstance(val, str) else val)

        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    current_password = (data.get('current_password') or '').strip()
    new_password = (data.get('new_password') or '').strip()

    if not current_password or not new_password:
        return jsonify({'success': False, 'error': 'Current and new password are required.'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'error': 'New password must be at least 6 characters long.'}), 400

    user = User.query.get(session['user_id'])
    if not user or not user.check_password(current_password):
        return jsonify({'success': False, 'error': 'Current password is incorrect.'}), 400

    try:
        user.password_hash = wz_generate_password_hash(new_password)
        db.session.add(user)
        db.session.commit()
        return jsonify({'success': True})
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Password update failed.'}), 500

# ------------------------------------------------

@app.route('/api/questions')
def get_questions():
    try:
        role = request.args.get('role')
        difficulty = request.args.get('difficulty')
        limit = request.args.get('limit', type=int)

        normalized_limit = None
        if isinstance(limit, int) and limit > 0:
            normalized_limit = min(limit, MAX_SESSION_QUESTIONS)

        questions, available = get_random_quiz_questions(role=role, difficulty=difficulty, limit=normalized_limit)

        return jsonify({
            'success': True,
            'questions': questions,
            'available': available,
            'requested': normalized_limit,
            'role': role,
            'difficulty': difficulty,
        })
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500

# Serve raw questions.json at the root path for frontend fetches
@app.route('/questions.json')
def serve_questions_json():
    try:
        # Use send_from_directory to ensure correct mimetype and caching headers
        return send_from_directory(app.root_path, 'questions.json', mimetype='application/json')
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'Questions dataset not found.'}), 404

@app.route('/api/start_interview', methods=['POST'])
def start_interview():
    try:
        _cleanup_sessions()
        data = request.get_json(silent=True) or {}

        role_raw = str(data.get('role', 'General Interview')).strip()
        role = role_raw if role_raw in ALLOWED_ROLES else 'General Interview'

        difficulty_raw = str(data.get('difficulty', 'Easy')).strip().title()
        difficulty = difficulty_raw if difficulty_raw in ALLOWED_DIFFICULTIES else 'Easy'

        try:
            limit = int(data.get('limit', 1))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Question limit must be an integer.'}), 400

        if limit < 1 or limit > MAX_SESSION_QUESTIONS:
            return jsonify({
                'success': False,
                'error': f'Question limit must be between 1 and {MAX_SESSION_QUESTIONS}.',
            }), 400

        if len(user_sessions) >= MAX_ACTIVE_SESSIONS:
            return jsonify({
                'success': False,
                'error': 'Too many active interview sessions. Please try again shortly.',
            }), 429

        questions = fetch_unique_interview_questions(limit, role, difficulty)
        if not questions:
            return jsonify({
                'success': False,
                'error': 'Unable to generate interview questions at this time.',
            }), 502

        question_count = len(questions)
        if question_count < limit:
            limit = question_count

        session_id = str(uuid.uuid4())

        user_sessions[session_id] = {
            'role': role,
            'limit': limit,
            'difficulty': difficulty,
            'questions': questions,
            'current_index': 0,
            'answers': [],
            'feedbacks': [],
            'scores': [],
            'tones': [],
            'expected_answers': [],
            'show_answer_warning': False,
            'is_submitting': False,
            'started_at': datetime.utcnow(),
        }

        return jsonify({
            'success': True,
            'session_id': session_id,
            'questions': questions,
            'current_question': questions[0] if questions else '',
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/submit_answer', methods=['POST'])
def submit_answer():
    try:
        data = request.json
        session_id = data.get('session_id')
        answer = data.get('answer', '')
        
        _cleanup_sessions()

        if session_id not in user_sessions:
            return jsonify({'success': False, 'error': 'Session not found'}), 404
        
        session_data = user_sessions[session_id]
        if _is_session_expired(session_data):
            user_sessions.pop(session_id, None)
            return jsonify({'success': False, 'error': 'Session expired'}), 404

        current_index = session_data['current_index']
        questions = session_data.get('questions') or []
        if not questions or current_index < 0 or current_index >= len(questions):
            return jsonify({'success': False, 'error': 'Interview state is invalid.'}), 400
        question = questions[current_index]
        
        # Set submitting state 
        session_data['is_submitting'] = True
        
        # Evaluate answer
        evaluation = evaluate_answer(question, answer)
        tone_analysis = analyze_tone(answer)
        
        # Update session data 
        session_data['answers'].append(answer)
        session_data['feedbacks'].append(evaluation['feedback'])
        session_data['scores'].append(evaluation['score'])
        session_data['tones'].append(tone_analysis['tone'])
        session_data['expected_answers'].append(evaluation['expected_answer'])
        session_data['show_answer_warning'] = False
        session_data['is_submitting'] = False
        
        # Move to next question or complete
        is_complete = len(session_data['answers']) >= session_data['limit']
        next_question = None
        
        if not is_complete:
            session_data['current_index'] += 1
            next_question = session_data['questions'][session_data['current_index']]
        
        response_data = {
            'success': True,
            'feedback': evaluation['feedback'],
            'score': evaluation['score'],
            'tone': tone_analysis['tone'],
            'expected_answer': evaluation['expected_answer'],
            'is_complete': is_complete,
            'next_question': next_question,
            'progress': {
                'current': len(session_data['answers']),
                'total': session_data['limit']
            }
        }
        # Persist result for logged-in users when session completes
        try:
            if is_complete and session.get('user_id'):
                user_id = session.get('user_id')
                # attempt to compute numeric average from stored scores
                nums = []
                for s in session_data.get('scores', []):
                    try:
                        nums.append(float(s))
                    except Exception:
                        try:
                            nums.append(float(str(s).strip().rstrip('%')))
                        except Exception:
                            pass
                avg = (sum(nums) / len(nums)) if nums else None
                title = f"{session_data.get('role','Interview')} ({session_data.get('difficulty','')})"
                # Prepare detailed payload to persist: questions, answers, feedbacks, scores, tones, expected answers
                details = {
                    'role': session_data.get('role'),
                    'difficulty': session_data.get('difficulty'),
                    'questions': session_data.get('questions', []),
                    'answers': session_data.get('answers', []),
                    'feedbacks': session_data.get('feedbacks', []),
                    'scores': session_data.get('scores', []),
                    'tones': session_data.get('tones', []),
                    'expected_answers': session_data.get('expected_answers', [])
                }
                try:
                    started_at = session_data.get('started_at')
                    if isinstance(started_at, (int, float)):
                        duration_seconds = max(0.0, (time.time() - started_at))
                    elif isinstance(started_at, datetime):
                        duration_seconds = max(0.0, (datetime.utcnow() - started_at).total_seconds())
                    else:
                        duration_seconds = 0.0
                    details['duration_seconds'] = round(duration_seconds, 2)
                    details['duration_minutes'] = round(duration_seconds / 60.0, 2)
                except Exception:
                    details['duration_seconds'] = 0.0
                    details['duration_minutes'] = 0.0
                try:
                    r = Result(user_id=user_id, title=title, score=avg or 0.0, kind='interview', details=json.dumps(details))
                    db.session.add(r)
                    db.session.commit()
                except Exception:
                    # If the DB schema doesn't support details or commit fails, fallback to saving minimal result
                    try:
                        r = Result(user_id=user_id, title=title, score=avg or 0.0, kind='interview')
                        db.session.add(r)
                        db.session.commit()
                    except Exception as e:
                        print(f"Failed to persist result: {e}")
        except Exception as e:
            print(f"Failed to persist result: {e}")

        if is_complete:
            user_sessions.pop(session_id, None)

        return jsonify(response_data)
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/get_question/<session_id>/<int:question_index>')
def get_question(session_id, question_index):
    _cleanup_sessions()
    payload = user_sessions.get(session_id)
    if not payload or _is_session_expired(payload):
        user_sessions.pop(session_id, None)
        return jsonify({'success': False, 'error': 'Question not found'}), 404
    questions = payload.get('questions') or []
    if 0 <= question_index < len(questions):
        return jsonify({
            'success': True,
            'question': questions[question_index]
        })
    return jsonify({'success': False, 'error': 'Question not found'}), 404

@app.route('/api/session/<session_id>')
def get_session(session_id):
    _cleanup_sessions()
    payload = user_sessions.get(session_id)
    if payload and not _is_session_expired(payload):
        return jsonify({'success': True, 'session': payload})
    user_sessions.pop(session_id, None)
    return jsonify({'success': False, 'error': 'Session not found'}), 404

@app.route('/api/end_session/<session_id>', methods=['DELETE'])
def end_session(session_id):
    _cleanup_sessions()
    if session_id in user_sessions:
        del user_sessions[session_id]
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Session not found'}), 404

# Return only real results saved in DB for the logged-in user
@app.route('/api/results')
def api_results():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = session['user_id']
    try:
        _ensure_result_details_column()
        rows = Result.query.filter_by(user_id=user_id).order_by(Result.timestamp.desc()).all()
        out = []
        for idx, r in enumerate(rows, start=1):
            # Defaults
            role = ''
            difficulty = ''
            questions = []
            duration_minutes = None
            try:
                if r.details:
                    d = json.loads(r.details)
                    role = (d.get('role') or '')
                    difficulty = (d.get('difficulty') or '')
                    questions = d.get('questions') or []
                    raw_minutes = d.get('duration_minutes')
                    raw_seconds = d.get('duration_seconds')
                    if raw_minutes is not None:
                        try:
                            duration_minutes = float(raw_minutes)
                        except (TypeError, ValueError):
                            duration_minutes = None
                    elif raw_seconds is not None:
                        try:
                            duration_minutes = float(raw_seconds) / 60.0
                        except (TypeError, ValueError):
                            duration_minutes = None
            except Exception:
                pass
            dt = r.timestamp or datetime.utcnow()
            out.append({
                'sno': idx,
                'id': r.id,
                'type': (r.kind or 'interview').capitalize(),
                'title': r.title,
                'score': r.score,
                'date': dt.strftime('%Y-%m-%d'),
                'time': dt.strftime('%I:%M %p'),
                'role': role,
                'difficulty': difficulty,
                'questions': questions,
                'duration': duration_minutes,
            })
        return jsonify({'success': True, 'results': out})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/results/<int:result_id>', methods=['DELETE'])
def delete_result(result_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = session['user_id']
    try:
        record = Result.query.filter_by(id=result_id, user_id=user_id).first()
        if not record:
            return jsonify({'success': False, 'error': 'Result not found'}), 404
        db.session.delete(record)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'error': str(e)}), 500


# Persist quiz result for logged-in users
@app.route('/api/save_quiz_result', methods=['POST'])
def save_quiz_result():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = session['user_id']
    try:
        payload = request.get_json() or {}
        role = (payload.get('role') or 'Quiz')
        difficulty = (payload.get('difficulty') or '')
        score = payload.get('score')
        total = payload.get('total') or 0
        selections = payload.get('selections') or []
        questions = payload.get('questions') or []
        duration_seconds = payload.get('duration_seconds')
        try:
            duration_seconds = float(duration_seconds)
            if duration_seconds < 0:
                duration_seconds = 0.0
        except (TypeError, ValueError):
            duration_seconds = None

        # compute percent
        try:
            pct = round((float(score) / float(total)) * 100.0) if total else 0
        except Exception:
            pct = 0

        title = f"{role} Quiz ({difficulty})".strip()
        details = {
            'role': role,
            'difficulty': difficulty,
            'score': score,
            'total': total,
            'selections': selections,
            'questions': questions,
        }
        if duration_seconds is not None:
            details['duration_seconds'] = round(duration_seconds, 2)
            details['duration_minutes'] = round(duration_seconds / 60.0, 2)
        _ensure_result_details_column()
        r = Result(user_id=user_id, title=title, score=pct, kind='quiz', details=json.dumps(details))
        db.session.add(r)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'error': str(e)}), 500


# -------- Time tracking APIs --------
@app.route('/api/time_log', methods=['POST'])
def time_log():
    """Increment today's time for the current user by `seconds` (int).

    Intended to be called periodically from the front-end while the page is active.
    """
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = session['user_id']
    try:
        payload = request.get_json() or {}
        seconds = int(payload.get('seconds') or 0)
        # clamp to a sensible range (avoid abuse)
        if seconds < 0:
            seconds = 0
        if seconds > 3600:
            seconds = 3600
        today = date.today()
        row = TimeLog.query.filter_by(user_id=user_id, day=today).first()
        if not row:
            row = TimeLog(user_id=user_id, day=today, seconds=seconds)
            db.session.add(row)
        else:
            row.seconds = int(row.seconds or 0) + seconds
            db.session.add(row)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/time_stats')
def time_stats():
    """Return per-day seconds for the last N days (default 30, max 365)."""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = session['user_id']
    try:
        days = request.args.get('days', default=30, type=int)
        if days is None or days <= 0:
            days = 30
        if days > 365:
            days = 365
        end_day = date.today()
        start_day = end_day - timedelta(days=days-1)
        # Fetch rows in range
        rows = (
            TimeLog.query
            .filter(TimeLog.user_id == user_id)
            .filter(TimeLog.day >= start_day)
            .filter(TimeLog.day <= end_day)
            .all()
        )
        by_day = {r.day: int(r.seconds or 0) for r in rows}
        labels = []
        series = []
        cur = start_day
        while cur <= end_day:
            labels.append(cur.strftime('%Y-%m-%d'))
            series.append(by_day.get(cur, 0))
            cur += timedelta(days=1)
        return jsonify({'success': True, 'labels': labels, 'series': series})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.errorhandler(404)
def handle_not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def handle_server_error(error):
    return render_template('404.html'), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)