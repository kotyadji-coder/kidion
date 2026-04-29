"""
callbacks.py — HMAC verification and callback handling from bots.
"""

import hashlib
import hmac
import os
import sqlite3

from db import (
    get_generation,
    insert_transaction,
    update_crystals,
    update_generation,
)


def generate_callback_hmac(gen_id: int, secret: str) -> str:
    """Compute HMAC-SHA256 hex digest for a given gen_id."""
    return hmac.new(
        secret.encode(),
        str(gen_id).encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_callback_hmac(gen_id: int, provided_secret: str, secret: str) -> bool:
    """Return True if provided_secret matches the expected HMAC for gen_id."""
    if not secret:
        return False
    expected = generate_callback_hmac(gen_id, secret)
    return hmac.compare_digest(expected, provided_secret)


def handle_callback(conn: sqlite3.Connection, gen_id: int, body: dict) -> None:
    """
    Process a callback from a bot.

    body fields:
      - status: "done" | "error"
      - user_id: int
      - tale_url: str (optional, present when status == "done")
    """
    generation = get_generation(conn, gen_id)
    if generation is None:
        return

    # Idempotency: only process if still pending
    if generation["status"] != "pending":
        return

    status = body.get("status")
    if status == "done":
        result_url = body.get("tale_url")
        update_generation(conn, gen_id, "done", result_url)

        user_id = generation["user_id"]
        success = update_crystals(conn, user_id, -20)
        if success:
            insert_transaction(conn, user_id, -20, "generation_cost")

    elif status == "error":
        update_generation(conn, gen_id, "error")
