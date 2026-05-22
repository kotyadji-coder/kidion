"""
payments.py — Prodamus payment integration.

Flow:
1. Server builds a payment URL → redirects user to edtale.payform.ru
2. User pays → Prodamus POSTs webhook to /api/payment/webhook
3. We verify HMAC-SHA256 signature and credit crystals.
"""

import hashlib
import hmac
import json
import logging
import os
import sqlite3
from urllib.parse import urlencode

from db import (
    create_payment,
    get_payment_by_yk_id,
    insert_transaction,
    update_crystals,
    update_payment_status,
    count_successful_payments,
)
from referral import process_payment_referral

PACKAGES = {
    "60_60": {"crystals": 60, "price_rub": 60},
    "360_320": {"crystals": 360, "price_rub": 320},
    "600_490": {"crystals": 600, "price_rub": 490},
    "1000_800": {"crystals": 1000, "price_rub": 800},
}

PRODAMUS_DOMAIN = os.environ.get("PRODAMUS_DOMAIN", "edtale.payform.ru")
PRODAMUS_SECRET = os.environ.get("PRODAMUS_SECRET_KEY", "")


def _get_secret() -> str:
    return os.environ.get("PRODAMUS_SECRET_KEY", PRODAMUS_SECRET)


def create_prodamus_payment(
    user_id: int,
    package_id: str,
    return_url: str,
    customer_email: str = "",
) -> dict:
    """
    Build a Prodamus payment URL and return dict with:
      - order_id: str (unique, stored as yookassa_payment_id for DB compat)
      - confirmation_url: str
      - amount_rub: float
      - crystals: int
    """
    package = PACKAGES[package_id]
    order_id = f"kidion_{user_id}_{package_id}_{os.urandom(8).hex()}"

    domain = os.environ.get("PRODAMUS_DOMAIN", PRODAMUS_DOMAIN)

    params = {
        "do": "pay",
        "products[0][name]": f"Kidion: {package['crystals']} кристаллов",
        "products[0][price]": str(package["price_rub"]),
        "products[0][quantity]": "1",
        "order_id": order_id,
        "urlSuccess": return_url,
        "urlReturn": return_url,
    }
    if customer_email:
        params["customer_email"] = customer_email

    confirmation_url = f"https://{domain}/?{urlencode(params)}"

    return {
        "order_id": order_id,
        "confirmation_url": confirmation_url,
        "amount_rub": package["price_rub"],
        "crystals": package["crystals"],
    }


def verify_prodamus_signature(data: dict, signature: str) -> bool:
    """
    Verify HMAC-SHA256 signature from Prodamus webhook.

    Prodamus signs the webhook body: HMAC-SHA256 of JSON-encoded sorted data
    using the secret key.
    """
    secret = _get_secret()
    if not secret:
        logging.warning("PRODAMUS_SECRET_KEY not set, skipping signature check")
        return True

    # Remove 'sign' from data before verification
    check_data = {k: v for k, v in data.items() if k != "sign"}

    # Sort keys and build canonical JSON string
    sorted_data = dict(sorted(check_data.items()))
    message = json.dumps(sorted_data, ensure_ascii=False, separators=(",", ":"))

    expected = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def create_prodamus_subscription_payment(
    user_id: int,
    return_url: str,
    price_rub: int = 500,
    customer_email: str = "",
) -> dict:
    """
    Build a Prodamus payment URL for chat subscription.
    Returns dict with order_id, confirmation_url, amount_rub.
    """
    order_id = f"kidion_sub_{user_id}_{os.urandom(8).hex()}"
    domain = os.environ.get("PRODAMUS_DOMAIN", PRODAMUS_DOMAIN)

    params = {
        "do": "pay",
        "products[0][name]": "Kidion: подписка Киди Pro (1 месяц)",
        "products[0][price]": str(price_rub),
        "products[0][quantity]": "1",
        "order_id": order_id,
        "urlSuccess": return_url,
        "urlReturn": return_url,
    }
    if customer_email:
        params["customer_email"] = customer_email

    confirmation_url = f"https://{domain}/?{urlencode(params)}"

    return {
        "order_id": order_id,
        "confirmation_url": confirmation_url,
        "amount_rub": price_rub,
    }


def handle_webhook(conn: sqlite3.Connection, event_body: dict) -> None:
    """
    Process a Prodamus webhook event.
    Handles crystal packages and chat subscriptions.
    """
    # Verify signature
    signature = event_body.get("sign", "")
    if not verify_prodamus_signature(event_body, signature):
        logging.warning("Invalid Prodamus webhook signature")
        return

    order_id = event_body.get("order_id", "")
    payment_status = event_body.get("payment_status", "")

    if not order_id:
        return

    if payment_status != "success":
        return

    # Subscription payments (order_id starts with "kidion_sub_")
    if order_id.startswith("kidion_sub_"):
        _handle_subscription_webhook(conn, order_id)
        return

    # Crystal package payments
    payment = get_payment_by_yk_id(conn, order_id)
    if payment is None:
        return

    # Idempotency: only process pending payments
    if payment["status"] != "pending":
        return

    user_id = payment["user_id"]
    crystals = payment["crystals"]
    amount_rub = payment["amount_rub"]

    # Credit crystals
    update_crystals(conn, user_id, crystals)
    insert_transaction(conn, user_id, crystals, "payment")

    # Mark payment as succeeded
    update_payment_status(conn, payment["id"], "succeeded")

    # Process referral bonus (only on first payment)
    process_payment_referral(conn, user_id, amount_rub)


def _handle_subscription_webhook(conn: sqlite3.Connection, order_id: str) -> None:
    """Activate chat subscription after successful Prodamus payment."""
    from db import create_chat_subscription, get_active_chat_subscription
    from datetime import datetime, timedelta, timezone

    # Parse user_id from order_id: "kidion_sub_{user_id}_{random}"
    parts = order_id.split("_")
    if len(parts) < 3:
        logging.warning("Invalid subscription order_id: %s", order_id)
        return

    try:
        user_id = int(parts[2])
    except (ValueError, IndexError):
        logging.warning("Cannot parse user_id from order_id: %s", order_id)
        return

    # Idempotency: check if already has active subscription
    existing = get_active_chat_subscription(conn, user_id)
    if existing:
        logging.info("User %d already has active subscription, skipping", user_id)
        return

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=30)
    create_chat_subscription(
        conn, user_id,
        started_at=now.isoformat(),
        expires_at=expires.isoformat(),
        images_remaining=30,
        amount_rub=500,
        payment_id=order_id,
    )
