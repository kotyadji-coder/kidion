"""
daily_report.py — Send daily summary reports to Telegram.

Reports:
1. Payments & revenue (today + totals)
2. Users & activity stats
3. Latest eval run results

Runs via cron, sends through relay (Telegram blocked from Russia).
"""

import os
import sys
import json
import sqlite3
import urllib.request
from datetime import date, datetime, timedelta

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

DB_PATH = os.path.join(os.path.dirname(__file__), "kidion.db")
EVALS_DB_PATH = os.path.join(os.path.dirname(__file__), "evals_data.db")
BOT_TOKEN = os.environ.get("NOTIFY_BOT_TOKEN", "")
CHAT_ID = os.environ.get("NOTIFY_CHAT_ID", "")
RELAY_URL = os.environ.get("NOTIFY_RELAY_URL", "")


def send_telegram(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("No Telegram credentials configured")
        return
    payload = json.dumps({
        "bot_token": BOT_TOKEN,
        "chat_id": CHAT_ID,
        "text": text[:4000],
    }).encode()

    if RELAY_URL:
        url = RELAY_URL
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = json.dumps({"chat_id": CHAT_ID, "text": text[:4000]}).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"Failed to send: {e}")


def get_report():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # --- Users ---
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_children = conn.execute("SELECT COUNT(*) FROM children").fetchone()[0]
    new_users_today = conn.execute(
        "SELECT COUNT(*) FROM users WHERE date(created_at) = ?", (today,)
    ).fetchone()[0]
    new_users_yesterday = conn.execute(
        "SELECT COUNT(*) FROM users WHERE date(created_at) = ?", (yesterday,)
    ).fetchone()[0]

    # --- Payments ---
    payments_today = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(amount_rub), 0) FROM payments "
        "WHERE status='succeeded' AND date(created_at) = ?", (today,)
    ).fetchone()
    payments_yesterday = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(amount_rub), 0) FROM payments "
        "WHERE status='succeeded' AND date(created_at) = ?", (yesterday,)
    ).fetchone()
    payments_total = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(amount_rub), 0) FROM payments WHERE status='succeeded'"
    ).fetchone()

    # --- Subscriptions ---
    active_subs = conn.execute(
        "SELECT COUNT(*) FROM chat_subscriptions WHERE expires_at > datetime('now')"
    ).fetchone()[0]

    # --- Chat activity ---
    messages_today = conn.execute(
        "SELECT COUNT(*) FROM kid_chat_messages WHERE date(created_at) = ?", (today,)
    ).fetchone()[0]
    messages_yesterday = conn.execute(
        "SELECT COUNT(*) FROM kid_chat_messages WHERE date(created_at) = ?", (yesterday,)
    ).fetchone()[0]

    # --- Lessons ---
    lessons_today = conn.execute(
        "SELECT COUNT(*) FROM lesson_results WHERE date(completed_at) = ?", (today,)
    ).fetchone()[0]
    lessons_yesterday = conn.execute(
        "SELECT COUNT(*) FROM lesson_results WHERE date(completed_at) = ?", (yesterday,)
    ).fetchone()[0]

    # --- Images generated ---
    images_today = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE reason IN ('free_chat_image', 'chat_image') "
        "AND date(created_at) = ?", (today,)
    ).fetchone()[0]

    conn.close()

    # --- Evals ---
    eval_text = ""
    if os.path.exists(EVALS_DB_PATH):
        econn = sqlite3.connect(EVALS_DB_PATH)
        econn.row_factory = sqlite3.Row
        last_run = econn.execute(
            "SELECT * FROM eval_runs WHERE status='completed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if last_run:
            run_date = last_run["started_at"][:10] if last_run["started_at"] else "?"
            det = f"{last_run['avg_deterministic']:.2f}" if last_run["avg_deterministic"] else "-"
            llm = f"{last_run['avg_llm_score']:.2f}" if last_run["avg_llm_score"] else "-"
            eval_text = (
                f"\n\n--- Evals (run {run_date}) ---\n"
                f"Lessons: {last_run['lesson_count']}, Chats: {last_run['chat_count']}\n"
                f"Deterministic: {det}, LLM score: {llm}"
            )
            recs = last_run["recommendations_json"]
            if recs:
                try:
                    recs_list = json.loads(recs)
                    if recs_list:
                        eval_text += "\nRecs: " + "; ".join(recs_list[:3])
                except Exception:
                    pass
        econn.close()

    # --- Format ---
    report = (
        f"📊 Kidion Daily Report — {today}\n"
        f"\n"
        f"👥 Users: {total_users} (+{new_users_today} today, +{new_users_yesterday} yesterday)\n"
        f"👶 Children: {total_children}\n"
        f"\n"
        f"💰 Payments today: {payments_today[0]} = {payments_today[1]:.0f} ₽\n"
        f"💰 Yesterday: {payments_yesterday[0]} = {payments_yesterday[1]:.0f} ₽\n"
        f"💰 Total: {payments_total[0]} = {payments_total[1]:.0f} ₽\n"
        f"📋 Active subscriptions: {active_subs}\n"
        f"\n"
        f"💬 Messages: {messages_today} today, {messages_yesterday} yesterday\n"
        f"📚 Lessons completed: {lessons_today} today, {lessons_yesterday} yesterday\n"
        f"🎨 Images generated today: {images_today}"
        f"{eval_text}"
    )
    return report


if __name__ == "__main__":
    report = get_report()
    print(report)
    if "--send" in sys.argv:
        send_telegram(report)
        print("Sent to Telegram!")
