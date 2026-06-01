"""
notify.py — Telegram error notifications for Kidion.

Fire-and-forget alerts via relay VPS (Telegram API blocked from Russia).
"""

import logging
import os
import threading

import httpx

logger = logging.getLogger("kidion")


def notify_error(message: str):
    """Send error alert to admin Telegram. Non-blocking, fire-and-forget."""
    bot_token = os.environ.get("NOTIFY_BOT_TOKEN")
    chat_id = os.environ.get("NOTIFY_CHAT_ID")
    relay_url = os.environ.get("NOTIFY_RELAY_URL")
    if not bot_token or not chat_id:
        logger.error("ADMIN ALERT (no Telegram configured): %s", message)
        return

    def _send():
        try:
            text = f"⚠️ Kidion Error:\n{message[:1000]}"
            if relay_url:
                httpx.post(relay_url, json={
                    "bot_token": bot_token, "chat_id": chat_id, "text": text,
                }, timeout=15)
            else:
                httpx.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                    timeout=10,
                )
        except Exception:
            logger.error("Failed to send Telegram notification: %s", message[:200])

    threading.Thread(target=_send, daemon=True).start()
