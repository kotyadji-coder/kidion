"""
main.py — FastAPI application for kidion.
"""

import logging
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

load_dotenv()

from auth import (
    create_child_session_token,
    create_reset_token,
    create_session_token,
    decode_reset_token,
    get_current_child,
    get_current_user,
    hash_password,
    verify_password,
)
from callbacks import handle_callback, verify_callback_hmac
from db import (
    count_children_by_parent,
    complete_weekly_plan,
    create_child,
    create_generation,
    create_lesson,
    create_lesson_result,
    create_payment,
    create_shop_items,
    create_weekly_lesson,
    create_weekly_plan,
    delete_child,
    get_active_weekly_plan,
    get_child_by_id,
    get_children_by_parent,
    get_completed_topic_ids,
    get_curriculum_with_progress,
    get_equipped_items,
    get_free_lessons,
    get_generation,
    get_lesson_by_id,
    get_lesson_result_by_lesson,
    get_lessons_by_child,
    get_lessons_by_plan,
    get_payment_by_id,
    get_program_progress,
    get_recent_lesson_results,
    get_shop_items_for_child,
    get_streak_by_child,
    get_user_by_email,
    get_user_by_id,
    get_user_by_ref_code,
    get_weekly_plan,
    init_db,
    insert_transaction,
    purchase_item,
    toggle_equip_item,
    update_child,
    update_child_character_image,
    update_child_universe,
    update_crystals,
    update_difficulty_level,
    update_user_password,
    update_streak,
    update_weekly_plan_index,
    create_enrollment,
    create_curriculum_lesson,
    get_enrollment_by_id,
    get_active_enrollments,
    get_enrollment_by_subject,
    update_enrollment_progress,
    get_last_lesson_result_for_enrollment_topic,
    # New curriculum system
    add_stars,
    bulk_complete_lessons,
    get_active_skip_test,
    get_child_progress_for_subject,
    get_child_stars,
    get_curriculum_lesson_by_id,
    get_progress_stats,
    get_topic_by_id,
    get_topics_by_subject_grade,
    initialize_child_progress,
    update_lesson_progress_status,
    # Kid chat
    create_kid_chat,
    get_kid_chat,
    get_kid_chats_by_child,
    update_kid_chat_title,
    update_kid_chat_timestamp,
    delete_kid_chat,
    add_kid_chat_message,
    get_kid_chat_messages,
    count_daily_messages,
    create_chat_subscription,
    get_active_chat_subscription,
)
from payments import PACKAGES, create_yookassa_payment, handle_webhook
from referral import generate_ref_code, process_registration_referral
import services.generation
from services.universe import generate_universe, generate_character_image, generate_shop_items
from services.kid_chat import CHARACTERS as CHAT_CHARACTERS, sanitize_message, generate_chat_response, generate_chat_title


def _sanitize_interests(interests: list[str]) -> list[str]:
    """Sanitize interests input to prevent prompt injection and remove harmful content."""
    sanitized = []
    # Blocklist of patterns that could be prompt injection
    _INJECTION_PATTERNS = [
        "ignore", "забудь", "игнорируй", "system", "prompt", "instruction",
        "ты теперь", "new role", "новая роль", "override", "bypass",
        "```", "{{", "}}", "${", "\\n", "<script", "javascript:",
    ]
    for interest in interests:
        if not interest or not isinstance(interest, str):
            continue
        # Trim and limit length
        clean = interest.strip()[:100]
        # Remove any non-text characters (keep letters, digits, spaces, basic punctuation)
        clean = re.sub(r'[^\w\s\-.,!?а-яёА-ЯЁ]', '', clean)
        if not clean:
            continue
        # Check for injection patterns
        lower = clean.lower()
        if any(p in lower for p in _INJECTION_PATTERNS):
            continue
        sanitized.append(clean)
    return sanitized[:20]  # Max 20 interests


def get_db_path() -> str:
    return os.environ.get("DATABASE_PATH", "./kidion.db")


def get_db_connection() -> sqlite3.Connection:
    """Return a SQLite connection for the current DATABASE_PATH."""
    from db import get_connection
    return get_connection(get_db_path())


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(get_db_path())
    if not os.environ.get("CALLBACK_HMAC_SECRET", ""):
        logging.warning("CALLBACK_HMAC_SECRET is not set or empty")
    from services.curricula import load_curricula
    load_curricula(get_db_path())
    yield


app = FastAPI(lifespan=lifespan)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES_DIR = os.path.join(_BASE_DIR, "templates")
_STATIC_DIR = os.path.join(_BASE_DIR, "static")
_CONTENT_DIR = os.path.join(_BASE_DIR, "content")

# Set of strong references to background tasks (prevents garbage collection)
_background_tasks: set = set()

# Create content directory
os.makedirs(_CONTENT_DIR, exist_ok=True)

# Mount static files
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

if os.path.isdir(_CONTENT_DIR):
    app.mount("/content", StaticFiles(directory=_CONTENT_DIR), name="content")

templates = Jinja2Templates(directory=_TEMPLATES_DIR) if os.path.isdir(_TEMPLATES_DIR) else None

# kid_templates uses the parent templates dir so extends/includes work correctly
kid_templates = templates  # templates/kid/ lives under templates/


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "").lower() in ("1", "true", "yes")


def _set_session_cookie(response: Response, user_id: int) -> None:
    token = create_session_token(user_id)
    response.set_cookie(
        "kid_session",
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        secure=_COOKIE_SECURE,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie("kid_session", httponly=True, samesite="lax")


# ---------------------------------------------------------------------------
# Pydantic models for children
# ---------------------------------------------------------------------------

class ChildCreateRequest(BaseModel):
    name: str
    gender: str
    birth_date: str = ""
    grade: int
    universe: str = ""
    interests: list[str] = []
    pin_code: str
    # Universe questionnaire (step 2)
    favorite_heroes: str = ""
    favorite_animals: str = ""
    favorite_activities: str = ""
    dream_world: str = ""
    favorite_subject_theme: str = ""

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v):
        if v not in ("boy", "girl"):
            raise ValueError("gender must be 'boy' or 'girl'")
        return v

    @field_validator("grade")
    @classmethod
    def validate_grade(cls, v):
        if not (1 <= v <= 11):
            raise ValueError("grade must be between 1 and 11")
        return v

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, v):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("birth_date must be YYYY-MM-DD")
        return v

    @field_validator("pin_code")
    @classmethod
    def validate_pin(cls, v):
        if not re.fullmatch(r"\d{4}", v):
            raise ValueError("pin_code must be exactly 4 digits")
        return v


class ChildUpdateRequest(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    grade: Optional[int] = None
    universe: Optional[str] = None
    pin_code: Optional[str] = None

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v):
        if v is not None and v not in ("boy", "girl"):
            raise ValueError("gender must be 'boy' or 'girl'")
        return v

    @field_validator("grade")
    @classmethod
    def validate_grade(cls, v):
        if v is not None and not (1 <= v <= 11):
            raise ValueError("grade must be between 1 and 11")
        return v

    @field_validator("pin_code")
    @classmethod
    def validate_pin(cls, v):
        if v is not None and not re.fullmatch(r"\d{4}", v):
            raise ValueError("pin_code must be exactly 4 digits")
        return v


class KidAuthRequest(BaseModel):
    child_id: int
    pin: str


class GenerateLessonRequest(BaseModel):
    child_id: int
    topic: str
    subject: Optional[str] = "general"

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v):
        if not v or not v.strip():
            raise ValueError("topic must not be empty")
        return v.strip()


class LessonResultRequest(BaseModel):
    correct_answers: int
    total_answers: int = 5

    @field_validator("correct_answers")
    @classmethod
    def validate_correct(cls, v):
        if not (0 <= v <= 5):
            raise ValueError("correct_answers must be 0-5")
        return v


class EnrollSubjectRequest(BaseModel):
    subject: str
    grade: int


class SkipTestRequest(BaseModel):
    topic_id: int


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"ok": True}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/auth/register")
async def register(request: Request):
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    ref_code_input = body.get("ref_code", None)

    # Validate email
    if not _EMAIL_RE.match(email):
        return JSONResponse({"error": "invalid_email"}, status_code=400)

    # Validate password length (min 8 chars)
    if len(password) < 8:
        return JSONResponse({"error": "weak_password"}, status_code=400)

    conn = get_db_connection()

    # Check duplicate email
    if get_user_by_email(conn, email):
        return JSONResponse({"error": "email_taken"}, status_code=400)

    # Determine crystals and referral
    referred_by = None
    referrer = get_user_by_ref_code(conn, ref_code_input) if ref_code_input else None
    crystals = 120 if referrer else 60
    if referrer:
        referred_by = referrer["id"]
    referrer_found = referrer is not None

    # Generate unique ref_code for new user
    new_ref_code = generate_ref_code()
    for _ in range(10):
        if not get_user_by_ref_code(conn, new_ref_code):
            break
        new_ref_code = generate_ref_code()

    pw_hash = hash_password(password)
    user_id = create_user_and_log(conn, email, pw_hash, crystals, new_ref_code, referred_by)

    # Create referral record if applicable
    if referrer_found and ref_code_input:
        process_registration_referral(conn, user_id, ref_code_input)

    response = JSONResponse({"ok": True})
    _set_session_cookie(response, user_id)
    return response


def create_user_and_log(conn, email, pw_hash, crystals, ref_code, referred_by):
    """Create user and log the initial crystal transaction."""
    from db import create_user
    user_id = create_user(conn, email, pw_hash, crystals, ref_code, referred_by)
    insert_transaction(conn, user_id, crystals, "registration_bonus")
    return user_id


@app.post("/auth/login")
async def login(request: Request):
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")

    conn = get_db_connection()
    user = get_user_by_email(conn, email)
    if not user or not verify_password(password, user["password_hash"]):
        return JSONResponse({"error": "invalid_credentials"}, status_code=401)

    response = JSONResponse({"ok": True})
    _set_session_cookie(response, user["id"])
    return response


@app.post("/auth/logout")
async def logout():
    response = JSONResponse({"ok": True})
    _clear_session_cookie(response)
    return response


@app.post("/auth/forgot-password")
async def forgot_password(request: Request):
    body = await request.json()
    email = body.get("email", "").strip().lower()

    if not _EMAIL_RE.match(email):
        return JSONResponse({"error": "invalid_email"}, status_code=400)

    conn = get_db_connection()
    user = get_user_by_email(conn, email)

    # Always return ok to prevent email enumeration
    if not user:
        return JSONResponse({"ok": True})

    token = create_reset_token(user["id"])
    base_url = os.environ.get("APP_BASE_URL", "http://localhost:8003")
    reset_link = f"{base_url}/reset-password?token={token}"

    # Send email if SMTP is configured, otherwise log the link
    _send_reset_email(email, reset_link)

    return JSONResponse({"ok": True})


def _send_reset_email(to_email: str, reset_link: str) -> None:
    """Send password reset email via SMTP. Falls back to logging if SMTP is not configured."""
    import smtplib
    from email.mime.text import MIMEText

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    if not all([smtp_host, smtp_user, smtp_password]):
        logging.warning("SMTP not configured. Reset link: %s", reset_link)
        return

    html = (
        "<div style='font-family:sans-serif;max-width:480px;margin:0 auto;'>"
        "<h2 style='color:#6c5ce7;'>Kidion</h2>"
        "<p>Вы запросили сброс пароля.</p>"
        f"<p><a href='{reset_link}' style='display:inline-block;padding:12px 24px;"
        "background:#6c5ce7;color:#fff;border-radius:8px;text-decoration:none;'>"
        "Сбросить пароль</a></p>"
        "<p style='color:#999;font-size:13px;'>Ссылка действительна 1 час. "
        "Если вы не запрашивали сброс — просто проигнорируйте это письмо.</p>"
        "</div>"
    )

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = "Сброс пароля — Kidion"
    msg["From"] = smtp_from
    msg["To"] = to_email

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        logging.info("Reset email sent to %s", to_email)
    except Exception:
        logging.exception("Failed to send reset email to %s", to_email)


@app.post("/auth/reset-password")
async def reset_password(request: Request):
    body = await request.json()
    token = body.get("token", "")
    password = body.get("password", "")

    if len(password) < 8:
        return JSONResponse({"error": "weak_password"}, status_code=400)

    user_id = decode_reset_token(token)
    if user_id is None:
        return JSONResponse({"error": "invalid_token"}, status_code=400)

    conn = get_db_connection()
    user = get_user_by_id(conn, user_id)
    if not user:
        return JSONResponse({"error": "invalid_token"}, status_code=400)

    update_user_password(conn, user_id, hash_password(password))

    response = JSONResponse({"ok": True})
    _set_session_cookie(response, user_id)
    return response


@app.get("/auth/me")
async def me(request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return JSONResponse({
        "id": user["id"],
        "email": user["email"],
        "crystals": user["crystals"],
        "ref_code": user["ref_code"],
    })


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

@app.post("/api/generate")
async def generate(request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    gen_type = body.get("type", "tale")

    # Check crystals (need at least 20)
    if user["crystals"] < 20:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)

    # Create generation record (do NOT deduct crystals yet — deduction happens on callback)
    gen_id = create_generation(conn, user["id"], gen_type)

    return JSONResponse({"gen_id": gen_id})


# ---------------------------------------------------------------------------
# Poll
# ---------------------------------------------------------------------------

@app.get("/api/poll/{gen_id}")
async def poll(gen_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    generation = get_generation(conn, gen_id)
    if generation is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    if generation["user_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    # Refresh user data for crystals
    fresh_user = get_user_by_id(conn, user["id"])

    return JSONResponse({
        "status": generation["status"],
        "result_url": generation["result_url"],
        "crystals": fresh_user["crystals"] if fresh_user else user["crystals"],
    })


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------

@app.post("/api/callback/{gen_id}")
async def callback(gen_id: int, secret: str, request: Request):
    hmac_secret = os.environ.get("CALLBACK_HMAC_SECRET", "")
    if not verify_callback_hmac(gen_id, secret, hmac_secret):
        return JSONResponse({"error": "invalid_signature"}, status_code=403)

    body = await request.json()
    conn = get_db_connection()
    handle_callback(conn, gen_id, body)

    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

@app.post("/api/payment/create")
async def payment_create(request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    package_id = body.get("package_id", "")

    if package_id not in PACKAGES:
        return JSONResponse({"error": "unknown_package"}, status_code=400)

    base_url = os.environ.get("APP_BASE_URL", "http://localhost:8000")
    return_url = f"{base_url}/payment/success"

    try:
        result = create_yookassa_payment(user["id"], package_id, return_url)
    except Exception:
        logging.exception("YooKassa payment creation failed")
        return JSONResponse({"error": "payment_provider_error"}, status_code=502)

    payment_id = create_payment(
        conn,
        user["id"],
        result["yk_payment_id"],
        result["amount_rub"],
        result["crystals"],
    )

    return JSONResponse({
        "payment_id": payment_id,
        "confirmation_url": result["confirmation_url"],
    })


@app.post("/api/payment/webhook")
async def payment_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        logging.warning("Webhook body is not valid JSON")
        return JSONResponse({"ok": True})

    conn = get_db_connection()
    try:
        handle_webhook(conn, body)
    except Exception:
        logging.exception("Webhook processing error")
        return JSONResponse({"ok": True})

    return JSONResponse({"ok": True})


@app.get("/api/payment/status/{payment_id}")
async def payment_status(payment_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    payment = get_payment_by_id(conn, payment_id)
    if payment is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    fresh_user = get_user_by_id(conn, user["id"])

    return JSONResponse({
        "status": payment["status"],
        "crystals": fresh_user["crystals"] if fresh_user else user["crystals"],
    })


# ---------------------------------------------------------------------------
# Children API
# ---------------------------------------------------------------------------

@app.post("/api/children")
async def create_child_endpoint(body: ChildCreateRequest, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    if count_children_by_parent(conn, user["id"]) >= 3:
        return JSONResponse({"error": "max_children_reached"}, status_code=400)

    # Build interests from universe questionnaire fields
    interests = body.interests if body.interests else []
    if not interests:
        for field_val in [body.favorite_heroes, body.favorite_animals, body.favorite_activities, body.dream_world, body.favorite_subject_theme]:
            if field_val and field_val.strip():
                interests.extend([s.strip() for s in field_val.split(",") if s.strip()])
    interests = _sanitize_interests(interests)
    universe_text = body.universe or ", ".join(interests) or "приключения"

    pin_hash = hash_password(body.pin_code)
    child = create_child(
        conn,
        parent_id=user["id"],
        name=body.name,
        gender=body.gender,
        birth_date=body.birth_date,
        grade=body.grade,
        universe=universe_text,
        pin_hash=pin_hash,
    )

    # Generate universe, character, and shop items in background
    import asyncio
    task = asyncio.create_task(_setup_child_universe(child["id"], body.name, body.gender, body.grade, interests))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return JSONResponse(child, status_code=201)


async def _setup_child_universe(child_id: int, name: str, gender: str, grade: int, interests: list[str]):
    """Background task: generate universe, character image, and shop items for a new child."""
    import asyncio
    import json as _json

    try:
        conn = get_db_connection()

        # Step 1: Generate universe description and character prompt
        universe_data = await asyncio.to_thread(generate_universe, name, gender, grade, interests)

        update_child_universe(
            conn,
            child_id,
            interests=_json.dumps(interests, ensure_ascii=False),
            universe_description=universe_data.get("universe_description", ""),
            character_prompt=universe_data.get("character_prompt", ""),
        )

        # Step 2: Generate character image
        character_prompt = universe_data.get("character_prompt", "")
        if character_prompt:
            image_bytes = await asyncio.to_thread(generate_character_image, character_prompt)
            if image_bytes:
                os.makedirs(os.path.join(_CONTENT_DIR, "characters"), exist_ok=True)
                img_path = f"characters/{child_id}.png"
                with open(os.path.join(_CONTENT_DIR, img_path), "wb") as f:
                    f.write(image_bytes)
                update_child_character_image(conn, child_id, f"/content/{img_path}")

        # Step 3: Generate and save shop items
        char_name = universe_data.get("character_name", "Проводник")
        universe_desc = universe_data.get("universe_description", "")
        items = await asyncio.to_thread(generate_shop_items, universe_desc, char_name)
        if items:
            create_shop_items(conn, child_id, items)

        logging.info(f"Universe setup complete for child {child_id}")
    except Exception:
        logging.exception(f"Failed to setup universe for child {child_id}")


@app.get("/api/children")
async def list_children(request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    children = get_children_by_parent(conn, user["id"])
    # Enrich with streak data for dashboard
    for child in children:
        streak = get_streak_by_child(conn, child["id"])
        child["current_streak"] = streak["current_streak"] if streak else 0
    return JSONResponse(children)


@app.get("/api/children/{child_id}")
async def get_child_endpoint(child_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    child.pop("pin_hash", None)

    streak = get_streak_by_child(conn, child_id)
    if streak:
        child["current_streak"] = streak["current_streak"]
        child["longest_streak"] = streak["longest_streak"]
        child["last_activity_date"] = streak["last_activity_date"]
    else:
        child["current_streak"] = 0
        child["longest_streak"] = 0
        child["last_activity_date"] = None

    return JSONResponse(child)


@app.put("/api/children/{child_id}")
async def update_child_endpoint(child_id: int, body: ChildUpdateRequest, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    update_dict = {}
    if body.name is not None:
        update_dict["name"] = body.name
    if body.gender is not None:
        update_dict["gender"] = body.gender
    if body.birth_date is not None:
        update_dict["birth_date"] = body.birth_date
    if body.grade is not None:
        update_dict["grade"] = body.grade
    if body.universe is not None:
        update_dict["universe"] = body.universe
    if body.pin_code is not None:
        update_dict["pin_hash"] = hash_password(body.pin_code)

    updated = update_child(conn, child_id, **update_dict)
    return JSONResponse(updated)


@app.delete("/api/children/{child_id}")
async def delete_child_endpoint(child_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    # Delete character image file if exists
    char_img_path = os.path.join(_CONTENT_DIR, "characters", f"{child_id}.png")
    if os.path.exists(char_img_path):
        os.remove(char_img_path)

    delete_child(conn, child_id)
    return JSONResponse({"ok": True})


class RecreateUniverseRequest(BaseModel):
    favorite_heroes: str = ""
    favorite_animals: str = ""
    favorite_activities: str = ""
    dream_world: str = ""
    favorite_subject_theme: str = ""


@app.post("/api/children/{child_id}/recreate-universe")
async def recreate_universe_endpoint(child_id: int, body: RecreateUniverseRequest, request: Request):
    """Reset universe: delete shop items & purchased items, regenerate universe/character/shop."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    # Build new interests from questionnaire
    interests = []
    for field_val in [body.favorite_heroes, body.favorite_animals, body.favorite_activities, body.dream_world, body.favorite_subject_theme]:
        if field_val and field_val.strip():
            interests.extend([s.strip() for s in field_val.split(",") if s.strip()])
    interests = _sanitize_interests(interests)

    # Save new interests to child record
    import json as _json
    conn.execute("UPDATE children SET interests=?, updated_at=? WHERE id=?",
                 (_json.dumps(interests, ensure_ascii=False), _now(), child_id))

    # Delete shop items and purchased items (stars are NOT refunded)
    conn.execute("DELETE FROM child_items WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM shop_items WHERE child_id = ?", (child_id,))
    conn.commit()

    # Delete old character image
    old_img = os.path.join(_CONTENT_DIR, "characters", f"{child_id}.png")
    if os.path.exists(old_img):
        os.remove(old_img)

    # Regenerate universe in background
    import asyncio
    task = asyncio.create_task(_setup_child_universe(child_id, child["name"], child["gender"], child["grade"], interests))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return JSONResponse({"ok": True, "message": "Universe regeneration started"})


@app.post("/api/kid/auth")
async def kid_auth(body: KidAuthRequest, request: Request):
    conn = get_db_connection()
    child = get_child_by_id(conn, body.child_id)
    if child is None or not verify_password(body.pin, child["pin_hash"]):
        return JSONResponse({"error": "invalid_credentials"}, status_code=401)

    token = create_child_session_token(child["id"])
    response = JSONResponse({"ok": True, "child_id": child["id"], "name": child["name"]})
    response.set_cookie(
        "kid_session_child",
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        secure=_COOKIE_SECURE,
    )
    return response


# ---------------------------------------------------------------------------
# Lesson Generation API
# ---------------------------------------------------------------------------

@app.post("/api/lessons/generate")
async def generate_lesson(body: GenerateLessonRequest, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, body.child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    if user["crystals"] < 20:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)

    # Deduct crystals
    ok = update_crystals(conn, user["id"], -20)
    if not ok:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)
    insert_transaction(conn, user["id"], -20, f"lesson_generation:child_{body.child_id}")

    # Create lesson record
    subject = body.subject or "general"
    lesson_id = create_lesson(conn, body.child_id, "on_demand", body.topic, subject)

    # Launch background generation
    server_url = os.environ.get("APP_BASE_URL", "http://localhost:8003")
    db_path = get_db_path()

    import threading
    thread = threading.Thread(
        target=services.generation.generate_lesson_content,
        args=(lesson_id, dict(child), body.topic, subject, db_path, server_url)
    )
    thread.start()

    return JSONResponse({"lesson_id": lesson_id})


@app.get("/api/lessons/{lesson_id}/poll")
async def poll_lesson(lesson_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    lesson = get_lesson_by_id(conn, lesson_id)
    if lesson is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    child = get_child_by_id(conn, lesson["child_id"])
    if child is None or child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    return JSONResponse({
        "status": lesson["status"],
        "content_url": lesson["content_url"],
        "print_url": lesson["print_url"],
        "worksheet_url": lesson.get("worksheet_url"),
    })


@app.post("/api/lessons/{lesson_id}/result")
async def submit_lesson_result(lesson_id: int, body: LessonResultRequest, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    child_session = get_current_child(request, conn)

    if not user and not child_session:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    lesson = get_lesson_by_id(conn, lesson_id)
    if lesson is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    child = get_child_by_id(conn, lesson["child_id"])
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    # Authorization check
    if user and child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if child_session and child_session["id"] != lesson["child_id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    # Compute stars
    if body.correct_answers == 5:
        stars = 3
    elif body.correct_answers >= 3:
        stars = 2
    else:
        stars = 1

    # Save result
    create_lesson_result(conn, lesson_id, lesson["child_id"],
                         body.correct_answers, body.total_answers, stars)

    # === Award stars to child ===
    stars_to_award = body.correct_answers
    if stars_to_award > 0:
        add_stars(conn, lesson["child_id"], stars_to_award)

    # === Update child_lesson_progress if this is a curriculum lesson ===
    progress_row = conn.execute(
        "SELECT * FROM child_lesson_progress WHERE lesson_id = ?",
        (lesson_id,)
    ).fetchone()
    if progress_row:
        progress = dict(progress_row)
        if lesson["mode"] == "skip_test":
            _handle_skip_test_result(conn, progress, lesson, body.correct_answers, stars_to_award)
        else:
            _handle_curriculum_lesson_complete(conn, progress, stars_to_award)

    # Update streak
    from datetime import date
    today_str = date.today().isoformat()
    streak = update_streak(conn, lesson["child_id"], today_str)

    # Update difficulty_level
    recent = get_recent_lesson_results(conn, lesson["child_id"], limit=2)
    if len(recent) == 2:
        if all(r["correct_answers"] == 5 for r in recent):
            new_level = min(3, child["difficulty_level"] + 1)
            update_difficulty_level(conn, lesson["child_id"], new_level)
        elif all(r["correct_answers"] <= 2 for r in recent):
            new_level = max(1, child["difficulty_level"] - 1)
            update_difficulty_level(conn, lesson["child_id"], new_level)

    # Re-fetch updated difficulty
    updated_child = get_child_by_id(conn, lesson["child_id"])

    # Auto-advance enrollment if lesson is part of a curriculum
    next_action = None
    if lesson.get("enrollment_id"):
        enrollment = get_enrollment_by_id(conn, lesson["enrollment_id"])
        if enrollment and enrollment["status"] == "active":
            next_action = _apply_advance(conn, enrollment, body.correct_answers)

    response_data = {
        "ok": True,
        "stars": stars,
        "difficulty_level": updated_child["difficulty_level"],
        "current_streak": streak["current_streak"],
    }
    if next_action is not None:
        response_data["next_action"] = next_action

    return JSONResponse(response_data)


# ---------------------------------------------------------------------------
# Weekly Plans API
# ---------------------------------------------------------------------------

class WeeklyPlanCreateRequest(BaseModel):
    child_id: int
    subject: str
    query: str
    lessons_count: Optional[int] = 5

    @field_validator("lessons_count")
    @classmethod
    def validate_lessons_count(cls, v):
        if v is not None and not (1 <= v <= 10):
            raise ValueError("lessons_count must be 1-10")
        return v

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v):
        if v not in ("math", "russian", "english"):
            raise ValueError("subject must be 'math', 'russian' or 'english'")
        return v


@app.post("/api/weekly-plans")
async def create_weekly_plan_endpoint(body: WeeklyPlanCreateRequest, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, body.child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    from services.curricula import search_unit, get_curriculum, load_curricula
    load_curricula(get_db_path())
    unit = search_unit(conn, body.subject, child["grade"], body.query)
    if unit is None:
        return JSONResponse({"error": "unit_not_found"}, status_code=404)

    curriculum = get_curriculum(conn, body.subject, child["grade"])
    curriculum_id = curriculum["id"]

    topics = unit.get("topics", [])
    lessons_count = min(body.lessons_count or 5, len(topics))
    selected_topics = topics[:lessons_count]
    topic_ids = [t["id"] for t in selected_topics]

    plan_id = create_weekly_plan(
        conn,
        child_id=body.child_id,
        curriculum_id=curriculum_id,
        unit_id=unit["id"],
        topic_ids=topic_ids,
        lessons_count=lessons_count,
    )

    return JSONResponse({
        "plan_id": plan_id,
        "unit_title": unit["title"],
        "topics": [{"id": t["id"], "title": t["title"]} for t in selected_topics],
    }, status_code=201)


@app.get("/api/weekly-plans/active/{child_id}")
async def get_active_plan(child_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    plan = get_active_weekly_plan(conn, child_id)
    if plan is None:
        return JSONResponse({"plan": None})

    return JSONResponse({"plan": {
        "id": plan["id"],
        "unit_id": plan["unit_id"],
        "lessons_count": plan["lessons_count"],
        "current_lesson_index": plan["current_lesson_index"],
        "status": plan["status"],
    }})


@app.get("/api/weekly-plans/{plan_id}")
async def get_weekly_plan_endpoint(plan_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    plan = get_weekly_plan(conn, plan_id)
    if plan is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    child = get_child_by_id(conn, plan["child_id"])
    if child is None or child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    # Get curriculum data to resolve topic titles
    import json as _json
    row = conn.execute(
        "SELECT * FROM curriculum_templates WHERE id=?", (plan["curriculum_id"],)
    ).fetchone()
    curriculum_data = _json.loads(row["topics_json"]) if row else {"units": []}

    # Find the unit
    unit = next((u for u in curriculum_data.get("units", []) if u["id"] == plan["unit_id"]), None)
    unit_title = unit["title"] if unit else ""

    # Build topics list from topic_ids_json
    topic_ids = _json.loads(plan["topic_ids_json"])
    all_topics = {t["id"]: t for u in curriculum_data.get("units", []) for t in u.get("topics", [])}
    topics = [{"id": tid, "title": all_topics.get(tid, {}).get("title", "")} for tid in topic_ids]

    # Get lessons for plan
    lessons = get_lessons_by_plan(conn, plan_id)

    return JSONResponse({
        "id": plan["id"],
        "unit_id": plan["unit_id"],
        "unit_title": unit_title,
        "topics": topics,
        "current_lesson_index": plan["current_lesson_index"],
        "status": plan["status"],
        "lessons": lessons,
    })


@app.post("/api/weekly-plans/{plan_id}/next")
async def weekly_plan_next(plan_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    plan = get_weekly_plan(conn, plan_id)
    if plan is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    child = get_child_by_id(conn, plan["child_id"])
    if child is None or child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    if plan["status"] != "active":
        return JSONResponse({"error": "plan_not_active"}, status_code=409)

    if plan["current_lesson_index"] >= plan["lessons_count"]:
        complete_weekly_plan(conn, plan_id)
        return JSONResponse({"error": "plan_completed"}, status_code=200)

    import json as _json
    topic_ids = _json.loads(plan["topic_ids_json"])
    idx = plan["current_lesson_index"]
    topic_id = topic_ids[idx]

    # Look up topic title from curriculum
    row = conn.execute(
        "SELECT topics_json FROM curriculum_templates WHERE id=?", (plan["curriculum_id"],)
    ).fetchone()
    curriculum_data = _json.loads(row["topics_json"]) if row else {"units": []}
    all_topics = {t["id"]: t for u in curriculum_data.get("units", []) for t in u.get("topics", [])}
    topic = all_topics.get(topic_id, {})
    topic_title = topic.get("title", topic_id)

    # Get subject from curriculum
    subject = curriculum_data.get("subject", "general")

    # Create lesson
    lesson_id = create_weekly_lesson(
        conn,
        child_id=plan["child_id"],
        topic_id=topic_id,
        topic_title=topic_title,
        subject=subject,
        plan_id=plan_id,
        sequence_number=idx,
    )

    # Update plan index
    update_weekly_plan_index(conn, plan_id, idx + 1)

    # Launch background generation
    server_url = os.environ.get("APP_BASE_URL", "http://localhost:8003")
    db_path = get_db_path()

    import threading
    thread = threading.Thread(
        target=services.generation.generate_lesson_content,
        args=(lesson_id, dict(child), topic_title, subject, db_path, server_url)
    )
    thread.start()

    return JSONResponse({"lesson_id": lesson_id})


@app.post("/api/weekly-plans/{plan_id}/generate-all")
async def weekly_plan_generate_all(plan_id: int, request: Request):
    """Generate ALL remaining lessons in the weekly plan at once. Costs 50 crystals."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    plan = get_weekly_plan(conn, plan_id)
    if plan is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    child = get_child_by_id(conn, plan["child_id"])
    if child is None or child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    if plan["status"] != "active":
        return JSONResponse({"error": "plan_not_active"}, status_code=409)

    remaining = plan["lessons_count"] - plan["current_lesson_index"]
    if remaining <= 0:
        complete_weekly_plan(conn, plan_id)
        return JSONResponse({"error": "plan_completed"})

    # Cost: 50 crystals for the whole plan
    PLAN_COST = 50
    if user["crystals"] < PLAN_COST:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)

    ok = update_crystals(conn, user["id"], -PLAN_COST)
    if not ok:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)
    insert_transaction(conn, user["id"], -PLAN_COST, f"weekly_plan:{plan_id}")

    import json as _json
    topic_ids = _json.loads(plan["topic_ids_json"])

    # Get curriculum data
    row = conn.execute(
        "SELECT topics_json FROM curriculum_templates WHERE id=?", (plan["curriculum_id"],)
    ).fetchone()
    curriculum_data = _json.loads(row["topics_json"]) if row else {"units": []}
    all_topics = {t["id"]: t for u in curriculum_data.get("units", []) for t in u.get("topics", [])}
    subject = curriculum_data.get("subject", "general")

    server_url = os.environ.get("APP_BASE_URL", "http://localhost:8003")
    db_path = get_db_path()
    lesson_ids = []

    for idx in range(plan["current_lesson_index"], plan["lessons_count"]):
        topic_id = topic_ids[idx]
        topic = all_topics.get(topic_id, {})
        topic_title = topic.get("title", topic_id)

        lesson_id = create_weekly_lesson(
            conn,
            child_id=plan["child_id"],
            topic_id=topic_id,
            topic_title=topic_title,
            subject=subject,
            plan_id=plan_id,
            sequence_number=idx,
        )
        lesson_ids.append(lesson_id)

        # Launch generation in background thread
        import threading
        thread = threading.Thread(
            target=services.generation.generate_lesson_content,
            args=(lesson_id, dict(child), topic_title, subject, db_path, server_url)
        )
        thread.start()

    # Mark plan index as fully generated
    update_weekly_plan_index(conn, plan_id, plan["lessons_count"])

    return JSONResponse({
        "ok": True,
        "lessons_count": len(lesson_ids),
        "lesson_ids": lesson_ids,
        "crystals_spent": PLAN_COST,
    })


# ---------------------------------------------------------------------------
# Enrollment helpers
# ---------------------------------------------------------------------------

def _get_flat_topics(conn, curriculum_id: int) -> list[dict]:
    """Return flat list of all topics from a curriculum template."""
    import json as _json
    row = conn.execute("SELECT topics_json FROM curriculum_templates WHERE id=?", (curriculum_id,)).fetchone()
    if not row:
        return []
    data = _json.loads(row["topics_json"])
    return [t for u in data.get("units", []) for t in u.get("topics", [])]


def _compute_advance(correct_answers: int, retry_count: int) -> tuple:
    """Returns (action, new_retry_count). action = 'next_topic' | 'retry'"""
    if correct_answers >= 3:
        return "next_topic", 0
    elif retry_count < 2:
        return "retry", retry_count + 1
    else:
        return "next_topic", 0


def _apply_advance(conn, enrollment: dict, correct_answers: int) -> str:
    """Apply advance logic, update DB, return next_action string."""
    action, new_retry = _compute_advance(correct_answers, enrollment["retry_count"])
    new_idx = enrollment["current_topic_index"]
    if action == "next_topic":
        new_idx += 1
    flat_topics = _get_flat_topics(conn, enrollment["curriculum_id"])
    total = len(flat_topics)
    if new_idx >= total:
        new_status = "completed"
        next_action = "completed"
    else:
        new_status = "active"
        next_action = action
    update_enrollment_progress(conn, enrollment["id"], new_idx, new_retry, new_status)
    return next_action


# ---------------------------------------------------------------------------
# Enrollment Pydantic models
# ---------------------------------------------------------------------------

class EnrollmentCreateRequest(BaseModel):
    child_id: int
    subject: str
    start_topic_index: int = 0

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v):
        if v not in ("math", "russian", "english"):
            raise ValueError("subject must be 'math', 'russian' or 'english'")
        return v

    @field_validator("start_topic_index")
    @classmethod
    def validate_start_index(cls, v):
        if v < 0:
            raise ValueError("start_topic_index must be >= 0")
        return v


# ---------------------------------------------------------------------------
# Enrollment API Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/enrollments")
async def create_enrollment_endpoint(body: EnrollmentCreateRequest, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, body.child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    # Check for duplicate active enrollment
    existing = get_enrollment_by_subject(conn, body.child_id, body.subject)
    if existing:
        return JSONResponse({"error": "enrollment_already_active"}, status_code=409)

    # Find curriculum by subject + child grade
    from services.curricula import get_curriculum, load_curricula
    load_curricula(get_db_path())
    curriculum = get_curriculum(conn, body.subject, child["grade"])
    if curriculum is None:
        return JSONResponse({"error": "curriculum_not_found"}, status_code=404)

    flat_topics = _get_flat_topics(conn, curriculum["id"])
    total_topics = len(flat_topics)

    start_idx = min(body.start_topic_index, total_topics)
    enrollment_id = create_enrollment(conn, body.child_id, curriculum["id"], start_idx)

    return JSONResponse({
        "enrollment_id": enrollment_id,
        "curriculum_title": curriculum["data"]["title"],
        "total_topics": total_topics,
        "current_topic_index": start_idx,
    }, status_code=201)


@app.get("/api/enrollments/active/{child_id}")
async def get_active_enrollments_endpoint(child_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    enrollments = get_active_enrollments(conn, child_id)
    result = []
    for e in enrollments:
        row = conn.execute("SELECT * FROM curriculum_templates WHERE id=?", (e["curriculum_id"],)).fetchone()
        ct = dict(row) if row else {}
        flat = _get_flat_topics(conn, e["curriculum_id"])
        result.append({
            "enrollment_id": e["id"],
            "subject": ct.get("subject", ""),
            "curriculum_title": ct.get("title", ""),
            "total_topics": len(flat),
            "current_topic_index": e["current_topic_index"],
            "status": e["status"],
        })
    return JSONResponse(result)


@app.get("/api/enrollments/{enrollment_id}")
async def get_enrollment_endpoint(enrollment_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    enrollment = get_enrollment_by_id(conn, enrollment_id)
    if enrollment is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    child = get_child_by_id(conn, enrollment["child_id"])
    if child is None or child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    import json as _json
    row = conn.execute("SELECT * FROM curriculum_templates WHERE id=?", (enrollment["curriculum_id"],)).fetchone()
    ct = dict(row) if row else {}

    flat_topics = _get_flat_topics(conn, enrollment["curriculum_id"])
    total = len(flat_topics)
    idx = enrollment["current_topic_index"]

    current_topic = flat_topics[idx] if idx < total else None

    # Build completed_topics with stars from lesson_results
    completed = []
    for i in range(min(idx, total)):
        t = flat_topics[i]
        result = get_last_lesson_result_for_enrollment_topic(conn, enrollment_id, i)
        completed.append({
            "id": t["id"],
            "title": t["title"],
            "stars": result["stars"] if result else None,
        })

    return JSONResponse({
        "id": enrollment["id"],
        "curriculum_title": ct.get("title", ""),
        "subject": ct.get("subject", ""),
        "grade": ct.get("grade", 0),
        "total_topics": total,
        "current_topic_index": idx,
        "status": enrollment["status"],
        "current_topic": {"id": current_topic["id"], "title": current_topic["title"]} if current_topic else None,
        "completed_topics": completed,
    })


@app.post("/api/enrollments/{enrollment_id}/next")
async def enrollment_next(enrollment_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    enrollment = get_enrollment_by_id(conn, enrollment_id)
    if enrollment is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    child = get_child_by_id(conn, enrollment["child_id"])
    if child is None or child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    if enrollment["status"] != "active":
        return JSONResponse({"error": "enrollment_completed"}, status_code=409)

    flat_topics = _get_flat_topics(conn, enrollment["curriculum_id"])
    total = len(flat_topics)
    idx = enrollment["current_topic_index"]

    if idx >= total:
        return JSONResponse({"error": "enrollment_completed"})

    topic = flat_topics[idx]

    row = conn.execute("SELECT subject FROM curriculum_templates WHERE id=?", (enrollment["curriculum_id"],)).fetchone()
    subject = row["subject"] if row else "general"

    lesson_id = create_curriculum_lesson(
        conn,
        child_id=enrollment["child_id"],
        topic_id=topic["id"],
        topic_title=topic["title"],
        subject=subject,
        enrollment_id=enrollment_id,
        sequence_number=idx,
    )

    server_url = os.environ.get("APP_BASE_URL", "http://localhost:8003")
    db_path = get_db_path()

    import threading
    thread = threading.Thread(
        target=services.generation.generate_lesson_content,
        args=(lesson_id, dict(child), topic["title"], subject, db_path, server_url)
    )
    thread.start()

    return JSONResponse({"lesson_id": lesson_id, "topic_title": topic["title"]})


@app.post("/api/enrollments/{enrollment_id}/advance")
async def enrollment_advance(enrollment_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    child_session = get_current_child(request, conn)

    if not user and not child_session:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    enrollment = get_enrollment_by_id(conn, enrollment_id)
    if enrollment is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    child = get_child_by_id(conn, enrollment["child_id"])
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    if user and child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if child_session and child_session["id"] != enrollment["child_id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    # Get last result for current topic
    result = get_last_lesson_result_for_enrollment_topic(
        conn, enrollment_id, enrollment["current_topic_index"]
    )
    correct_answers = result["correct_answers"] if result else 0

    next_action = _apply_advance(conn, enrollment, correct_answers)
    updated = get_enrollment_by_id(conn, enrollment_id)

    return JSONResponse({
        "next_action": next_action,
        "current_topic_index": updated["current_topic_index"],
        "retry_count": updated["retry_count"],
    })


@app.delete("/api/enrollments/{enrollment_id}")
async def delete_enrollment(enrollment_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    enrollment = get_enrollment_by_id(conn, enrollment_id)
    if enrollment is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    child = get_child_by_id(conn, enrollment["child_id"])
    if child is None or child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    update_enrollment_progress(
        conn, enrollment_id,
        enrollment["current_topic_index"],
        enrollment["retry_count"],
        "paused"
    )
    return JSONResponse({"ok": True})

# ---------------------------------------------------------------------------
# Curriculum progression helpers
# ---------------------------------------------------------------------------

def _handle_curriculum_lesson_complete(conn, progress: dict, stars_earned: int) -> None:
    """Mark lesson completed and unlock next lesson in sequence."""
    update_lesson_progress_status(
        conn, progress["id"], "completed",
        lesson_id=progress["lesson_id"],
        stars_earned=stars_earned,
    )

    cl = conn.execute(
        "SELECT cl.*, ct.theme_order, ct.subject, ct.grade FROM curriculum_lessons cl "
        "JOIN curriculum_topics ct ON ct.id = cl.topic_id "
        "WHERE cl.id = ?", (progress["curriculum_lesson_id"],)
    ).fetchone()
    if cl is None:
        return

    if cl["lesson_order"] < 5:
        next_cl = conn.execute(
            "SELECT id FROM curriculum_lessons WHERE topic_id = ? AND lesson_order = ?",
            (cl["topic_id"], cl["lesson_order"] + 1)
        ).fetchone()
        if next_cl:
            conn.execute(
                "UPDATE child_lesson_progress SET status = 'available' "
                "WHERE child_id = ? AND curriculum_lesson_id = ? AND status = 'locked'",
                (progress["child_id"], next_cl["id"])
            )
            conn.commit()
    else:
        next_topic = conn.execute(
            "SELECT id FROM curriculum_topics "
            "WHERE subject = ? AND grade = ? AND theme_order = ?",
            (cl["subject"], cl["grade"], cl["theme_order"] + 1)
        ).fetchone()
        if next_topic:
            first_lesson = conn.execute(
                "SELECT id FROM curriculum_lessons WHERE topic_id = ? AND lesson_order = 1",
                (next_topic["id"],)
            ).fetchone()
            if first_lesson:
                conn.execute(
                    "UPDATE child_lesson_progress SET status = 'available' "
                    "WHERE child_id = ? AND curriculum_lesson_id = ? AND status = 'locked'",
                    (progress["child_id"], first_lesson["id"])
                )
                conn.commit()


def _handle_skip_test_result(conn, progress: dict, lesson: dict,
                              correct_answers: int, stars_earned: int) -> None:
    """Handle skip test completion. If 4+/5: bulk unlock up to tested topic."""
    update_lesson_progress_status(
        conn, progress["id"], "completed",
        lesson_id=progress["lesson_id"],
        stars_earned=stars_earned,
    )

    if correct_answers >= 4:
        cl = conn.execute(
            "SELECT cl.*, ct.theme_order, ct.subject, ct.grade FROM curriculum_lessons cl "
            "JOIN curriculum_topics ct ON ct.id = cl.topic_id "
            "WHERE cl.id = ?", (progress["curriculum_lesson_id"],)
        ).fetchone()
        if cl:
            bulk_complete_lessons(
                conn, progress["child_id"],
                cl["subject"], cl["grade"], cl["theme_order"]
            )


# ---------------------------------------------------------------------------
# New Curriculum API Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/children/{child_id}/enroll-subject")
async def enroll_subject(child_id: int, body: EnrollSubjectRequest, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    topics = get_topics_by_subject_grade(conn, body.subject, body.grade)
    if not topics:
        return JSONResponse({"error": "no_curriculum_for_subject_grade"}, status_code=400)

    rows_created = initialize_child_progress(conn, child_id, body.subject, body.grade)
    total = conn.execute(
        """SELECT COUNT(*) FROM child_lesson_progress clp
           JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE clp.child_id=? AND ct.subject=? AND ct.grade=?""",
        (child_id, body.subject, body.grade),
    ).fetchone()[0]

    message = "enrolled" if rows_created > 0 else "already_enrolled"

    # Auto-generate first 4 lessons of the first topic on first enrollment (FREE)
    auto_lesson_ids = []
    if rows_created > 0:
        first_topic = topics[0] if topics else None
        if first_topic:
            first_topic_id = first_topic["id"]
            # Get first 4 lessons of the first topic (exclude the 5th = test/activity)
            first_lessons = conn.execute(
                """SELECT clp.id AS progress_id, cl.id AS curriculum_lesson_id, cl.lesson_order, cl.title_ru
                   FROM child_lesson_progress clp
                   JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
                   WHERE clp.child_id=? AND cl.topic_id=? AND clp.lesson_id IS NULL
                   ORDER BY cl.lesson_order LIMIT 4""",
                (child_id, first_topic_id),
            ).fetchall()

            server_url = os.environ.get("APP_BASE_URL", "http://localhost:8003")
            db_path = get_db_path()

            for fl in first_lessons:
                try:
                    lesson_id = create_lesson(
                        conn, child_id, "curriculum", fl["title_ru"],
                        body.subject, plan_id=None,
                    )
                    conn.execute(
                        "UPDATE child_lesson_progress SET status='available', lesson_id=? WHERE id=?",
                        (lesson_id, fl["progress_id"]),
                    )
                    conn.commit()
                    auto_lesson_ids.append(lesson_id)

                    import threading
                    thread = threading.Thread(
                        target=services.generation.generate_lesson_content,
                        args=(lesson_id, dict(child), fl["title_ru"], body.subject, db_path, server_url),
                        kwargs={"lesson_number": fl["lesson_order"]},
                    )
                    thread.start()
                except Exception:
                    pass

    return JSONResponse({
        "ok": True,
        "subject": body.subject,
        "grade": body.grade,
        "total_lessons": total,
        "message": message,
        "auto_lesson_ids": auto_lesson_ids,
    })


@app.get("/api/children/{child_id}/subject-progress/{subject}")
async def get_subject_progress(child_id: int, subject: str, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    grade = child["grade"]
    progress_rows = get_child_progress_for_subject(conn, child_id, subject, grade)
    if not progress_rows:
        return JSONResponse({"error": "not_enrolled"}, status_code=404)

    stats = get_progress_stats(conn, child_id, subject, grade)

    # Group by topic
    topics_map = {}
    for row in progress_rows:
        tid = row["topic_id"]
        if tid not in topics_map:
            topics_map[tid] = {
                "id": tid,
                "title_ru": row["topic_title"],
                "theme_order": row["theme_order"],
                "icon": row["icon"],
                "lessons": [],
            }
        topics_map[tid]["lessons"].append({
            "curriculum_lesson_id": row["curriculum_lesson_id"],
            "title_ru": row["title_ru"],
            "lesson_order": row["lesson_order"],
            "status": row["status"],
            "stars_earned": row["stars_earned"],
            "lesson_id": row["lesson_id"],
            "lesson_status": row.get("lesson_status"),
        })

    topics = sorted(topics_map.values(), key=lambda t: t["theme_order"])

    return JSONResponse({
        "subject": subject,
        "grade": grade,
        "total_lessons": stats["total_lessons"],
        "completed_lessons": stats["completed_lessons"],
        "total_stars": stats["total_stars"],
        "topics": topics,
    })


@app.get("/api/children/{child_id}/enrolled-subjects")
async def get_enrolled_subjects(child_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    subjects = _get_enrolled_subjects_for_child(conn, child_id)
    return JSONResponse({"subjects": subjects})


def _get_enrolled_subjects_for_child(conn, child_id: int) -> list[dict]:
    """Find all subjects where child has progress rows, aggregate stats."""
    rows = conn.execute(
        """SELECT DISTINCT ct.subject, ct.grade
           FROM child_lesson_progress clp
           JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE clp.child_id = ?""",
        (child_id,),
    ).fetchall()

    subjects = []
    for row in rows:
        stats = get_progress_stats(conn, child_id, row["subject"], row["grade"])
        total = stats["total_lessons"]
        completed = stats["completed_lessons"]
        percent = round(completed / total * 100) if total > 0 else 0
        subjects.append({
            "subject": row["subject"],
            "grade": row["grade"],
            "total_lessons": total,
            "completed_lessons": completed,
            "total_stars": stats["total_stars"],
            "percent": percent,
        })
    return subjects


@app.post("/api/children/{child_id}/skip-test")
async def assign_skip_test(child_id: int, body: SkipTestRequest, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    topic = get_topic_by_id(conn, body.topic_id)
    if topic is None:
        return JSONResponse({"error": "topic_not_found"}, status_code=404)

    # Check child has progress in this subject
    progress_rows = get_child_progress_for_subject(
        conn, child_id, topic["subject"], topic["grade"]
    )
    if not progress_rows:
        return JSONResponse({"error": "not_enrolled"}, status_code=400)

    # Check at least one lesson in this topic is locked
    topic_lessons = conn.execute(
        """SELECT clp.* FROM child_lesson_progress clp
           JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
           WHERE clp.child_id=? AND cl.topic_id=? AND clp.status='locked'""",
        (child_id, body.topic_id),
    ).fetchall()
    if not topic_lessons:
        return JSONResponse({"error": "topic_already_completed"}, status_code=400)

    # Check no active skip test
    active_test = get_active_skip_test(conn, child_id)
    if active_test:
        return JSONResponse({"error": "active_skip_test_exists"}, status_code=409)

    # Skip test is FREE — no crystal deduction

    # Create lesson with mode='skip_test'
    lesson_id = create_lesson(
        conn, child_id, "skip_test", topic["title_ru"], topic["subject"]
    )

    # Find a locked lesson in this topic and set to 'test'
    first_locked = topic_lessons[0]
    conn.execute(
        "UPDATE child_lesson_progress SET status='test', lesson_id=? WHERE id=?",
        (lesson_id, first_locked["id"]),
    )
    conn.commit()

    # Launch background generation
    server_url = os.environ.get("APP_BASE_URL", "http://localhost:8003")
    db_path = get_db_path()

    import threading
    thread = threading.Thread(
        target=services.generation.generate_lesson_content,
        args=(lesson_id, dict(child), topic["title_ru"], topic["subject"], db_path, server_url)
    )
    thread.start()

    return JSONResponse({"ok": True, "lesson_id": lesson_id, "status": "generating"})


# ---------------------------------------------------------------------------
# Bulk Generation API Endpoints
# ---------------------------------------------------------------------------

class BulkGenerateTopicRequest(BaseModel):
    topic_id: int


@app.post("/api/children/{child_id}/generate-topic")
async def generate_topic_lessons(child_id: int, body: BulkGenerateTopicRequest, request: Request):
    """Generate all 5 lessons in a topic. Cost: 50 crystals."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    topic = get_topic_by_id(conn, body.topic_id)
    if topic is None:
        return JSONResponse({"error": "topic_not_found"}, status_code=404)

    # Initialize progress if not done
    initialize_child_progress(conn, child_id, topic["subject"], topic["grade"])

    # Get lessons in this topic that are still locked/available (not completed)
    from db import get_lessons_by_topic_id
    curriculum_lessons = get_lessons_by_topic_id(conn, body.topic_id)
    pending = []
    for cl in curriculum_lessons:
        progress = conn.execute(
            "SELECT * FROM child_lesson_progress WHERE child_id=? AND curriculum_lesson_id=?",
            (child_id, cl["id"]),
        ).fetchone()
        if progress and progress["status"] in ("locked", "available") and not progress["lesson_id"]:
            pending.append((cl, dict(progress)))

    if not pending:
        return JSONResponse({"error": "all_lessons_already_generated"}, status_code=400)

    cost = len(pending) * 20  # 20 per lesson
    if user["crystals"] < cost:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)

    ok = update_crystals(conn, user["id"], -cost)
    if not ok:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)
    insert_transaction(conn, user["id"], -cost, f"bulk_topic:{body.topic_id}:child_{child_id}")

    server_url = os.environ.get("APP_BASE_URL", "http://localhost:8003")
    db_path = get_db_path()
    lesson_ids = []

    for cl, progress in pending:
        lesson_id = create_lesson(conn, child_id, "curriculum", cl["title_ru"], topic["subject"])
        lesson_ids.append(lesson_id)

        # Update progress: set status to available and link lesson
        conn.execute(
            "UPDATE child_lesson_progress SET status='available', lesson_id=? WHERE id=?",
            (lesson_id, progress["id"]),
        )
        conn.commit()

        import threading
        thread = threading.Thread(
            target=services.generation.generate_lesson_content,
            args=(lesson_id, dict(child), cl["title_ru"], topic["subject"], db_path, server_url),
            kwargs={"lesson_number": cl["lesson_order"]},
        )
        thread.start()

    return JSONResponse({
        "ok": True,
        "lesson_ids": lesson_ids,
        "crystals_spent": cost,
    })


class BulkGenerateMonthRequest(BaseModel):
    subject: str


@app.post("/api/children/{child_id}/generate-month")
async def generate_month_lessons(child_id: int, body: BulkGenerateMonthRequest, request: Request):
    """Generate next 20 lessons (4 topics) in a subject. Cost: 200 crystals."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    grade = child["grade"]
    initialize_child_progress(conn, child_id, body.subject, grade)

    # Find next 20 ungenerated lessons
    progress_rows = get_child_progress_for_subject(conn, child_id, body.subject, grade)
    pending = []
    for row in progress_rows:
        if row["status"] in ("locked", "available") and not row["lesson_id"]:
            pending.append(row)
        if len(pending) >= 20:
            break

    if not pending:
        return JSONResponse({"error": "no_lessons_to_generate"}, status_code=400)

    cost = len(pending) * 20  # 20 per lesson
    if user["crystals"] < cost:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)

    ok = update_crystals(conn, user["id"], -cost)
    if not ok:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)
    insert_transaction(conn, user["id"], -cost, f"bulk_month:{body.subject}:child_{child_id}")

    server_url = os.environ.get("APP_BASE_URL", "http://localhost:8003")
    db_path = get_db_path()
    lesson_ids = []

    for row in pending:
        cl = get_curriculum_lesson_by_id(conn, row["curriculum_lesson_id"])
        topic = get_topic_by_id(conn, cl["topic_id"])

        lesson_id = create_lesson(conn, child_id, "curriculum", cl["title_ru"], topic["subject"])
        lesson_ids.append(lesson_id)

        conn.execute(
            "UPDATE child_lesson_progress SET status='available', lesson_id=? WHERE id=?",
            (lesson_id, row["id"]),
        )
        conn.commit()

        import threading
        thread = threading.Thread(
            target=services.generation.generate_lesson_content,
            args=(lesson_id, dict(child), cl["title_ru"], topic["subject"], db_path, server_url),
            kwargs={"lesson_number": cl["lesson_order"]},
        )
        thread.start()

    return JSONResponse({
        "ok": True,
        "lesson_ids": lesson_ids,
        "lessons_count": len(lesson_ids),
        "crystals_spent": cost,
    })


# ---------------------------------------------------------------------------
# Batch Print Worksheets
# ---------------------------------------------------------------------------

@app.get("/api/children/{child_id}/worksheets")
async def batch_print_worksheets(child_id: int, request: Request,
                                  topic_id: int | None = None,
                                  subject: str | None = None):
    """Return combined HTML with all worksheets for a topic or subject (month).

    Query params:
      - topic_id: print worksheets for specific topic (5 lessons)
      - subject: print all worksheets for subject (up to 20 lessons)
    """
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None or child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    worksheets = []

    if topic_id:
        # Get all lessons for this topic via child_lesson_progress
        rows = conn.execute(
            """
            SELECT clp.lesson_id, cl.lesson_order, cl.title_ru
            FROM child_lesson_progress clp
            JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
            WHERE clp.child_id = ? AND cl.topic_id = ? AND clp.lesson_id IS NOT NULL
            ORDER BY cl.lesson_order
            """,
            (child_id, topic_id),
        ).fetchall()

        for row in rows:
            lesson = get_lesson_by_id(conn, row["lesson_id"])
            if lesson and lesson.get("worksheet_url"):
                worksheets.append({
                    "lesson_number": row["lesson_order"],
                    "worksheet_url": lesson["worksheet_url"],
                    "topic_title": row["title_ru"],
                })

    elif subject:
        # Get all lessons for subject, ordered by topic then lesson_order
        rows = conn.execute(
            """
            SELECT clp.lesson_id, cl.lesson_order, cl.title_ru, ct.theme_order
            FROM child_lesson_progress clp
            JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
            JOIN curriculum_topics ct ON ct.id = cl.topic_id
            WHERE clp.child_id = ? AND ct.subject = ? AND clp.lesson_id IS NOT NULL
            ORDER BY ct.theme_order, cl.lesson_order
            """,
            (child_id, subject),
        ).fetchall()

        lesson_counter = 0
        for row in rows:
            lesson = get_lesson_by_id(conn, row["lesson_id"])
            if lesson and lesson.get("worksheet_url"):
                lesson_counter += 1
                worksheets.append({
                    "lesson_number": lesson_counter,
                    "worksheet_url": lesson["worksheet_url"],
                    "topic_title": row["title_ru"],
                })
    else:
        return JSONResponse({"error": "Specify topic_id or subject"}, status_code=400)

    if not worksheets:
        return JSONResponse({"error": "no_worksheets"}, status_code=404)

    from services.worksheet.generator import generate_batch_print_html
    html = generate_batch_print_html(worksheets)
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Kid Curriculum API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/kid/subjects")
async def kid_subjects(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    subjects = _get_enrolled_subjects_for_child(conn, child["id"])
    return JSONResponse({"subjects": subjects})


@app.get("/api/kid/subject/{subject}/map")
async def kid_subject_map(subject: str, request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    grade = child["grade"]
    progress_rows = get_child_progress_for_subject(conn, child["id"], subject, grade)
    if not progress_rows:
        return JSONResponse({"error": "not_enrolled"}, status_code=404)

    stats = get_progress_stats(conn, child["id"], subject, grade)

    topics_map = {}
    for row in progress_rows:
        tid = row["topic_id"]
        if tid not in topics_map:
            topics_map[tid] = {
                "id": tid,
                "title_ru": row["topic_title"],
                "theme_order": row["theme_order"],
                "icon": row["icon"],
                "lessons": [],
            }
        topics_map[tid]["lessons"].append({
            "curriculum_lesson_id": row["curriculum_lesson_id"],
            "title_ru": row["title_ru"],
            "lesson_order": row["lesson_order"],
            "status": row["status"],
            "stars_earned": row["stars_earned"],
            "lesson_id": row["lesson_id"],
        })

    topics = sorted(topics_map.values(), key=lambda t: t["theme_order"])

    return JSONResponse({
        "subject": subject,
        "grade": grade,
        "total_lessons": stats["total_lessons"],
        "completed_lessons": stats["completed_lessons"],
        "total_stars": stats["total_stars"],
        "topics": topics,
    })


@app.post("/api/kid/lessons/{curriculum_lesson_id}/start")
async def kid_start_lesson(curriculum_lesson_id: int, request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    # Get progress row
    progress_row = conn.execute(
        "SELECT * FROM child_lesson_progress WHERE child_id=? AND curriculum_lesson_id=?",
        (child["id"], curriculum_lesson_id),
    ).fetchone()
    if progress_row is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    progress = dict(progress_row)

    if progress["status"] != "available":
        return JSONResponse({"error": "lesson_not_available"}, status_code=400)

    # Already generated?
    if progress["lesson_id"]:
        lesson = get_lesson_by_id(conn, progress["lesson_id"])
        if lesson:
            return JSONResponse({
                "ok": True,
                "lesson_id": lesson["id"],
                "status": lesson["status"],
            })

    # Check parent crystals
    parent = get_user_by_id(conn, child["parent_id"])
    if not parent or parent["crystals"] < 20:
        return JSONResponse(
            {"error": "insufficient_crystals", "message": "Попроси родителей добавить кристаллы!"},
            status_code=402,
        )

    ok = update_crystals(conn, parent["id"], -20)
    if not ok:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)
    insert_transaction(conn, parent["id"], -20, f"kid_lesson:child_{child['id']}")

    # Get curriculum lesson details
    cl = get_curriculum_lesson_by_id(conn, curriculum_lesson_id)
    topic = get_topic_by_id(conn, cl["topic_id"])

    lesson_id = create_lesson(
        conn, child["id"], "curriculum", cl["title_ru"], topic["subject"]
    )

    # Link progress to lesson
    conn.execute(
        "UPDATE child_lesson_progress SET lesson_id=? WHERE id=?",
        (lesson_id, progress["id"]),
    )
    conn.commit()

    # Launch background generation
    server_url = os.environ.get("APP_BASE_URL", "http://localhost:8003")
    db_path = get_db_path()

    import threading
    thread = threading.Thread(
        target=services.generation.generate_lesson_content,
        args=(lesson_id, dict(child), cl["title_ru"], topic["subject"], db_path, server_url),
        kwargs={"lesson_number": cl["lesson_order"]},
    )
    thread.start()

    return JSONResponse({"ok": True, "lesson_id": lesson_id, "status": "generating"})


# ---------------------------------------------------------------------------
# Program Progress & Free Lessons API
# ---------------------------------------------------------------------------


@app.get("/api/children/{child_id}/program-progress")
async def get_child_program_progress(child_id: int, request: Request):
    """Per-subject progress for the child's grade curriculum."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    progress = get_program_progress(conn, child_id, child["grade"])

    # Include active weekly plan and enrollments info
    plan = get_active_weekly_plan(conn, child_id)
    active_plan = None
    if plan:
        import json as _json
        ct_row = conn.execute(
            "SELECT * FROM curriculum_templates WHERE id=?", (plan["curriculum_id"],)
        ).fetchone()
        unit_title = ""
        if ct_row:
            try:
                topics_data = _json.loads(ct_row["topics_json"])
                for unit in topics_data.get("units", []):
                    if unit.get("id") == plan["unit_id"]:
                        unit_title = unit.get("title", "")
                        break
            except Exception:
                pass
        active_plan = {
            "id": plan["id"],
            "unit_title": unit_title,
            "current_lesson_index": plan["current_lesson_index"],
            "lessons_count": plan["lessons_count"],
            "subject": ct_row["subject"] if ct_row else "",
        }

    enrollments = get_active_enrollments(conn, child_id)
    active_enrollments = []
    for e in enrollments:
        ct_row = conn.execute(
            "SELECT * FROM curriculum_templates WHERE id=?", (e["curriculum_id"],)
        ).fetchone()
        ct = dict(ct_row) if ct_row else {}
        flat = _get_flat_topics(conn, e["curriculum_id"])
        active_enrollments.append({
            "id": e["id"],
            "subject": ct.get("subject", ""),
            "current_topic_index": e["current_topic_index"],
            "total_topics": len(flat),
        })

    return JSONResponse({
        "subjects": progress,
        "active_weekly_plan": active_plan,
        "active_enrollments": active_enrollments,
    })


@app.get("/api/children/{child_id}/curriculum/{subject}")
async def get_child_curriculum(child_id: int, subject: str, request: Request):
    """Full curriculum with topic completion status."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    if subject not in ("math", "russian", "english"):
        return JSONResponse({"error": "invalid_subject"}, status_code=400)

    result = get_curriculum_with_progress(conn, child_id, subject, child["grade"])
    if result is None:
        return JSONResponse({"error": "curriculum_not_found"}, status_code=404)

    # Include active enrollment for this subject
    enrollment = get_enrollment_by_subject(conn, child_id, subject)
    if enrollment:
        result["active_enrollment"] = {
            "id": enrollment["id"],
            "current_topic_index": enrollment["current_topic_index"],
            "retry_count": enrollment["retry_count"],
            "status": enrollment["status"],
        }
    else:
        result["active_enrollment"] = None

    # Include active weekly plan for this subject
    plan = get_active_weekly_plan(conn, child_id)
    if plan:
        ct_row = conn.execute(
            "SELECT subject FROM curriculum_templates WHERE id=?", (plan["curriculum_id"],)
        ).fetchone()
        if ct_row and ct_row["subject"] == subject:
            result["active_weekly_plan"] = {
                "id": plan["id"],
                "unit_id": plan["unit_id"],
                "current_lesson_index": plan["current_lesson_index"],
                "lessons_count": plan["lessons_count"],
            }
        else:
            result["active_weekly_plan"] = None
    else:
        result["active_weekly_plan"] = None

    return JSONResponse(result)


class GenerateTopicRequest(BaseModel):
    child_id: int
    topic_id: str
    subject: str

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v):
        if v not in ("math", "russian", "english"):
            raise ValueError("subject must be 'math', 'russian' or 'english'")
        return v


@app.post("/api/lessons/generate-topic")
async def generate_topic_lesson(body: GenerateTopicRequest, request: Request):
    """Generate a lesson for a specific curriculum topic (pick-a-topic mode)."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, body.child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    if user["crystals"] < 20:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)

    # Find topic title from curriculum
    from services.curricula import get_curriculum, load_curricula
    load_curricula(get_db_path())
    curriculum = get_curriculum(conn, body.subject, child["grade"])
    if curriculum is None:
        return JSONResponse({"error": "curriculum_not_found"}, status_code=404)

    import json as _json
    all_topics = {
        t["id"]: t
        for u in curriculum["data"].get("units", [])
        for t in u.get("topics", [])
    }
    topic = all_topics.get(body.topic_id)
    if topic is None:
        return JSONResponse({"error": "topic_not_found"}, status_code=404)

    # Deduct crystals
    ok = update_crystals(conn, user["id"], -20)
    if not ok:
        return JSONResponse({"error": "insufficient_crystals"}, status_code=402)
    insert_transaction(conn, user["id"], -20, f"topic_lesson:child_{body.child_id}")

    # Create lesson with mode='curriculum' but no enrollment_id
    lesson_id = create_curriculum_lesson(
        conn,
        child_id=body.child_id,
        topic_id=body.topic_id,
        topic_title=topic["title"],
        subject=body.subject,
        enrollment_id=None,
        sequence_number=0,
    )

    # Launch background generation
    server_url = os.environ.get("APP_BASE_URL", "http://localhost:8003")
    db_path = get_db_path()

    import threading
    thread = threading.Thread(
        target=services.generation.generate_lesson_content,
        args=(lesson_id, dict(child), topic["title"], body.subject, db_path, server_url)
    )
    thread.start()

    return JSONResponse({"lesson_id": lesson_id, "topic_title": topic["title"]})


@app.get("/api/children/{child_id}/free-lessons")
async def get_child_free_lessons(child_id: int, request: Request):
    """Return all free (on_demand) lessons for a child."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    lessons = get_free_lessons(conn, child_id)
    return JSONResponse({"lessons": lessons})


# ---------------------------------------------------------------------------
# HTML page routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def page_index(request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    if templates is None:
        return HTMLResponse("<h1>Kidion</h1>")
    return templates.TemplateResponse(request, "index.html", {"user": None})


@app.get("/login", response_class=HTMLResponse)
async def page_login(request: Request):
    if templates is None:
        return HTMLResponse("<h1>Login</h1>")
    return templates.TemplateResponse(
        request, "auth.html", {"user": None, "mode": "login", "error": None}
    )


@app.get("/register", response_class=HTMLResponse)
async def page_register(request: Request, ref: str = ""):
    if templates is None:
        return HTMLResponse("<h1>Register</h1>")
    return templates.TemplateResponse(
        request,
        "auth.html",
        {"user": None, "mode": "register", "error": None, "ref_code": ref},
    )


@app.get("/forgot-password", response_class=HTMLResponse)
async def page_forgot_password(request: Request):
    if templates is None:
        return HTMLResponse("<h1>Forgot Password</h1>")
    return templates.TemplateResponse(
        request, "auth.html", {"user": None, "mode": "forgot", "error": None}
    )


@app.get("/reset-password", response_class=HTMLResponse)
async def page_reset_password(request: Request, token: str = ""):
    if templates is None:
        return HTMLResponse("<h1>Reset Password</h1>")
    return templates.TemplateResponse(
        request, "auth.html",
        {"user": None, "mode": "reset", "error": None, "reset_token": token},
    )


@app.get("/terms", response_class=HTMLResponse)
async def page_terms(request: Request):
    if templates is None:
        return HTMLResponse("<h1>Terms</h1>")
    return templates.TemplateResponse(
        request, "legal.html",
        {"user": None, "title": "Условия использования", "page": "terms"},
    )


@app.get("/privacy", response_class=HTMLResponse)
async def page_privacy(request: Request):
    if templates is None:
        return HTMLResponse("<h1>Privacy</h1>")
    return templates.TemplateResponse(
        request, "legal.html",
        {"user": None, "title": "Политика конфиденциальности", "page": "privacy"},
    )


@app.get("/chat", response_class=HTMLResponse)
async def page_chat(request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if templates is None:
        return HTMLResponse("<h1>Chat</h1>")
    return templates.TemplateResponse(request, "chat.html", {"user": user})


@app.get("/profile", response_class=HTMLResponse)
async def page_profile(request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if templates is None:
        return HTMLResponse("<h1>Profile</h1>")
    return templates.TemplateResponse(request, "profile.html", {"user": user})


@app.get("/buy", response_class=HTMLResponse)
async def page_buy(request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if templates is None:
        return HTMLResponse("<h1>Buy</h1>")
    return templates.TemplateResponse(request, "buy.html", {"user": user})


# ---------------------------------------------------------------------------
# Kid API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/kid/me")
async def kid_me(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    streak = get_streak_by_child(conn, child["id"])
    current_streak = streak["current_streak"] if streak else 0
    longest_streak = streak["longest_streak"] if streak else 0

    return JSONResponse({
        "id": child["id"],
        "name": child["name"],
        "grade": child["grade"],
        "universe": child["universe"],
        "difficulty_level": child["difficulty_level"],
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "stars": child.get("stars", 0),
        "character_image_url": child.get("character_image_url"),
        "universe_description": child.get("universe_description", ""),
        "character_name": child.get("character_name", ""),
        "character_onboarded": bool(child.get("character_onboarded", 0)),
    })


@app.get("/api/kid/lessons")
async def kid_lessons(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    all_lessons = get_lessons_by_child(conn, child["id"])

    # Build all lessons list with lock state
    # completed = has result (stars not None)
    # active = first lesson without result (and status=done, has content)
    # locked = no result, but a previous lesson is still not completed
    current = None
    lessons_list = []
    found_active = False

    for lesson in all_lessons:
        entry = {
            "id": lesson["id"],
            "topic_title": lesson["topic_title"],
            "subject": lesson["subject"],
            "status": lesson["status"],
            "content_url": lesson["content_url"],
            "stars": lesson["stars"],
            "mode": lesson.get("mode"),
            "plan_id": lesson.get("plan_id"),
            "sequence_number": lesson.get("sequence_number"),
        }

        if lesson["stars"] is not None:
            entry["state"] = "completed"
        elif not found_active:
            entry["state"] = "active"
            found_active = True
            current = entry
        else:
            entry["state"] = "locked"

        lessons_list.append(entry)

    # history = completed lessons
    history = [l for l in lessons_list if l["state"] == "completed"]

    return JSONResponse({"current": current, "lessons": lessons_list, "history": history})


@app.get("/api/kid/lessons/{lesson_id}")
async def kid_lesson_detail(lesson_id: int, request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    lesson = get_lesson_by_id(conn, lesson_id)
    if lesson is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if lesson["child_id"] != child["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    result = get_lesson_result_by_lesson(conn, lesson_id)

    return JSONResponse({
        "id": lesson["id"],
        "topic_title": lesson["topic_title"],
        "subject": lesson["subject"],
        "status": lesson["status"],
        "content_url": lesson["content_url"],
        "print_url": lesson["print_url"],
        "worksheet_url": lesson.get("worksheet_url"),
        "stars": result["stars"] if result else None,
    })


@app.get("/api/kid/free-lessons")
async def kid_free_lessons_api(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    rows = conn.execute(
        """
        SELECT l.id, l.topic_title, l.subject, l.status, l.content_url,
               lr.stars, lr.correct_answers
        FROM lessons l
        LEFT JOIN lesson_results lr ON lr.lesson_id = l.id
        WHERE l.child_id = ? AND l.mode = 'on_demand'
        ORDER BY l.created_at DESC
        """,
        (child["id"],),
    ).fetchall()

    lessons = []
    for r in rows:
        lessons.append({
            "id": r["id"],
            "topic_title": r["topic_title"],
            "subject": r["subject"],
            "status": r["status"],
            "content_url": r["content_url"],
            "stars": r["stars"],
            "correct_answers": r["correct_answers"],
        })

    return JSONResponse({"lessons": lessons, "total": len(lessons)})


@app.get("/api/kid/character")
async def kid_character_api(request: Request):
    """Get character info, equipped items, and shop items for the kid."""
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    import json as _json

    equipped = get_equipped_items(conn, child["id"])
    shop_items = get_shop_items_for_child(conn, child["id"])

    # Group shop items by category
    categories = {}
    for item in shop_items:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "id": item["id"],
            "title_ru": item["title_ru"],
            "description_ru": item["description_ru"],
            "emoji": item["emoji"],
            "price_stars": item["price_stars"],
            "purchased": item["purchase_id"] is not None,
            "equipped": bool(item["equipped"]) if item["purchase_id"] else False,
        })

    interests_raw = child.get("interests", "[]")
    try:
        interests = _json.loads(interests_raw) if interests_raw else []
    except (ValueError, TypeError):
        interests = []

    return JSONResponse({
        "character_image_url": child.get("character_image_url"),
        "character_name": child.get("character_name", ""),
        "universe_description": child.get("universe_description", ""),
        "interests": interests,
        "stars": child.get("stars", 0),
        "equipped_items": [
            {"id": e["id"], "title_ru": e["title_ru"], "emoji": e["emoji"], "category": e["category"]}
            for e in equipped
        ],
        "shop": categories,
    })


@app.post("/api/kid/character/name")
async def kid_set_character_name(request: Request):
    """Set or update the character name."""
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    name = str(body.get("name", "")).strip()
    if not name:
        name = "Искатель"
    if len(name) > 30:
        name = name[:30]

    from db import update_child_character_name
    update_child_character_name(conn, child["id"], name)

    return JSONResponse({"ok": True, "character_name": name})


@app.post("/api/kid/shop/buy/{item_id}")
async def kid_buy_item(item_id: int, request: Request):
    """Purchase a shop item with stars."""
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    success = purchase_item(conn, child["id"], item_id)
    if not success:
        return JSONResponse({"error": "purchase_failed", "message": "Not enough stars or already purchased"}, status_code=400)

    # Regenerate character image with new equipment in background
    import asyncio
    task = asyncio.create_task(_regenerate_character(child["id"]))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    fresh_child = get_child_by_id(conn, child["id"])
    return JSONResponse({
        "ok": True,
        "stars": fresh_child.get("stars", 0) if fresh_child else 0,
    })


@app.post("/api/kid/shop/equip/{item_id}")
async def kid_equip_item(item_id: int, request: Request):
    """Toggle equip/unequip an item."""
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    equipped = body.get("equipped", True)

    success = toggle_equip_item(conn, child["id"], item_id, equipped)
    if not success:
        return JSONResponse({"error": "item_not_found"}, status_code=404)

    # Regenerate character image in background
    import asyncio
    task = asyncio.create_task(_regenerate_character(child["id"]))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return JSONResponse({"ok": True})


async def _regenerate_character(child_id: int):
    """Regenerate character image with current equipped items."""
    import asyncio
    try:
        conn = get_db_connection()
        child = get_child_by_id(conn, child_id)
        if not child or not child.get("character_prompt"):
            return

        equipped = get_equipped_items(conn, child_id)
        image_bytes = await asyncio.to_thread(
            generate_character_image, child["character_prompt"], equipped
        )
        if image_bytes:
            os.makedirs(os.path.join(_CONTENT_DIR, "characters"), exist_ok=True)
            img_path = f"characters/{child_id}.png"
            with open(os.path.join(_CONTENT_DIR, img_path), "wb") as f:
                f.write(image_bytes)
            update_child_character_image(conn, child_id, f"/content/{img_path}")
    except Exception:
        logging.exception(f"Failed to regenerate character for child {child_id}")


@app.post("/api/kid/logout")
async def kid_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("kid_session_child", httponly=True, samesite="lax")
    return response


@app.post("/api/report")
async def report_content(request: Request):
    """Report inappropriate content. Works for both parent and child sessions."""
    conn = get_db_connection()
    body = await request.json()
    lesson_id = body.get("lesson_id")
    reason = body.get("reason", "inappropriate_content")[:200]

    # Try child auth first, then parent
    child = get_current_child(request, conn)
    user = get_current_user(request, conn) if not child else None

    if not child and not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    conn.execute(
        "INSERT INTO content_reports (lesson_id, child_id, user_id, reason) VALUES (?, ?, ?, ?)",
        (lesson_id, child["id"] if child else None, user["id"] if user else None, reason),
    )
    conn.commit()
    logging.info("Content report filed: lesson_id=%s, reason=%s", lesson_id, reason)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Kid HTML page routes
# ---------------------------------------------------------------------------

@app.get("/kid", response_class=HTMLResponse)
async def kid_root(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if child:
        return RedirectResponse(url="/kid/home", status_code=302)
    return RedirectResponse(url="/kid/login", status_code=302)


@app.get("/kid/login", response_class=HTMLResponse)
async def kid_login_page(request: Request, child_id: Optional[int] = None):
    if templates is None:
        return HTMLResponse("<h1>Login</h1>")

    conn = get_db_connection()
    children = []

    # Try to get children from parent session
    user = get_current_user(request, conn)
    if user:
        all_children = get_children_by_parent(conn, user["id"])
        children = [
            {
                "id": c["id"],
                "name": c["name"],
                "character_image_url": c.get("character_image_url"),
            }
            for c in all_children
        ]

    # If child_id is provided directly, ensure it's in the list
    selected_child = None
    if child_id is not None:
        fetched = get_child_by_id(conn, child_id)
        if fetched:
            selected_child = {
                "id": fetched["id"],
                "name": fetched["name"],
                "character_image_url": fetched.get("character_image_url"),
            }
            # If no parent session, add this child as the only option
            if not children:
                children = [selected_child]

    return templates.TemplateResponse(
        request,
        "kid/login.html",
        {"children": children, "selected_child": selected_child, "child_id": child_id},
    )


@app.get("/kid/home", response_class=HTMLResponse)
async def kid_home_page(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return RedirectResponse(url="/kid/login", status_code=302)

    # Redirect to onboarding if first time
    if not child.get("character_onboarded"):
        return RedirectResponse(url="/kid/onboarding", status_code=302)

    if templates is None:
        return HTMLResponse(f"<h1>Привет, {child['name']}!</h1>")

    return templates.TemplateResponse(
        request,
        "kid/home.html",
        {"child": child},
    )


@app.get("/kid/onboarding", response_class=HTMLResponse)
async def kid_onboarding_page(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return RedirectResponse(url="/kid/login", status_code=302)

    if child.get("character_onboarded"):
        return RedirectResponse(url="/kid/home", status_code=302)

    if templates is None:
        return HTMLResponse("<h1>Onboarding</h1>")

    return templates.TemplateResponse(
        request,
        "kid/onboarding.html",
        {"child": child},
    )


@app.get("/kid/subject/{subject}", response_class=HTMLResponse)
async def kid_subject_page(subject: str, request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return RedirectResponse(url="/kid/login", status_code=302)

    if templates is None:
        return HTMLResponse(f"<h1>Subject Map: {subject}</h1>")

    subject_names = {"math": "Математика", "russian": "Русский язык", "english": "Английский язык", "world": "Окружающий мир"}

    return templates.TemplateResponse(
        request,
        "kid/subject_map.html",
        {"child": child, "subject": subject,
         "subject_name": subject_names.get(subject, subject)},
    )


@app.get("/kid/free-lessons", response_class=HTMLResponse)
async def kid_free_lessons_page(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return RedirectResponse(url="/kid/login", status_code=302)

    if templates is None:
        return HTMLResponse("<h1>Free Lessons</h1>")

    return templates.TemplateResponse(
        request,
        "kid/free_lessons.html",
        {"child": child},
    )


@app.get("/kid/character", response_class=HTMLResponse)
async def kid_character_page(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return RedirectResponse(url="/kid/login", status_code=302)

    if templates is None:
        return HTMLResponse("<h1>Character</h1>")

    return templates.TemplateResponse(
        request,
        "kid/character.html",
        {"child": child},
    )


@app.get("/kid/chat", response_class=HTMLResponse)
async def kid_chat_page(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return RedirectResponse(url="/kid/login", status_code=302)

    if templates is None:
        return HTMLResponse("<h1>Chat</h1>")

    import json as _json

    # Check subscription via parent
    parent_id = child["parent_id"]
    has_sub = get_active_chat_subscription(conn, parent_id) is not None

    # Characters dict for template
    characters_json = _json.dumps(
        {k: {"emoji": v["emoji"], "name_ru": v["name_ru"], "description_ru": v["description_ru"], "color": v["color"]}
         for k, v in CHAT_CHARACTERS.items()},
        ensure_ascii=False,
    )

    return templates.TemplateResponse(
        request,
        "kid/chat.html",
        {
            "child": child,
            "characters": CHAT_CHARACTERS,
            "characters_json": characters_json,
            "has_subscription": has_sub,
        },
    )


# ---------------------------------------------------------------------------
# Kid Chat API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/kid/chats")
async def kid_chats_list(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    chats = get_kid_chats_by_child(conn, child["id"])
    return JSONResponse({"chats": chats})


@app.post("/api/kid/chats")
async def kid_chat_create(request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = await request.json()
    character_key = body.get("character_key", "owl")
    if character_key not in CHAT_CHARACTERS:
        character_key = "owl"

    chat_id = create_kid_chat(conn, child["id"], character_key)
    chat = get_kid_chat(conn, chat_id)
    return JSONResponse({"chat": chat}, status_code=201)


@app.delete("/api/kid/chats/{chat_id}")
async def kid_chat_delete(chat_id: int, request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    chat = get_kid_chat(conn, chat_id)
    if not chat or chat["child_id"] != child["id"]:
        return JSONResponse({"error": "not_found"}, status_code=404)

    delete_kid_chat(conn, chat_id)
    return JSONResponse({"ok": True})


@app.get("/api/kid/chats/{chat_id}/messages")
async def kid_chat_messages(chat_id: int, request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    chat = get_kid_chat(conn, chat_id)
    if not chat or chat["child_id"] != child["id"]:
        return JSONResponse({"error": "not_found"}, status_code=404)

    messages = get_kid_chat_messages(conn, chat_id, limit=30)
    from datetime import date
    today_str = date.today().isoformat()
    daily_count = count_daily_messages(conn, child["id"], today_str)

    parent_id = child["parent_id"]
    has_sub = get_active_chat_subscription(conn, parent_id) is not None
    daily_limit = 50 if has_sub else 5

    return JSONResponse({
        "messages": messages,
        "daily_count": daily_count,
        "daily_limit": daily_limit,
    })


@app.post("/api/kid/chats/{chat_id}/send")
async def kid_chat_send(chat_id: int, request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    chat = get_kid_chat(conn, chat_id)
    if not chat or chat["child_id"] != child["id"]:
        return JSONResponse({"error": "not_found"}, status_code=404)

    # Check daily limit
    from datetime import date
    today_str = date.today().isoformat()
    daily_count = count_daily_messages(conn, child["id"], today_str)
    parent_id = child["parent_id"]
    has_sub = get_active_chat_subscription(conn, parent_id) is not None
    daily_limit = 50 if has_sub else 5

    if daily_count >= daily_limit:
        msg = "На сегодня сообщения закончились! Приходи завтра!" if not has_sub else "Лимит 50 сообщений в день достигнут. Приходи завтра!"
        if not has_sub:
            msg += " Попроси родителей подключить подписку для безлимита."
        return JSONResponse({"error": "limit_reached", "message": msg}, status_code=429)

    # Parse body (JSON or FormData)
    content_type = request.headers.get("content-type", "")
    message_text = ""
    image_url = None

    if "multipart/form-data" in content_type:
        from fastapi import UploadFile
        form = await request.form()
        message_text = form.get("message", "")
        image_file = form.get("image")
        if image_file and hasattr(image_file, "read"):
            # Save image
            import uuid
            os.makedirs("content/chat_images", exist_ok=True)
            ext = os.path.splitext(image_file.filename)[1] or ".png"
            fname = f"{uuid.uuid4().hex}{ext}"
            fpath = f"content/chat_images/{fname}"
            data = await image_file.read()
            if len(data) > 5 * 1024 * 1024:
                return JSONResponse({"error": "file_too_large"}, status_code=400)
            with open(fpath, "wb") as f:
                f.write(data)
            image_url = f"/content/chat_images/{fname}"
    else:
        body = await request.json()
        message_text = body.get("message", "")

    message_text = sanitize_message(message_text)
    if not message_text and not image_url:
        return JSONResponse({"error": "empty_message"}, status_code=400)

    # Save user message
    add_kid_chat_message(conn, chat_id, "user", message_text, image_url)

    # Get context (last 30 messages)
    history = get_kid_chat_messages(conn, chat_id, limit=30)
    context = [{"role": m["role"], "content": m["content"]} for m in history]

    # Generate AI response
    response_text = generate_chat_response(
        chat["character_key"],
        context,
        child_name=child["name"],
    )

    # Save assistant message
    add_kid_chat_message(conn, chat_id, "assistant", response_text)
    update_kid_chat_timestamp(conn, chat_id)

    # Auto-title on first user message
    title_update = None
    user_messages = [m for m in history if m["role"] == "user"]
    if len(user_messages) <= 1:
        new_title = generate_chat_title(message_text)
        update_kid_chat_title(conn, chat_id, new_title)
        title_update = new_title

    new_daily_count = daily_count + 1

    return JSONResponse({
        "response": response_text,
        "title": title_update,
        "daily_count": new_daily_count,
        "daily_limit": daily_limit,
    })


# ---------------------------------------------------------------------------
# Chat Subscription API (parent buys for account)
# ---------------------------------------------------------------------------

@app.post("/api/chat/subscribe")
async def chat_subscribe(request: Request):
    """Buy chat subscription for 300 crystals/month."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    # Check if already subscribed
    existing = get_active_chat_subscription(conn, user["id"])
    if existing:
        return JSONResponse({"error": "already_subscribed", "expires_at": existing["expires_at"]}, status_code=400)

    # Deduct 300 crystals
    ok = update_crystals(conn, user["id"], -300)
    if not ok:
        return JSONResponse({"error": "not_enough_crystals", "message": "Недостаточно кристаллов (нужно 300)"}, status_code=400)

    insert_transaction(conn, user["id"], -300, "chat_subscription")

    # Create subscription (30 days)
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=30)
    sub_id = create_chat_subscription(conn, user["id"], now.isoformat(), expires.isoformat())

    return JSONResponse({
        "ok": True,
        "subscription_id": sub_id,
        "expires_at": expires.isoformat(),
    })


@app.get("/api/chat/subscription")
async def chat_subscription_status(request: Request):
    """Check chat subscription status."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    sub = get_active_chat_subscription(conn, user["id"])
    return JSONResponse({
        "active": sub is not None,
        "expires_at": sub["expires_at"] if sub else None,
    })


@app.get("/kid/lesson/{lesson_id}", response_class=HTMLResponse)
async def kid_lesson_page(lesson_id: int, request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return RedirectResponse(url="/kid/login", status_code=302)

    lesson = get_lesson_by_id(conn, lesson_id)
    if lesson is None or lesson["child_id"] != child["id"]:
        return RedirectResponse(url="/kid/home", status_code=302)

    if templates is None:
        return HTMLResponse(f"<h1>Урок: {lesson['topic_title']}</h1>")

    return templates.TemplateResponse(
        request,
        "kid/lesson.html",
        {"child": child, "lesson": dict(lesson)},
    )


@app.get("/kid/result/{lesson_id}", response_class=HTMLResponse)
async def kid_result_page(lesson_id: int, request: Request):
    conn = get_db_connection()
    child = get_current_child(request, conn)
    if not child:
        return RedirectResponse(url="/kid/login", status_code=302)

    lesson = get_lesson_by_id(conn, lesson_id)
    if lesson is None or lesson["child_id"] != child["id"]:
        return RedirectResponse(url="/kid/home", status_code=302)

    result = get_lesson_result_by_lesson(conn, lesson_id)
    streak = get_streak_by_child(conn, child["id"])

    if templates is None:
        stars = result["stars"] if result else 0
        return HTMLResponse(f"<h1>Результат: {stars} звёзд!</h1>")

    return templates.TemplateResponse(
        request,
        "kid/result.html",
        {
            "child": child,
            "lesson": dict(lesson),
            "result": dict(result) if result else None,
            "streak": dict(streak) if streak else None,
        },
    )


# ---------------------------------------------------------------------------
# Parent Dashboard UI routes (Этап 6)
# ---------------------------------------------------------------------------

@app.get("/api/children/{child_id}/stats")
async def get_child_stats(child_id: int, request: Request):
    """Return aggregated stats for a child: lesson counts, stars, streaks, active plans."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    # Total lessons
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM lessons WHERE child_id=?", (child_id,)
    ).fetchone()
    total_lessons = row["cnt"] if row else 0

    # Average stars from lesson_results
    row = conn.execute(
        "SELECT AVG(CAST(stars AS REAL)) as avg_stars FROM lesson_results WHERE child_id=?",
        (child_id,),
    ).fetchone()
    raw_avg = row["avg_stars"] if row else None
    if raw_avg is None:
        average_stars = 0
    else:
        average_stars = round(raw_avg, 1)

    # Streak
    streak = get_streak_by_child(conn, child_id)
    current_streak = streak["current_streak"] if streak else 0
    longest_streak = streak["longest_streak"] if streak else 0

    # Active weekly plan
    plan = get_active_weekly_plan(conn, child_id)
    active_weekly_plan = None
    if plan:
        # Get unit title from curriculum
        ct_row = conn.execute(
            "SELECT * FROM curriculum_templates WHERE id=?", (plan["curriculum_id"],)
        ).fetchone()
        import json as _json
        unit_title = ""
        if ct_row:
            try:
                topics_data = _json.loads(ct_row["topics_json"])
                for unit in topics_data.get("units", []):
                    if unit.get("id") == plan["unit_id"]:
                        unit_title = unit.get("title", "")
                        break
            except Exception:
                pass
        lessons_count = plan["lessons_count"] or 0
        current_index = plan["current_lesson_index"] or 0
        active_weekly_plan = {
            "id": plan["id"],
            "unit_title": unit_title,
            "progress": f"{current_index}/{lessons_count}",
        }

    # Active enrollments
    enrollments = get_active_enrollments(conn, child_id)
    active_enrollments = []
    for e in enrollments:
        ct_row = conn.execute(
            "SELECT * FROM curriculum_templates WHERE id=?", (e["curriculum_id"],)
        ).fetchone()
        ct = dict(ct_row) if ct_row else {}
        # Count total topics
        flat = _get_flat_topics(conn, e["curriculum_id"])
        total_topics = len(flat)
        idx = e["current_topic_index"] or 0
        active_enrollments.append({
            "id": e["id"],
            "subject": ct.get("subject", ""),
            "title": ct.get("title", ""),
            "progress": f"{idx}/{total_topics}",
        })

    return JSONResponse({
        "total_lessons": total_lessons,
        "average_stars": average_stars,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "active_weekly_plan": active_weekly_plan,
        "active_enrollments": active_enrollments,
    })


@app.get("/api/children/{child_id}/lessons")
async def get_child_lessons(child_id: int, request: Request):
    """Return all lessons for a child (for parent's history view)."""
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if child["parent_id"] != user["id"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    all_lessons = get_lessons_by_child(conn, child_id)
    lessons = []
    for l in all_lessons:
        lessons.append({
            "id": l["id"],
            "topic_title": l["topic_title"],
            "subject": l["subject"],
            "mode": l["mode"],
            "status": l["status"],
            "stars": l["stars"],
            "content_url": l["content_url"],
            "created_at": l.get("created_at"),
        })

    return JSONResponse({"lessons": lessons})


@app.get("/dashboard", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if templates is None:
        return HTMLResponse("<h1>Dashboard</h1>")
    return templates.TemplateResponse(request, "dashboard.html", {"user": user})


@app.get("/children/new", response_class=HTMLResponse)
async def page_child_new(request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if templates is None:
        return HTMLResponse("<h1>New Child</h1>")
    return templates.TemplateResponse(request, "child_new.html", {"user": user})


@app.get("/children/{child_id}", response_class=HTMLResponse)
async def page_child_profile(child_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    child = get_child_by_id(conn, child_id)
    if child is None:
        if templates is None:
            return HTMLResponse("<h1>Not Found</h1>", status_code=404)
        return templates.TemplateResponse(
            request, "base.html",
            {"user": user, "error": "Ребёнок не найден"},
            status_code=404,
        )
    if child["parent_id"] != user["id"]:
        if templates is None:
            return HTMLResponse("<h1>Forbidden</h1>", status_code=403)
        return templates.TemplateResponse(
            request, "base.html",
            {"user": user, "error": "Доступ запрещён"},
            status_code=403,
        )

    if templates is None:
        return HTMLResponse("<h1>Child Profile</h1>")

    child_dict = dict(child)
    child_dict.pop("pin_hash", None)
    streak = get_streak_by_child(conn, child_id)
    if streak:
        child_dict["current_streak"] = streak["current_streak"]
    else:
        child_dict["current_streak"] = 0

    return templates.TemplateResponse(
        request, "child_profile.html",
        {"user": user, "child": child_dict},
    )


@app.get("/children/{child_id}/history", response_class=HTMLResponse)
async def page_child_history(child_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    child = get_child_by_id(conn, child_id)
    if child is None:
        if templates is None:
            return HTMLResponse("<h1>Not Found</h1>", status_code=404)
        return templates.TemplateResponse(
            request, "base.html",
            {"user": user, "error": "Ребёнок не найден"},
            status_code=404,
        )
    if child["parent_id"] != user["id"]:
        if templates is None:
            return HTMLResponse("<h1>Forbidden</h1>", status_code=403)
        return templates.TemplateResponse(
            request, "base.html",
            {"user": user, "error": "Доступ запрещён"},
            status_code=403,
        )

    if templates is None:
        return HTMLResponse("<h1>History</h1>")

    child_dict = dict(child)
    child_dict.pop("pin_hash", None)

    return templates.TemplateResponse(
        request, "child_history.html",
        {"user": user, "child": child_dict},
    )


@app.get("/children/{child_id}/program", response_class=HTMLResponse)
async def page_child_program(child_id: int, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    child = get_child_by_id(conn, child_id)
    if child is None:
        if templates is None:
            return HTMLResponse("<h1>Not Found</h1>", status_code=404)
        return templates.TemplateResponse(
            request, "base.html",
            {"user": user, "error": "Ребёнок не найден"},
            status_code=404,
        )
    if child["parent_id"] != user["id"]:
        if templates is None:
            return HTMLResponse("<h1>Forbidden</h1>", status_code=403)
        return templates.TemplateResponse(
            request, "base.html",
            {"user": user, "error": "Доступ запрещён"},
            status_code=403,
        )

    if templates is None:
        return HTMLResponse("<h1>Program</h1>")

    child_dict = dict(child)
    child_dict.pop("pin_hash", None)

    return templates.TemplateResponse(
        request, "program.html",
        {"user": user, "child": child_dict},
    )


@app.get("/children/{child_id}/subject/{subject}", response_class=HTMLResponse)
async def page_child_subject(child_id: int, subject: str, request: Request):
    conn = get_db_connection()
    user = get_current_user(request, conn)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    child = get_child_by_id(conn, child_id)
    if child is None:
        return RedirectResponse(url="/dashboard", status_code=302)
    if child["parent_id"] != user["id"]:
        return RedirectResponse(url="/dashboard", status_code=302)

    if templates is None:
        return HTMLResponse(f"<h1>Subject: {subject}</h1>")

    child_dict = dict(child)
    child_dict.pop("pin_hash", None)

    subject_names = {"math": "Математика", "russian": "Русский язык", "english": "Английский язык", "world": "Окружающий мир"}

    return templates.TemplateResponse(
        request, "subject.html",
        {"user": user, "child": child_dict, "subject": subject,
         "subject_name": subject_names.get(subject, subject)},
    )
