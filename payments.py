"""
payments.py — YooKassa payment integration.
"""

import os
import sqlite3
import uuid

import yookassa
from yookassa import Payment

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


def _configure_yookassa() -> None:
    yookassa.Configuration.account_id = os.environ.get("YOOKASSA_SHOP_ID", "")
    yookassa.Configuration.secret_key = os.environ.get("YOOKASSA_SECRET_KEY", "")


def create_yookassa_payment(
    user_id: int,
    package_id: str,
    return_url: str,
) -> dict:
    """
    Create a YooKassa payment and return dict with:
      - yk_payment_id: str
      - confirmation_url: str
      - amount_rub: float
      - crystals: int
    """
    _configure_yookassa()
    package = PACKAGES[package_id]
    idempotency_key = str(uuid.uuid4())

    payment = Payment.create(
        {
            "amount": {
                "value": f"{package['price_rub']:.2f}",
                "currency": "RUB",
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url,
            },
            "capture": True,
            "description": f"Kidion: {package['crystals']} кристаллов",
            "metadata": {
                "user_id": str(user_id),
                "package_id": package_id,
            },
        },
        idempotency_key,
    )

    return {
        "yk_payment_id": payment.id,
        "confirmation_url": payment.confirmation.confirmation_url,
        "amount_rub": package["price_rub"],
        "crystals": package["crystals"],
    }


def handle_webhook(conn: sqlite3.Connection, event_body: dict) -> None:
    """
    Process a YooKassa webhook event.
    Handles 'payment.succeeded': credits crystals and triggers referral processing.
    """
    event = event_body.get("event", "")
    if not event.startswith("payment."):
        return

    obj = event_body.get("object", {})
    yk_payment_id = obj.get("id")
    if not yk_payment_id:
        return

    if event != "payment.succeeded":
        return

    payment = get_payment_by_yk_id(conn, yk_payment_id)
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
