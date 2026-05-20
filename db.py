"""
db.py — SQLite database layer for kidion.

Uses thread-local connections to avoid sharing SQLite connections across threads.
"""

import sqlite3
import threading
from datetime import datetime, timezone

_local = threading.local()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a thread-local SQLite connection for db_path, initializing DB if needed."""
    if not hasattr(_local, "connections"):
        _local.connections = {}
    if db_path not in _local.connections:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # Initialize schema lazily on first connection
        _init_schema(conn)
        _local.connections[db_path] = conn
    return _local.connections[db_path]


def _init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if they don't exist (on given connection)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            crystals INTEGER NOT NULL DEFAULT 0,
            ref_code TEXT NOT NULL UNIQUE,
            referred_by INTEGER REFERENCES users(id),
            is_blogger INTEGER NOT NULL DEFAULT 0,
            blogger_balance_rub REAL NOT NULL DEFAULT 0.0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            delta INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            yookassa_payment_id TEXT NOT NULL UNIQUE,
            amount_rub REAL NOT NULL,
            crystals INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            result_url TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL REFERENCES users(id),
            referred_id INTEGER NOT NULL REFERENCES users(id),
            blogger_reward_paid INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS children (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name             TEXT NOT NULL,
            gender           TEXT NOT NULL CHECK(gender IN ('boy', 'girl')),
            birth_date       TEXT NOT NULL,
            grade            INTEGER NOT NULL CHECK(grade BETWEEN 1 AND 11),
            universe         TEXT NOT NULL,
            pin_hash         TEXT NOT NULL,
            difficulty_level INTEGER NOT NULL DEFAULT 2 CHECK(difficulty_level BETWEEN 1 AND 3),
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS curriculum_templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            subject     TEXT NOT NULL,
            grade       INTEGER NOT NULL,
            title       TEXT NOT NULL,
            topics_json TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS curriculum_enrollments (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id              INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
            curriculum_id         INTEGER NOT NULL REFERENCES curriculum_templates(id),
            current_topic_index   INTEGER NOT NULL DEFAULT 0,
            retry_count           INTEGER NOT NULL DEFAULT 0,
            status                TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed', 'paused')),
            started_at            TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS weekly_plans (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id              INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
            curriculum_id         INTEGER NOT NULL REFERENCES curriculum_templates(id),
            unit_id               TEXT NOT NULL,
            topic_ids_json        TEXT NOT NULL,
            lessons_count         INTEGER NOT NULL,
            current_lesson_index  INTEGER NOT NULL DEFAULT 0,
            status                TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed', 'abandoned')),
            created_at            TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS lessons (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id        INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
            generation_id   INTEGER REFERENCES generations(id),
            mode            TEXT NOT NULL CHECK(mode IN ('on_demand', 'weekly', 'curriculum', 'skip_test')),
            topic_id        TEXT,
            topic_title     TEXT NOT NULL,
            subject         TEXT NOT NULL,
            content_url     TEXT,
            print_url       TEXT,
            worksheet_url   TEXT,
            icon            TEXT,
            plan_id         INTEGER REFERENCES weekly_plans(id),
            enrollment_id   INTEGER REFERENCES curriculum_enrollments(id),
            sequence_number INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS lesson_results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id       INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
            child_id        INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
            correct_answers INTEGER NOT NULL CHECK(correct_answers BETWEEN 0 AND 5),
            total_answers   INTEGER NOT NULL DEFAULT 5,
            stars           INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 3),
            completed_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS streaks (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id           INTEGER NOT NULL UNIQUE REFERENCES children(id) ON DELETE CASCADE,
            current_streak     INTEGER NOT NULL DEFAULT 0,
            longest_streak     INTEGER NOT NULL DEFAULT 0,
            last_activity_date TEXT
        );

        CREATE TABLE IF NOT EXISTS curriculum_topics (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            subject       TEXT NOT NULL,
            grade         INTEGER NOT NULL,
            theme_order   INTEGER NOT NULL,
            title_ru      TEXT NOT NULL,
            icon          TEXT,
            UNIQUE(subject, grade, theme_order)
        );

        CREATE INDEX IF NOT EXISTS idx_ct_subject_grade ON curriculum_topics(subject, grade);

        CREATE TABLE IF NOT EXISTS curriculum_lessons (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id      INTEGER NOT NULL REFERENCES curriculum_topics(id),
            lesson_order  INTEGER NOT NULL,
            title_ru      TEXT NOT NULL,
            prompt_hint   TEXT,
            UNIQUE(topic_id, lesson_order)
        );

        CREATE INDEX IF NOT EXISTS idx_cl_topic ON curriculum_lessons(topic_id);

        CREATE TABLE IF NOT EXISTS child_lesson_progress (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id             INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
            curriculum_lesson_id INTEGER NOT NULL REFERENCES curriculum_lessons(id),
            status               TEXT NOT NULL DEFAULT 'locked'
                                 CHECK(status IN ('locked', 'available', 'completed', 'test')),
            lesson_id            INTEGER REFERENCES lessons(id),
            stars_earned         INTEGER NOT NULL DEFAULT 0,
            completed_at         TEXT,
            UNIQUE(child_id, curriculum_lesson_id)
        );

        CREATE INDEX IF NOT EXISTS idx_clp_child ON child_lesson_progress(child_id);
        CREATE INDEX IF NOT EXISTS idx_clp_child_lesson ON child_lesson_progress(child_id, curriculum_lesson_id);

        CREATE TABLE IF NOT EXISTS shop_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id        INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
            category        TEXT NOT NULL CHECK(category IN ('outfit', 'accessory', 'pet', 'background', 'special')),
            title_ru        TEXT NOT NULL,
            description_ru  TEXT NOT NULL DEFAULT '',
            emoji           TEXT NOT NULL DEFAULT '',
            price_stars     INTEGER NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_shop_items_child ON shop_items(child_id);

        CREATE TABLE IF NOT EXISTS child_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id    INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
            item_id     INTEGER NOT NULL REFERENCES shop_items(id) ON DELETE CASCADE,
            equipped    INTEGER NOT NULL DEFAULT 1,
            purchased_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(child_id, item_id)
        );

        CREATE INDEX IF NOT EXISTS idx_child_items_child ON child_items(child_id);

        CREATE TABLE IF NOT EXISTS content_reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id   INTEGER REFERENCES lessons(id) ON DELETE SET NULL,
            child_id    INTEGER REFERENCES children(id) ON DELETE SET NULL,
            user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            reason      TEXT NOT NULL DEFAULT 'inappropriate_content',
            status      TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'reviewed', 'resolved')),
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS kid_chats (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id        INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
            character_key   TEXT NOT NULL DEFAULT 'owl',
            title           TEXT NOT NULL DEFAULT 'Новый чат',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_kid_chats_child ON kid_chats(child_id);

        CREATE TABLE IF NOT EXISTS kid_chat_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id         INTEGER NOT NULL REFERENCES kid_chats(id) ON DELETE CASCADE,
            role            TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content         TEXT NOT NULL,
            image_url       TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_kid_chat_messages_chat ON kid_chat_messages(chat_id);

        CREATE TABLE IF NOT EXISTS chat_subscriptions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            started_at      TEXT NOT NULL,
            expires_at      TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_chat_subs_user ON chat_subscriptions(user_id);

        CREATE TABLE IF NOT EXISTS chat_reports (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id        INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
            date            TEXT NOT NULL,
            summary         TEXT NOT NULL DEFAULT '',
            topics_json     TEXT NOT NULL DEFAULT '[]',
            message_count   INTEGER NOT NULL DEFAULT 0,
            character_key   TEXT NOT NULL DEFAULT 'spark',
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_chat_reports_child ON chat_reports(child_id, date);

        CREATE TABLE IF NOT EXISTS chat_characters (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            key             TEXT NOT NULL UNIQUE,
            name_ru         TEXT NOT NULL,
            role_ru         TEXT NOT NULL,
            avatar_type     TEXT NOT NULL DEFAULT 'svg',
            system_prompt   TEXT NOT NULL,
            greeting_ru     TEXT NOT NULL,
            greeting_sub_ru TEXT NOT NULL DEFAULT '',
            suggestions_json TEXT NOT NULL DEFAULT '[]',
            accent_color    TEXT NOT NULL DEFAULT '',
            is_free         INTEGER NOT NULL DEFAULT 0,
            sort_order      INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS methodologist_cache (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            subject    TEXT NOT NULL,
            grade      INTEGER NOT NULL,
            topic      TEXT NOT NULL,
            output     TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(subject, grade, topic)
        );

        CREATE TABLE IF NOT EXISTS topic_images (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            curriculum_topic_id INTEGER,
            subject         TEXT NOT NULL,
            grade           INTEGER NOT NULL,
            topic           TEXT NOT NULL,
            image_filename  TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(subject, grade, topic)
        );

        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_ref_code ON users(ref_code);
        CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_payments_yk_id ON payments(yookassa_payment_id);
        CREATE INDEX IF NOT EXISTS idx_generations_user ON generations(user_id);
        CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id);
    """)
    conn.commit()

    # Add status column to lessons table (migration-safe)
    try:
        conn.execute("ALTER TABLE lessons ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists
        pass

    # Add stars column to children table (migration-safe)
    try:
        conn.execute("ALTER TABLE children ADD COLUMN stars INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Add interests column to children table (migration-safe)
    try:
        conn.execute("ALTER TABLE children ADD COLUMN interests TEXT NOT NULL DEFAULT '[]'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Add universe_description column to children table (migration-safe)
    try:
        conn.execute("ALTER TABLE children ADD COLUMN universe_description TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Add character_prompt column to children table (migration-safe)
    try:
        conn.execute("ALTER TABLE children ADD COLUMN character_prompt TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Add character_image_url column to children table (migration-safe)
    try:
        conn.execute("ALTER TABLE children ADD COLUMN character_image_url TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Add character_name column to children table (migration-safe)
    try:
        conn.execute("ALTER TABLE children ADD COLUMN character_name TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Add character_onboarded column to children table (migration-safe)
    try:
        conn.execute("ALTER TABLE children ADD COLUMN character_onboarded INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Add images_remaining and payment_id to chat_subscriptions (migration-safe)
    for col, defn in [
        ("images_remaining", "INTEGER NOT NULL DEFAULT 0"),
        ("amount_rub", "REAL NOT NULL DEFAULT 0"),
        ("payment_id", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE chat_subscriptions ADD COLUMN {col} {defn}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Seed curriculum data
    _seed_math_grade1(conn)

    # Seed chat characters
    _seed_chat_characters(conn)


def init_db(db_path: str) -> None:
    """Create all tables and indexes if they don't exist."""
    conn = get_connection(db_path)
    _init_schema(conn)
    _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Run incremental migrations for schema changes."""
    # Add worksheet_url column to lessons if missing
    cols = [row[1] for row in conn.execute("PRAGMA table_info(lessons)").fetchall()]
    if "worksheet_url" not in cols:
        conn.execute("ALTER TABLE lessons ADD COLUMN worksheet_url TEXT")
        conn.commit()

    # Add icon column to lessons if missing
    cols = [row[1] for row in conn.execute("PRAGMA table_info(lessons)").fetchall()]
    if "icon" not in cols:
        conn.execute("ALTER TABLE lessons ADD COLUMN icon TEXT")
        conn.commit()

    # Add consent columns to users table
    user_cols = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "consent_given_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN consent_given_at TEXT")
        conn.commit()
    if "consent_version" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN consent_version TEXT")
        conn.commit()


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------

def create_user(
    conn: sqlite3.Connection,
    email: str,
    password_hash: str,
    crystals: int,
    ref_code: str,
    referred_by: int | None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO users (email, password_hash, crystals, ref_code, referred_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (email, password_hash, crystals, ref_code, referred_by, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def get_user_by_email(conn: sqlite3.Connection, email: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    return dict(row) if row else None


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return dict(row) if row else None


def delete_user(conn: sqlite3.Connection, user_id: int) -> bool:
    """
    Delete user and all associated data (children cascade-delete their own data).
    Returns True if deleted, False if not found.
    """
    # Get all children to delete their character images
    children = conn.execute(
        "SELECT id FROM children WHERE parent_id = ?", (user_id,)
    ).fetchall()
    child_ids = [row[0] for row in children]

    # Delete children first (cascades to lessons, chats, etc.)
    for cid in child_ids:
        conn.execute("DELETE FROM children WHERE id = ?", (cid,))

    # Delete user-level data
    conn.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM payments WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM generations WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM referrals WHERE referrer_id = ? OR referred_id = ?", (user_id, user_id))
    conn.execute("DELETE FROM chat_subscriptions WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM content_reports WHERE user_id = ?", (user_id,))

    cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    return cursor.rowcount == 1


def get_user_by_ref_code(conn: sqlite3.Connection, ref_code: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM users WHERE ref_code = ?", (ref_code,)
    ).fetchone()
    return dict(row) if row else None


def update_user_password(conn: sqlite3.Connection, user_id: int, password_hash: str) -> None:
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (password_hash, user_id),
    )
    conn.commit()


def update_crystals(conn: sqlite3.Connection, user_id: int, delta: int) -> bool:
    """
    Atomically update crystals by delta.
    For negative delta, uses WHERE crystals >= abs(delta) to prevent going below zero.
    Returns True if the update succeeded.
    """
    if delta >= 0:
        conn.execute(
            "UPDATE users SET crystals = crystals + ? WHERE id = ?",
            (delta, user_id),
        )
        conn.commit()
        return True
    else:
        cursor = conn.execute(
            "UPDATE users SET crystals = crystals + ? WHERE id = ? AND crystals >= ?",
            (delta, user_id, abs(delta)),
        )
        conn.commit()
        return cursor.rowcount == 1


def insert_transaction(
    conn: sqlite3.Connection,
    user_id: int,
    delta: int,
    reason: str,
) -> None:
    conn.execute(
        "INSERT INTO transactions (user_id, delta, reason, created_at) VALUES (?, ?, ?, ?)",
        (user_id, delta, reason, _now()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Generation operations
# ---------------------------------------------------------------------------

def create_generation(conn: sqlite3.Connection, user_id: int, gen_type: str) -> int:
    cursor = conn.execute(
        "INSERT INTO generations (user_id, type, status, created_at) VALUES (?, ?, 'pending', ?)",
        (user_id, gen_type, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def get_generation(conn: sqlite3.Connection, gen_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM generations WHERE id = ?", (gen_id,)
    ).fetchone()
    return dict(row) if row else None


def update_generation(
    conn: sqlite3.Connection,
    gen_id: int,
    status: str,
    result_url: str | None = None,
) -> None:
    conn.execute(
        "UPDATE generations SET status = ?, result_url = ? WHERE id = ?",
        (status, result_url, gen_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Payment operations
# ---------------------------------------------------------------------------

def create_payment(
    conn: sqlite3.Connection,
    user_id: int,
    yk_payment_id: str,
    amount_rub: float,
    crystals: int,
) -> int:
    cursor = conn.execute(
        "INSERT INTO payments (user_id, yookassa_payment_id, amount_rub, crystals, status, created_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?)",
        (user_id, yk_payment_id, amount_rub, crystals, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def get_payment_by_yk_id(conn: sqlite3.Connection, yk_payment_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM payments WHERE yookassa_payment_id = ?", (yk_payment_id,)
    ).fetchone()
    return dict(row) if row else None


def get_payment_by_id(conn: sqlite3.Connection, payment_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM payments WHERE id = ?", (payment_id,)
    ).fetchone()
    return dict(row) if row else None


def update_payment_status(conn: sqlite3.Connection, payment_id: int, status: str) -> None:
    conn.execute(
        "UPDATE payments SET status = ? WHERE id = ?",
        (status, payment_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Referral operations
# ---------------------------------------------------------------------------

def create_referral(
    conn: sqlite3.Connection,
    referrer_id: int,
    referred_id: int,
) -> int:
    cursor = conn.execute(
        "INSERT INTO referrals (referrer_id, referred_id, blogger_reward_paid, created_at) "
        "VALUES (?, ?, 0, ?)",
        (referrer_id, referred_id, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def get_referral_by_referred(conn: sqlite3.Connection, referred_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM referrals WHERE referred_id = ?", (referred_id,)
    ).fetchone()
    return dict(row) if row else None


def update_referral_paid(conn: sqlite3.Connection, referral_id: int) -> bool:
    """Atomically mark referral as paid. Returns True if the row was updated (race-condition safe)."""
    cursor = conn.execute(
        "UPDATE referrals SET blogger_reward_paid = 1 WHERE id = ? AND blogger_reward_paid = 0",
        (referral_id,),
    )
    conn.commit()
    return cursor.rowcount == 1


def update_blogger_balance(
    conn: sqlite3.Connection,
    user_id: int,
    amount_rub: float,
) -> None:
    conn.execute(
        "UPDATE users SET blogger_balance_rub = blogger_balance_rub + ? WHERE id = ?",
        (amount_rub, user_id),
    )
    conn.commit()


def count_successful_payments(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM payments WHERE user_id = ? AND status = 'succeeded'",
        (user_id,),
    ).fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Children operations
# ---------------------------------------------------------------------------

ALLOWED_UPDATE_FIELDS = {"name", "gender", "birth_date", "grade", "universe", "pin_hash", "interests"}


def create_child(
    conn: sqlite3.Connection,
    parent_id: int,
    name: str,
    gender: str,
    birth_date: str,
    grade: int,
    universe: str,
    pin_hash: str,
) -> dict:
    """
    INSERT into children with difficulty_level=2 (hardcoded).
    Also INSERT into streaks (current_streak=0, longest_streak=0).
    Returns full child record WITHOUT pin_hash.
    Raises sqlite3.IntegrityError on constraint violation.
    """
    cursor = conn.execute(
        "INSERT INTO children (parent_id, name, gender, birth_date, grade, universe, pin_hash, difficulty_level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 2)",
        (parent_id, name, gender, birth_date, grade, universe, pin_hash),
    )
    child_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO streaks (child_id, current_streak, longest_streak) VALUES (?, 0, 0)",
        (child_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, parent_id, name, gender, birth_date, grade, universe, "
        "difficulty_level, created_at, updated_at FROM children WHERE id = ?",
        (child_id,),
    ).fetchone()
    return dict(row)


def get_children_by_parent(conn: sqlite3.Connection, parent_id: int) -> list[dict]:
    """SELECT all children WHERE parent_id = ? ORDER BY created_at ASC. Each dict excludes pin_hash."""
    rows = conn.execute(
        "SELECT id, parent_id, name, gender, birth_date, grade, universe, "
        "difficulty_level, stars, character_image_url, universe_description, interests, "
        "character_name, character_onboarded, "
        "created_at, updated_at FROM children WHERE parent_id = ? ORDER BY created_at ASC",
        (parent_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_child_by_id(conn: sqlite3.Connection, child_id: int) -> dict | None:
    """SELECT child WHERE id = ?. Returns full record INCLUDING pin_hash. Returns None if not found."""
    row = conn.execute(
        "SELECT * FROM children WHERE id = ?", (child_id,)
    ).fetchone()
    return dict(row) if row else None


def update_child(conn: sqlite3.Connection, child_id: int, **fields) -> dict | None:
    """
    UPDATE children SET <fields>, updated_at = now() WHERE id = ?.
    Allowed keys: name, gender, birth_date, grade, universe, pin_hash.
    Silently ignores any other keys (difficulty_level, parent_id, etc.).
    Returns updated record WITHOUT pin_hash, or None if not found.
    """
    safe = {k: v for k, v in fields.items() if k in ALLOWED_UPDATE_FIELDS}
    if not safe:
        row = conn.execute(
            "SELECT id, parent_id, name, gender, birth_date, grade, universe, "
            "difficulty_level, created_at, updated_at FROM children WHERE id = ?",
            (child_id,),
        ).fetchone()
        return dict(row) if row else None
    safe["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in safe)
    conn.execute(
        f"UPDATE children SET {set_clause} WHERE id = ?",
        list(safe.values()) + [child_id],
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, parent_id, name, gender, birth_date, grade, universe, "
        "difficulty_level, created_at, updated_at FROM children WHERE id = ?",
        (child_id,),
    ).fetchone()
    return dict(row) if row else None


def delete_child(conn: sqlite3.Connection, child_id: int) -> bool:
    """
    DELETE FROM children WHERE id = ?.
    CASCADE removes streaks, lessons, lesson_results, weekly_plans, curriculum_enrollments.
    Returns True if deleted, False if not found.
    """
    cursor = conn.execute("DELETE FROM children WHERE id = ?", (child_id,))
    conn.commit()
    return cursor.rowcount == 1


def count_children_by_parent(conn: sqlite3.Connection, parent_id: int) -> int:
    """SELECT COUNT(*) FROM children WHERE parent_id = ?. Returns int."""
    row = conn.execute(
        "SELECT COUNT(*) FROM children WHERE parent_id = ?", (parent_id,)
    ).fetchone()
    return row[0] if row else 0


def get_streak_by_child(conn: sqlite3.Connection, child_id: int) -> dict | None:
    """
    SELECT streak row for child_id.
    Returns {id, child_id, current_streak, longest_streak, last_activity_date} or None.
    """
    row = conn.execute(
        "SELECT * FROM streaks WHERE child_id = ?", (child_id,)
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Lesson operations
# ---------------------------------------------------------------------------

def create_lesson(
    conn: sqlite3.Connection,
    child_id: int,
    mode: str,
    topic_title: str,
    subject: str,
    generation_id: int | None = None,
) -> int:
    """
    INSERT into lessons with status='pending'.
    Returns lesson id.
    """
    cursor = conn.execute(
        "INSERT INTO lessons (child_id, mode, topic_title, subject, status, generation_id) "
        "VALUES (?, ?, ?, ?, 'pending', ?)",
        (child_id, mode, topic_title, subject, generation_id),
    )
    conn.commit()
    return cursor.lastrowid


def get_lesson_by_id(conn: sqlite3.Connection, lesson_id: int) -> dict | None:
    """SELECT * FROM lessons WHERE id = ?. Returns dict or None."""
    row = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    return dict(row) if row else None


def update_lesson_content(
    conn: sqlite3.Connection,
    lesson_id: int,
    content_url: str | None,
    print_url: str | None,
    status: str,
    worksheet_url: str | None = None,
    icon: str | None = None,
) -> None:
    """UPDATE lessons SET content_url=?, print_url=?, worksheet_url=?, icon=?, status=? WHERE id=?"""
    conn.execute(
        "UPDATE lessons SET content_url = ?, print_url = ?, worksheet_url = ?, icon = ?, status = ? WHERE id = ?",
        (content_url, print_url, worksheet_url, icon, status, lesson_id),
    )
    conn.commit()


def get_recent_lesson_titles(conn: sqlite3.Connection, child_id: int, limit: int = 3) -> list[str]:
    """
    SELECT topic_title FROM lessons WHERE child_id=? ORDER BY created_at DESC, id DESC LIMIT ?.
    Returns list of titles.
    """
    rows = conn.execute(
        "SELECT topic_title FROM lessons WHERE child_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        (child_id, limit),
    ).fetchall()
    return [row[0] for row in rows]


def create_lesson_result(
    conn: sqlite3.Connection,
    lesson_id: int,
    child_id: int,
    correct_answers: int,
    total_answers: int,
    stars: int,
) -> int:
    """INSERT INTO lesson_results. Returns result id."""
    cursor = conn.execute(
        "INSERT INTO lesson_results (lesson_id, child_id, correct_answers, total_answers, stars) "
        "VALUES (?, ?, ?, ?, ?)",
        (lesson_id, child_id, correct_answers, total_answers, stars),
    )
    conn.commit()
    return cursor.lastrowid


def get_recent_lesson_results(conn: sqlite3.Connection, child_id: int, limit: int = 2) -> list[dict]:
    """
    SELECT * FROM lesson_results WHERE child_id=? ORDER BY completed_at DESC LIMIT ?.
    Returns list of dicts.
    """
    rows = conn.execute(
        "SELECT * FROM lesson_results WHERE child_id = ? ORDER BY completed_at DESC LIMIT ?",
        (child_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def update_difficulty_level(conn: sqlite3.Connection, child_id: int, new_level: int) -> None:
    """UPDATE children SET difficulty_level=? WHERE id=?"""
    conn.execute(
        "UPDATE children SET difficulty_level = ? WHERE id = ?",
        (new_level, child_id),
    )
    conn.commit()


def update_streak(conn: sqlite3.Connection, child_id: int, today_str: str) -> dict:
    """
    Update streak for child_id based on today_str.
    Logic:
      - last_activity_date == today → no change
      - last_activity_date == yesterday → current_streak += 1
      - else → current_streak = 1
      - longest_streak = max(longest_streak, current_streak)
    Returns updated streak dict.
    """
    from datetime import date, timedelta

    streak = get_streak_by_child(conn, child_id)
    if streak is None:
        # Create streak record if it doesn't exist (shouldn't happen, but handle it)
        conn.execute(
            "INSERT INTO streaks (child_id, current_streak, longest_streak, last_activity_date) "
            "VALUES (?, 1, 1, ?)",
            (child_id, today_str),
        )
        conn.commit()
        return get_streak_by_child(conn, child_id)

    last_date = streak["last_activity_date"]
    today = date.fromisoformat(today_str)

    if last_date == today_str:
        # Already updated today
        return streak

    if last_date:
        last = date.fromisoformat(last_date)
        yesterday = today - timedelta(days=1)
        if last == yesterday:
            # Consecutive day
            new_current = streak["current_streak"] + 1
        else:
            # Streak broken
            new_current = 1
    else:
        # First activity
        new_current = 1

    new_longest = max(streak["longest_streak"], new_current)

    conn.execute(
        "UPDATE streaks SET current_streak = ?, longest_streak = ?, last_activity_date = ? "
        "WHERE child_id = ?",
        (new_current, new_longest, today_str, child_id),
    )
    conn.commit()

    return get_streak_by_child(conn, child_id)


# ---------------------------------------------------------------------------
# Kid interface helpers
# ---------------------------------------------------------------------------

def get_lessons_by_child(conn: sqlite3.Connection, child_id: int) -> list[dict]:
    """
    Fetch all lessons for a child with their result (if any), ordered by created_at DESC.
    Each item includes: id, topic_title, subject, status, content_url, print_url, stars.
    """
    rows = conn.execute(
        """
        SELECT l.id, l.topic_title, l.subject, l.status, l.content_url, l.print_url, l.worksheet_url,
               l.plan_id, l.mode, l.sequence_number, l.created_at,
               lr.stars, lr.correct_answers, lr.completed_at AS result_completed_at
        FROM lessons l
        LEFT JOIN lesson_results lr ON lr.lesson_id = l.id
        WHERE l.child_id = ?
        ORDER BY l.created_at ASC, l.id ASC
        """,
        (child_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_lesson_result_by_lesson(conn: sqlite3.Connection, lesson_id: int) -> dict | None:
    """Get the most recent result for a lesson."""
    row = conn.execute(
        "SELECT * FROM lesson_results WHERE lesson_id = ? ORDER BY completed_at DESC LIMIT 1",
        (lesson_id,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Weekly plan operations
# ---------------------------------------------------------------------------

def create_weekly_plan(
    conn: sqlite3.Connection,
    child_id: int,
    curriculum_id: int,
    unit_id: str,
    topic_ids: list,
    lessons_count: int,
) -> int:
    """INSERT into weekly_plans. Returns plan id."""
    import json as _json
    cursor = conn.execute(
        "INSERT INTO weekly_plans "
        "(child_id, curriculum_id, unit_id, topic_ids_json, lessons_count, current_lesson_index, status) "
        "VALUES (?, ?, ?, ?, ?, 0, 'active')",
        (child_id, curriculum_id, unit_id, _json.dumps(topic_ids), lessons_count),
    )
    conn.commit()
    return cursor.lastrowid


def get_weekly_plan(conn: sqlite3.Connection, plan_id: int) -> dict | None:
    """SELECT weekly_plan by id. Returns dict or None."""
    row = conn.execute("SELECT * FROM weekly_plans WHERE id=?", (plan_id,)).fetchone()
    return dict(row) if row else None


def get_active_weekly_plan(conn: sqlite3.Connection, child_id: int) -> dict | None:
    """SELECT most recent active weekly_plan for child."""
    row = conn.execute(
        "SELECT * FROM weekly_plans WHERE child_id=? AND status='active' "
        "ORDER BY created_at DESC LIMIT 1",
        (child_id,),
    ).fetchone()
    return dict(row) if row else None


def update_weekly_plan_index(conn: sqlite3.Connection, plan_id: int, new_index: int) -> None:
    """UPDATE current_lesson_index for a weekly plan."""
    conn.execute(
        "UPDATE weekly_plans SET current_lesson_index=? WHERE id=?",
        (new_index, plan_id),
    )
    conn.commit()


def complete_weekly_plan(conn: sqlite3.Connection, plan_id: int) -> None:
    """Mark plan as completed."""
    conn.execute("UPDATE weekly_plans SET status='completed' WHERE id=?", (plan_id,))
    conn.commit()


def get_lessons_by_plan(conn: sqlite3.Connection, plan_id: int) -> list[dict]:
    """Get all lessons for a weekly plan with their results, ordered by sequence_number."""
    rows = conn.execute(
        """
        SELECT l.id, l.topic_title, l.topic_id, l.status, l.content_url,
               l.sequence_number, lr.stars
        FROM lessons l
        LEFT JOIN lesson_results lr ON lr.lesson_id = l.id
        WHERE l.plan_id=?
        ORDER BY l.sequence_number ASC
        """,
        (plan_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def create_weekly_lesson(
    conn: sqlite3.Connection,
    child_id: int,
    topic_id: str,
    topic_title: str,
    subject: str,
    plan_id: int,
    sequence_number: int,
) -> int:
    """Create a lesson record for a weekly plan. Returns lesson id."""
    cursor = conn.execute(
        "INSERT INTO lessons "
        "(child_id, mode, topic_id, topic_title, subject, plan_id, sequence_number, status) "
        "VALUES (?, 'weekly', ?, ?, ?, ?, ?, 'pending')",
        (child_id, topic_id, topic_title, subject, plan_id, sequence_number),
    )
    conn.commit()
    return cursor.lastrowid


# ---------------------------------------------------------------------------
# Curriculum Enrollment operations
# ---------------------------------------------------------------------------

def create_enrollment(
    conn: sqlite3.Connection,
    child_id: int,
    curriculum_id: int,
    start_topic_index: int = 0,
) -> int:
    """INSERT into curriculum_enrollments. Returns enrollment_id."""
    cursor = conn.execute(
        "INSERT INTO curriculum_enrollments "
        "(child_id, curriculum_id, current_topic_index, retry_count, status, started_at, updated_at) "
        "VALUES (?, ?, ?, 0, 'active', ?, ?)",
        (child_id, curriculum_id, start_topic_index, _now(), _now()),
    )
    conn.commit()
    return cursor.lastrowid


def get_enrollment_by_id(conn: sqlite3.Connection, enrollment_id: int) -> dict | None:
    """SELECT * FROM curriculum_enrollments WHERE id=?"""
    row = conn.execute(
        "SELECT * FROM curriculum_enrollments WHERE id=?", (enrollment_id,)
    ).fetchone()
    return dict(row) if row else None


def get_active_enrollments(conn: sqlite3.Connection, child_id: int) -> list[dict]:
    """SELECT active enrollments for child."""
    rows = conn.execute(
        "SELECT * FROM curriculum_enrollments WHERE child_id=? AND status='active'",
        (child_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_enrollment_by_subject(
    conn: sqlite3.Connection,
    child_id: int,
    subject: str,
) -> dict | None:
    """Return active enrollment for a specific subject, or None."""
    row = conn.execute(
        """
        SELECT e.* FROM curriculum_enrollments e
        JOIN curriculum_templates ct ON ct.id = e.curriculum_id
        WHERE e.child_id=? AND ct.subject=? AND e.status='active'
        ORDER BY e.started_at DESC LIMIT 1
        """,
        (child_id, subject),
    ).fetchone()
    return dict(row) if row else None


def update_enrollment_progress(
    conn: sqlite3.Connection,
    enrollment_id: int,
    current_topic_index: int,
    retry_count: int,
    status: str,
) -> None:
    """UPDATE enrollment progress fields."""
    conn.execute(
        "UPDATE curriculum_enrollments "
        "SET current_topic_index=?, retry_count=?, status=?, updated_at=? WHERE id=?",
        (current_topic_index, retry_count, status, _now(), enrollment_id),
    )
    conn.commit()


def create_curriculum_lesson(
    conn: sqlite3.Connection,
    child_id: int,
    topic_id: str,
    topic_title: str,
    subject: str,
    enrollment_id: int | None,
    sequence_number: int,
) -> int:
    """Create a lesson record for a curriculum topic. enrollment_id may be None for pick-a-topic mode."""
    cursor = conn.execute(
        "INSERT INTO lessons "
        "(child_id, mode, topic_id, topic_title, subject, enrollment_id, sequence_number, status) "
        "VALUES (?, 'curriculum', ?, ?, ?, ?, ?, 'pending')",
        (child_id, topic_id, topic_title, subject, enrollment_id, sequence_number),
    )
    conn.commit()
    return cursor.lastrowid


def get_free_lessons(conn: sqlite3.Connection, child_id: int) -> list[dict]:
    """Get all on_demand (free) lessons for a child, newest first."""
    rows = conn.execute(
        """
        SELECT l.id, l.topic_title, l.subject, l.status, l.content_url, l.print_url, l.worksheet_url,
               l.created_at, lr.stars, lr.correct_answers
        FROM lessons l
        LEFT JOIN lesson_results lr ON lr.lesson_id = l.id
        WHERE l.child_id = ? AND l.mode = 'on_demand'
        ORDER BY l.created_at DESC
        """,
        (child_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_completed_topic_ids(conn: sqlite3.Connection, child_id: int) -> set[str]:
    """Return set of topic_ids where the child has completed at least one lesson (has a result)."""
    rows = conn.execute(
        """
        SELECT DISTINCT l.topic_id
        FROM lessons l
        JOIN lesson_results lr ON lr.lesson_id = l.id
        WHERE l.child_id = ? AND l.topic_id IS NOT NULL
        """,
        (child_id,),
    ).fetchall()
    return {row[0] for row in rows if row[0]}


def get_program_progress(conn: sqlite3.Connection, child_id: int, grade: int) -> list[dict]:
    """Return per-subject progress: [{subject, title, total_topics, completed_topics, percent}]."""
    import json as _json
    completed_ids = get_completed_topic_ids(conn, child_id)

    rows = conn.execute(
        "SELECT * FROM curriculum_templates WHERE grade = ?", (grade,)
    ).fetchall()

    result = []
    for row in rows:
        data = _json.loads(row["topics_json"])
        all_topic_ids = [t["id"] for u in data.get("units", []) for t in u.get("topics", [])]
        total = len(all_topic_ids)
        completed = len([tid for tid in all_topic_ids if tid in completed_ids])
        percent = round(completed / total * 100) if total > 0 else 0
        result.append({
            "curriculum_id": row["id"],
            "subject": row["subject"],
            "title": row["title"],
            "total_topics": total,
            "completed_topics": completed,
            "percent": percent,
        })
    return result


def get_curriculum_with_progress(
    conn: sqlite3.Connection, child_id: int, subject: str, grade: int
) -> dict | None:
    """Return full curriculum with topic completion status for a child."""
    import json as _json
    row = conn.execute(
        "SELECT * FROM curriculum_templates WHERE subject = ? AND grade = ?",
        (subject, grade),
    ).fetchone()
    if not row:
        return None

    data = _json.loads(row["topics_json"])
    completed_ids = get_completed_topic_ids(conn, child_id)

    # Annotate each topic with status
    units = []
    for unit in data.get("units", []):
        topics = []
        for topic in unit.get("topics", []):
            topics.append({
                "id": topic["id"],
                "title": topic["title"],
                "completed": topic["id"] in completed_ids,
            })
        unit_completed = sum(1 for t in topics if t["completed"])
        units.append({
            "id": unit["id"],
            "title": unit["title"],
            "topics": topics,
            "total": len(topics),
            "completed": unit_completed,
        })

    total_topics = sum(u["total"] for u in units)
    total_completed = sum(u["completed"] for u in units)

    return {
        "curriculum_id": row["id"],
        "subject": row["subject"],
        "grade": row["grade"],
        "title": row["title"],
        "units": units,
        "total_topics": total_topics,
        "completed_topics": total_completed,
        "percent": round(total_completed / total_topics * 100) if total_topics > 0 else 0,
    }


def get_last_lesson_result_for_enrollment_topic(
    conn: sqlite3.Connection,
    enrollment_id: int,
    topic_index: int,
) -> dict | None:
    """Get the most recent lesson result for a specific topic index in an enrollment."""
    row = conn.execute(
        """
        SELECT lr.* FROM lesson_results lr
        JOIN lessons l ON l.id = lr.lesson_id
        WHERE l.enrollment_id=? AND l.sequence_number=?
        ORDER BY lr.completed_at DESC LIMIT 1
        """,
        (enrollment_id, topic_index),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------


def _seed_chat_characters(conn: sqlite3.Connection) -> None:
    """Idempotent seed: 4 chat characters for Kidi Chat."""
    existing = conn.execute("SELECT COUNT(*) FROM chat_characters").fetchone()[0]
    if existing >= 4:
        return

    import json as _json

    chars = [
        {
            "key": "spark",
            "name_ru": "Kidi",
            "role_ru": "Универсальный друг",
            "avatar_type": "png",
            "system_prompt": "",  # filled from kid_chat.py
            "greeting_ru": "Привет! Я Kidi!",
            "greeting_sub_ru": "Спроси меня о чём угодно — про космос, динозавров, домашку или просто поболтаем.",
            "suggestions_json": _json.dumps([
                {"ico": "\u2728", "label": "Интересный факт"},
                {"ico": "\U0001f4da", "label": "Помощь с уроками"},
                {"ico": "\U0001f4d6", "label": "Придумай историю"},
                {"ico": "\U0001f914", "label": "А почему\u2026?"},
            ]),
            "accent_color": "spark",
            "is_free": 1,
            "sort_order": 0,
        },
        {
            "key": "owl",
            "name_ru": "Профессор Сова",
            "role_ru": "Учитель",
            "avatar_type": "svg",
            "system_prompt": "",
            "greeting_ru": "Добро пожаловать в класс!",
            "greeting_sub_ru": "Какой предмет сегодня разберём? Я объясню по шагам и проверю, что всё понятно.",
            "suggestions_json": _json.dumps([
                {"ico": "\U0001f522", "label": "Объясни тему"},
                {"ico": "\U0001f9ea", "label": "Проверь мои знания"},
                {"ico": "\U0001f4d0", "label": "Помоги с задачей"},
                {"ico": "\U0001f9e0", "label": "Расскажи опыт"},
            ]),
            "accent_color": "owl",
            "is_free": 0,
            "sort_order": 1,
        },
        {
            "key": "captain",
            "name_ru": "Капитан Сказка",
            "role_ru": "Рассказчик",
            "avatar_type": "svg",
            "system_prompt": "",
            "greeting_ru": "Ого, новый путешественник!",
            "greeting_sub_ru": "Какую историю придумаем сегодня? Можешь стать главным героем — расскажи, где хочешь побывать.",
            "suggestions_json": _json.dumps([
                {"ico": "\U0001f3f4\u200d\u2620\ufe0f", "label": "Придумай сказку"},
                {"ico": "\U0001fa90", "label": "Продолжи историю"},
                {"ico": "\U0001f5dd\ufe0f", "label": "Загадка"},
                {"ico": "\U0001f3ad", "label": "Сыграем роли"},
            ]),
            "accent_color": "captain",
            "is_free": 0,
            "sort_order": 2,
        },
        {
            "key": "pixie",
            "name_ru": "Друг Пикси",
            "role_ru": "Ровесник",
            "avatar_type": "svg",
            "system_prompt": "",
            "greeting_ru": "Привет-привет!",
            "greeting_sub_ru": "Что нового расскажешь? У меня тут пара секретов и одна несмешная шутка — выбирай!",
            "suggestions_json": _json.dumps([
                {"ico": "\U0001f4ac", "label": "Что нового?"},
                {"ico": "\U0001f602", "label": "Расскажи шутку"},
                {"ico": "\U0001f3b2", "label": "Давай играть"},
                {"ico": "\u2728", "label": "Угадай настроение"},
            ]),
            "accent_color": "pixie",
            "is_free": 0,
            "sort_order": 3,
        },
    ]

    for c in chars:
        conn.execute(
            "INSERT OR IGNORE INTO chat_characters "
            "(key, name_ru, role_ru, avatar_type, system_prompt, greeting_ru, greeting_sub_ru, "
            "suggestions_json, accent_color, is_free, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                c["key"], c["name_ru"], c["role_ru"], c["avatar_type"],
                c["system_prompt"], c["greeting_ru"], c["greeting_sub_ru"],
                c["suggestions_json"], c["accent_color"], c["is_free"], c["sort_order"],
            ),
        )
    conn.commit()

    # Rename Spark → Kidi for existing databases
    conn.execute(
        "UPDATE chat_characters SET name_ru='Kidi', greeting_ru='Привет! Я Kidi!' "
        "WHERE key='spark' AND name_ru != 'Kidi'"
    )
    conn.commit()


def _seed_math_grade1(conn: sqlite3.Connection) -> None:
    """Idempotent seed: Math Grade 1, 12 themes x 5 lessons = 60 rows.
    Checks if the first theme title matches; if not, clears and reseeds."""
    existing = conn.execute(
        "SELECT COUNT(*) FROM curriculum_topics WHERE subject='math' AND grade=1"
    ).fetchone()[0]
    if existing > 0:
        # Check if seed data matches current version
        first = conn.execute(
            "SELECT title_ru FROM curriculum_topics WHERE subject='math' AND grade=1 AND theme_order=1"
        ).fetchone()
        if first and first["title_ru"] == "Счёт до 10":
            return  # Already correct version
        # Old seed data — clear and reseed
        old_topics = conn.execute(
            "SELECT id FROM curriculum_topics WHERE subject='math' AND grade=1"
        ).fetchall()
        old_ids = [r["id"] for r in old_topics]
        if old_ids:
            placeholders = ",".join("?" * len(old_ids))
            # Delete progress, lessons, then topics
            conn.execute(
                f"DELETE FROM child_lesson_progress WHERE curriculum_lesson_id IN "
                f"(SELECT id FROM curriculum_lessons WHERE topic_id IN ({placeholders}))",
                old_ids,
            )
            conn.execute(
                f"DELETE FROM curriculum_lessons WHERE topic_id IN ({placeholders})",
                old_ids,
            )
            conn.execute(
                f"DELETE FROM curriculum_topics WHERE id IN ({placeholders})",
                old_ids,
            )
            conn.commit()

    themes = [
        (1, "Счёт до 10", "🔢"),
        (2, "Сравнение чисел", "⚖️"),
        (3, "Сложение до 10", "➕"),
        (4, "Вычитание до 10", "➖"),
        (5, "Состав числа", "🧩"),
        (6, "Числа до 20", "🔢"),
        (7, "Сложение с переходом через 10", "➕"),
        (8, "Вычитание с переходом через 10", "➖"),
        (9, "Задачи на сложение", "📝"),
        (10, "Задачи на вычитание", "📝"),
        (11, "Геометрические фигуры", "📐"),
        (12, "Измерение длины", "📏"),
    ]

    lessons_by_theme = {
        1: ["Считаем предметы", "Числа 1, 2, 3", "Числа 4, 5",
            "Числа 6, 7, 8", "Числа 9, 10"],
        2: ["Больше и меньше", "Знаки > < =", "Сравниваем числа до 5",
            "Сравниваем числа до 10", "Соседи числа"],
        3: ["Что такое сложение", "Прибавляем 1 и 2", "Прибавляем 3 и 4",
            "Прибавляем 5", "Считаем быстро"],
        4: ["Что такое вычитание", "Вычитаем 1 и 2", "Вычитаем 3 и 4",
            "Вычитаем 5", "Считаем быстро"],
        5: ["Состав чисел 2, 3, 4", "Состав чисел 5, 6", "Состав чисел 7, 8",
            "Состав чисел 9, 10", "Тренировка"],
        6: ["Десяток", "Числа 11-15", "Числа 16-20",
            "Сравниваем числа до 20", "Считаем до 20"],
        7: ["Как прибавлять через 10", "9 + 2, 9 + 3, 9 + 4", "8 + 3, 8 + 4, 8 + 5",
            "7 + 4, 7 + 5, 6 + 5", "Тренировка"],
        8: ["Как вычитать через 10", "11 − 2, 11 − 3", "12 − 3, 12 − 4",
            "13 − 4, 14 − 5", "Тренировка"],
        9: ["Что такое задача", "Задачи «всего», «вместе»", "Задачи «на больше»",
            "Рисуем схему", "Решаем задачи"],
        10: ["Задачи «осталось»", "Задачи «на меньше»", "Задачи на сравнение",
             "Рисуем схему", "Решаем задачи"],
        11: ["Точка, линия, отрезок", "Треугольник", "Квадрат и прямоугольник",
             "Круг и овал", "Ищем фигуры вокруг"],
        12: ["Сантиметр", "Измеряем отрезки", "Чертим отрезки",
             "Сравниваем длины", "Итоговый урок"],
    }

    for theme_order, title_ru, icon in themes:
        conn.execute(
            "INSERT INTO curriculum_topics (subject, grade, theme_order, title_ru, icon) "
            "VALUES ('math', 1, ?, ?, ?)",
            (theme_order, title_ru, icon),
        )
    conn.commit()

    # Get topic IDs
    topics = conn.execute(
        "SELECT id, theme_order FROM curriculum_topics WHERE subject='math' AND grade=1 "
        "ORDER BY theme_order"
    ).fetchall()

    for topic in topics:
        lesson_titles = lessons_by_theme[topic["theme_order"]]
        for lesson_order, title in enumerate(lesson_titles, 1):
            conn.execute(
                "INSERT INTO curriculum_lessons (topic_id, lesson_order, title_ru) "
                "VALUES (?, ?, ?)",
                (topic["id"], lesson_order, title),
            )
    conn.commit()


# ---------------------------------------------------------------------------
# Curriculum Topics helpers
# ---------------------------------------------------------------------------

def get_topics_by_subject_grade(conn: sqlite3.Connection, subject: str, grade: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM curriculum_topics WHERE subject=? AND grade=? ORDER BY theme_order",
        (subject, grade),
    ).fetchall()
    return [dict(r) for r in rows]


def get_topic_by_id(conn: sqlite3.Connection, topic_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM curriculum_topics WHERE id=?", (topic_id,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Curriculum Lessons helpers
# ---------------------------------------------------------------------------

def get_lessons_by_topic_id(conn: sqlite3.Connection, topic_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM curriculum_lessons WHERE topic_id=? ORDER BY lesson_order",
        (topic_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_curriculum_lesson_by_id(conn: sqlite3.Connection, cl_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM curriculum_lessons WHERE id=?", (cl_id,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Child Lesson Progress helpers
# ---------------------------------------------------------------------------

def initialize_child_progress(conn: sqlite3.Connection, child_id: int, subject: str, grade: int) -> int:
    """
    Create child_lesson_progress rows for ALL curriculum lessons in subject+grade.
    First lesson of first topic = 'available', rest = 'locked'.
    Idempotent: returns 0 if already initialized.
    """
    # Check if already initialized
    existing = conn.execute(
        """SELECT COUNT(*) FROM child_lesson_progress clp
           JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE clp.child_id = ? AND ct.subject = ? AND ct.grade = ?""",
        (child_id, subject, grade),
    ).fetchone()[0]
    if existing > 0:
        return 0

    topics = conn.execute(
        "SELECT id FROM curriculum_topics WHERE subject=? AND grade=? ORDER BY theme_order",
        (subject, grade),
    ).fetchall()

    count = 0
    first = True
    for topic in topics:
        lessons = conn.execute(
            "SELECT id FROM curriculum_lessons WHERE topic_id=? ORDER BY lesson_order",
            (topic["id"],),
        ).fetchall()
        for lesson in lessons:
            status = "available" if first else "locked"
            first = False
            conn.execute(
                "INSERT INTO child_lesson_progress (child_id, curriculum_lesson_id, status) "
                "VALUES (?, ?, ?)",
                (child_id, lesson["id"], status),
            )
            count += 1
    conn.commit()
    return count


def get_child_progress_for_subject(conn: sqlite3.Connection, child_id: int, subject: str, grade: int) -> list[dict]:
    rows = conn.execute(
        """SELECT clp.*, cl.lesson_order, cl.title_ru, cl.prompt_hint,
                  ct.id AS topic_id, ct.theme_order, ct.title_ru AS topic_title, ct.icon,
                  l.status AS lesson_status, l.icon AS lesson_icon, l.content_url
           FROM child_lesson_progress clp
           JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           LEFT JOIN lessons l ON l.id = clp.lesson_id
           WHERE clp.child_id = ? AND ct.subject = ? AND ct.grade = ?
           ORDER BY ct.theme_order, cl.lesson_order""",
        (child_id, subject, grade),
    ).fetchall()
    return [dict(r) for r in rows]


def update_lesson_progress_status(
    conn: sqlite3.Connection,
    progress_id: int,
    status: str,
    lesson_id: int | None = None,
    stars_earned: int = 0,
) -> None:
    completed_at = _now() if status == "completed" else None
    conn.execute(
        "UPDATE child_lesson_progress SET status=?, lesson_id=?, stars_earned=?, completed_at=? WHERE id=?",
        (status, lesson_id, stars_earned, completed_at, progress_id),
    )
    conn.commit()


def bulk_complete_lessons(
    conn: sqlite3.Connection,
    child_id: int,
    subject: str,
    grade: int,
    up_to_theme_order: int,
) -> None:
    """Mark ALL lessons in themes 1..up_to_theme_order as 'completed', then unlock next."""
    now = _now()
    conn.execute(
        """UPDATE child_lesson_progress SET status='completed', completed_at=?
           WHERE child_id=? AND curriculum_lesson_id IN (
               SELECT cl.id FROM curriculum_lessons cl
               JOIN curriculum_topics ct ON ct.id = cl.topic_id
               WHERE ct.subject=? AND ct.grade=? AND ct.theme_order <= ?
           ) AND status != 'completed'""",
        (now, child_id, subject, grade, up_to_theme_order),
    )

    # Unlock first lesson of next topic
    next_topic = conn.execute(
        "SELECT id FROM curriculum_topics WHERE subject=? AND grade=? AND theme_order=?",
        (subject, grade, up_to_theme_order + 1),
    ).fetchone()
    if next_topic:
        first_lesson = conn.execute(
            "SELECT id FROM curriculum_lessons WHERE topic_id=? AND lesson_order=1",
            (next_topic["id"],),
        ).fetchone()
        if first_lesson:
            conn.execute(
                "UPDATE child_lesson_progress SET status='available' "
                "WHERE child_id=? AND curriculum_lesson_id=? AND status='locked'",
                (child_id, first_lesson["id"]),
            )
    conn.commit()


def get_active_skip_test(conn: sqlite3.Connection, child_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM child_lesson_progress WHERE child_id=? AND status='test' LIMIT 1",
        (child_id,),
    ).fetchone()
    return dict(row) if row else None


def get_progress_stats(conn: sqlite3.Connection, child_id: int, subject: str, grade: int) -> dict:
    row = conn.execute(
        """SELECT
               COUNT(*) AS total_lessons,
               SUM(CASE WHEN clp.status='completed' THEN 1 ELSE 0 END) AS completed_lessons,
               SUM(clp.stars_earned) AS total_stars
           FROM child_lesson_progress clp
           JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE clp.child_id=? AND ct.subject=? AND ct.grade=?""",
        (child_id, subject, grade),
    ).fetchone()
    return {
        "total_lessons": row["total_lessons"] or 0,
        "completed_lessons": row["completed_lessons"] or 0,
        "total_stars": row["total_stars"] or 0,
    }


# ---------------------------------------------------------------------------
# Stars helpers
# ---------------------------------------------------------------------------

def add_stars(conn: sqlite3.Connection, child_id: int, delta: int) -> None:
    conn.execute("UPDATE children SET stars = stars + ? WHERE id = ?", (delta, child_id))
    conn.commit()


def get_child_stars(conn: sqlite3.Connection, child_id: int) -> int:
    row = conn.execute("SELECT stars FROM children WHERE id=?", (child_id,)).fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Universe & Character helpers
# ---------------------------------------------------------------------------

def update_child_universe(
    conn: sqlite3.Connection,
    child_id: int,
    interests: str,
    universe_description: str,
    character_prompt: str,
) -> None:
    conn.execute(
        "UPDATE children SET interests=?, universe_description=?, character_prompt=?, updated_at=? WHERE id=?",
        (interests, universe_description, character_prompt, _now(), child_id),
    )
    conn.commit()


def update_child_character_image(conn: sqlite3.Connection, child_id: int, image_url: str) -> None:
    conn.execute(
        "UPDATE children SET character_image_url=?, updated_at=? WHERE id=?",
        (image_url, _now(), child_id),
    )
    conn.commit()


def update_child_character_name(conn: sqlite3.Connection, child_id: int, character_name: str) -> None:
    conn.execute(
        "UPDATE children SET character_name=?, character_onboarded=1, updated_at=? WHERE id=?",
        (character_name, _now(), child_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Shop operations
# ---------------------------------------------------------------------------

def create_shop_items(conn: sqlite3.Connection, child_id: int, items: list[dict]) -> list[int]:
    """Bulk insert shop items for a child. Each dict must have: category, title_ru, description_ru, emoji, price_stars."""
    ids = []
    for item in items:
        cursor = conn.execute(
            "INSERT INTO shop_items (child_id, category, title_ru, description_ru, emoji, price_stars) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (child_id, item["category"], item["title_ru"], item.get("description_ru", ""),
             item.get("emoji", ""), item["price_stars"]),
        )
        ids.append(cursor.lastrowid)
    conn.commit()
    return ids


def get_shop_items_for_child(conn: sqlite3.Connection, child_id: int) -> list[dict]:
    """Get all shop items for a child with purchase status."""
    rows = conn.execute(
        """SELECT si.*, ci.id AS purchase_id, ci.equipped
           FROM shop_items si
           LEFT JOIN child_items ci ON ci.item_id = si.id AND ci.child_id = si.child_id
           WHERE si.child_id = ?
           ORDER BY si.category, si.price_stars""",
        (child_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def purchase_item(conn: sqlite3.Connection, child_id: int, item_id: int) -> bool:
    """Purchase a shop item. Deducts stars and creates child_items record.
    Returns True if successful, False if not enough stars or already purchased."""
    # Check if already purchased
    existing = conn.execute(
        "SELECT id FROM child_items WHERE child_id=? AND item_id=?",
        (child_id, item_id),
    ).fetchone()
    if existing:
        return False

    # Get item price
    item = conn.execute("SELECT * FROM shop_items WHERE id=? AND child_id=?", (item_id, child_id)).fetchone()
    if not item:
        return False

    # Check stars
    child = conn.execute("SELECT stars FROM children WHERE id=?", (child_id,)).fetchone()
    if not child or child["stars"] < item["price_stars"]:
        return False

    # Deduct stars and create purchase
    conn.execute("UPDATE children SET stars = stars - ? WHERE id=?", (item["price_stars"], child_id))
    conn.execute(
        "INSERT INTO child_items (child_id, item_id, equipped) VALUES (?, ?, 1)",
        (child_id, item_id),
    )
    conn.commit()
    return True


def get_equipped_items(conn: sqlite3.Connection, child_id: int) -> list[dict]:
    """Get all equipped items for a child."""
    rows = conn.execute(
        """SELECT si.* FROM shop_items si
           JOIN child_items ci ON ci.item_id = si.id
           WHERE ci.child_id = ? AND ci.equipped = 1
           ORDER BY si.category""",
        (child_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def toggle_equip_item(conn: sqlite3.Connection, child_id: int, item_id: int, equipped: bool) -> bool:
    """Toggle equipped status. Returns True if updated."""
    cursor = conn.execute(
        "UPDATE child_items SET equipped=? WHERE child_id=? AND item_id=?",
        (1 if equipped else 0, child_id, item_id),
    )
    conn.commit()
    return cursor.rowcount == 1


# ---------------------------------------------------------------------------
# Kid Chat operations
# ---------------------------------------------------------------------------

def create_kid_chat(
    conn: sqlite3.Connection,
    child_id: int,
    character_key: str = "spark",
    title: str = "Kidi",
) -> int:
    cursor = conn.execute(
        "INSERT INTO kid_chats (child_id, character_key, title, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (child_id, character_key, title, _now(), _now()),
    )
    conn.commit()
    return cursor.lastrowid


def get_or_create_spark_chat(conn: sqlite3.Connection, child_id: int) -> dict:
    """Get existing Spark chat for child, or create one. Returns chat dict."""
    return get_or_create_character_chat(conn, child_id, "spark")


def get_or_create_character_chat(
    conn: sqlite3.Connection, child_id: int, character_key: str = "spark"
) -> dict:
    """Get existing chat for child+character, or create one. Returns chat dict."""
    row = conn.execute(
        "SELECT * FROM kid_chats WHERE child_id = ? AND character_key = ? "
        "ORDER BY updated_at DESC LIMIT 1",
        (child_id, character_key),
    ).fetchone()
    if row:
        return dict(row)
    # Look up character name for title
    char_row = conn.execute(
        "SELECT name_ru FROM chat_characters WHERE key = ?", (character_key,)
    ).fetchone()
    title = char_row["name_ru"] if char_row else character_key.capitalize()
    chat_id = create_kid_chat(conn, child_id, character_key, title)
    return dict(conn.execute("SELECT * FROM kid_chats WHERE id = ?", (chat_id,)).fetchone())


def get_chat_characters(conn: sqlite3.Connection) -> list[dict]:
    """Return all chat characters sorted by sort_order."""
    rows = conn.execute(
        "SELECT * FROM chat_characters ORDER BY sort_order"
    ).fetchall()
    return [dict(r) for r in rows]


def get_chat_character(conn: sqlite3.Connection, key: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM chat_characters WHERE key = ?", (key,)
    ).fetchone()
    return dict(row) if row else None


def get_kid_chat(conn: sqlite3.Connection, chat_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM kid_chats WHERE id = ?", (chat_id,)).fetchone()
    return dict(row) if row else None


def get_kid_chats_by_child(conn: sqlite3.Connection, child_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM kid_chats WHERE child_id = ? ORDER BY updated_at DESC",
        (child_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_kid_chat_timestamp(conn: sqlite3.Connection, chat_id: int) -> None:
    conn.execute("UPDATE kid_chats SET updated_at = ? WHERE id = ?", (_now(), chat_id))
    conn.commit()


def delete_kid_chat(conn: sqlite3.Connection, chat_id: int) -> bool:
    cursor = conn.execute("DELETE FROM kid_chats WHERE id = ?", (chat_id,))
    conn.commit()
    return cursor.rowcount == 1


def clear_kid_chat_messages(conn: sqlite3.Connection, chat_id: int) -> None:
    """Delete all messages in a chat (used for 'new conversation')."""
    conn.execute("DELETE FROM kid_chat_messages WHERE chat_id = ?", (chat_id,))
    conn.commit()


def add_kid_chat_message(
    conn: sqlite3.Connection,
    chat_id: int,
    role: str,
    content: str,
    image_url: str | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO kid_chat_messages (chat_id, role, content, image_url, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (chat_id, role, content, image_url, _now()),
    )
    conn.commit()
    # Trim to keep only last 30 messages
    _trim_chat_messages(conn, chat_id, max_messages=30)
    return cursor.lastrowid


def _trim_chat_messages(conn: sqlite3.Connection, chat_id: int, max_messages: int = 30) -> None:
    """Keep only the last N messages in a chat, delete older ones."""
    count = conn.execute(
        "SELECT COUNT(*) FROM kid_chat_messages WHERE chat_id = ?", (chat_id,)
    ).fetchone()[0]
    if count <= max_messages:
        return
    conn.execute(
        "DELETE FROM kid_chat_messages WHERE id IN ("
        "  SELECT id FROM kid_chat_messages WHERE chat_id = ? "
        "  ORDER BY created_at ASC, id ASC LIMIT ?"
        ")",
        (chat_id, count - max_messages),
    )
    conn.commit()


def get_kid_chat_messages(
    conn: sqlite3.Connection,
    chat_id: int,
    limit: int = 30,
) -> list[dict]:
    """Get last N messages for a chat, ordered chronologically."""
    rows = conn.execute(
        "SELECT * FROM kid_chat_messages WHERE chat_id = ? "
        "ORDER BY created_at DESC, id DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    # Reverse to get chronological order
    return [dict(r) for r in reversed(rows)]


def count_daily_messages(conn: sqlite3.Connection, child_id: int, today_str: str) -> int:
    """Count user messages sent by any child of the same parent today."""
    # Get parent_id
    child = conn.execute("SELECT parent_id FROM children WHERE id = ?", (child_id,)).fetchone()
    if not child:
        return 0
    parent_id = child[0]
    # Count messages from all children of this parent
    row = conn.execute(
        """SELECT COUNT(*) FROM kid_chat_messages kcm
           JOIN kid_chats kc ON kc.id = kcm.chat_id
           JOIN children c ON c.id = kc.child_id
           WHERE c.parent_id = ? AND kcm.role = 'user'
           AND kcm.created_at >= ? AND kcm.created_at < ?""",
        (parent_id, today_str + "T00:00:00", today_str + "T23:59:59.999999"),
    ).fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Chat Subscription operations
# ---------------------------------------------------------------------------

def create_chat_subscription(
    conn: sqlite3.Connection,
    user_id: int,
    started_at: str,
    expires_at: str,
    images_remaining: int = 30,
    amount_rub: float = 0,
    payment_id: str | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO chat_subscriptions "
        "(user_id, started_at, expires_at, images_remaining, amount_rub, payment_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, started_at, expires_at, images_remaining, amount_rub, payment_id, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def get_active_chat_subscription(conn: sqlite3.Connection, user_id: int) -> dict | None:
    """Get active subscription (expires_at > now)."""
    row = conn.execute(
        "SELECT * FROM chat_subscriptions WHERE user_id = ? AND expires_at > ? "
        "ORDER BY expires_at DESC LIMIT 1",
        (user_id, _now()),
    ).fetchone()
    return dict(row) if row else None


def use_chat_image(conn: sqlite3.Connection, user_id: int) -> bool:
    """Decrement images_remaining for active subscription. Returns True if had remaining."""
    sub = get_active_chat_subscription(conn, user_id)
    if not sub or sub.get("images_remaining", 0) <= 0:
        return False
    conn.execute(
        "UPDATE chat_subscriptions SET images_remaining = images_remaining - 1 WHERE id = ?",
        (sub["id"],),
    )
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Chat Reports
# ---------------------------------------------------------------------------


def create_chat_report(
    conn: sqlite3.Connection,
    child_id: int,
    date: str,
    summary: str,
    topics_json: str = "[]",
    message_count: int = 0,
    character_key: str = "spark",
) -> int:
    cursor = conn.execute(
        "INSERT INTO chat_reports (child_id, date, summary, topics_json, message_count, character_key, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (child_id, date, summary, topics_json, message_count, character_key, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def get_chat_reports(conn: sqlite3.Connection, child_id: int, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM chat_reports WHERE child_id = ? ORDER BY date DESC LIMIT ?",
        (child_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Methodologist Cache operations
# ---------------------------------------------------------------------------

def get_cached_methodologist(conn: sqlite3.Connection, subject: str, grade: int, topic: str) -> str | None:
    """Return cached methodologist output or None."""
    row = conn.execute(
        "SELECT output FROM methodologist_cache WHERE subject = ? AND grade = ? AND topic = ?",
        (subject, grade, topic),
    ).fetchone()
    return row[0] if row else None


def save_methodologist_cache(conn: sqlite3.Connection, subject: str, grade: int, topic: str, output: str) -> None:
    """Save methodologist output to cache."""
    conn.execute(
        "INSERT OR REPLACE INTO methodologist_cache (subject, grade, topic, output, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (subject, grade, topic, output, _now()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Topic Image Cache operations
# ---------------------------------------------------------------------------

def get_topic_image(conn: sqlite3.Connection, subject: str, grade: int, topic: str) -> str | None:
    """Return cached image filename for a topic or None."""
    row = conn.execute(
        "SELECT image_filename FROM topic_images WHERE subject = ? AND grade = ? AND topic = ?",
        (subject, grade, topic),
    ).fetchone()
    return row[0] if row else None


def save_topic_image(conn: sqlite3.Connection, subject: str, grade: int, topic: str, image_filename: str) -> None:
    """Save topic image filename to cache."""
    conn.execute(
        "INSERT OR REPLACE INTO topic_images (subject, grade, topic, image_filename, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (subject, grade, topic, image_filename, _now()),
    )
    conn.commit()
