"""
referral.py — Referral system logic.
"""

import random
import sqlite3
import string

from db import (
    create_referral,
    get_referral_by_referred,
    get_user_by_ref_code,
    insert_transaction,
    update_blogger_balance,
    update_crystals,
    update_referral_paid,
    count_successful_payments,
    get_user_by_id,
)


def generate_ref_code(prefix: str = "U") -> str:
    """Generate a ref code like 'U-ABCD1234'."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=8))
    return f"{prefix}-{suffix}"


def process_registration_referral(
    conn: sqlite3.Connection,
    referred_user_id: int,
    ref_code: str,
) -> bool:
    """
    Find the referrer by ref_code, create a referrals record.
    Returns True if referrer was found and record created, False otherwise.
    """
    referrer = get_user_by_ref_code(conn, ref_code)
    if referrer is None:
        return False
    create_referral(conn, referrer["id"], referred_user_id)
    return True


def process_payment_referral(
    conn: sqlite3.Connection,
    referred_user_id: int,
    amount_rub: float,
) -> None:
    """
    Called after a successful payment by referred_user_id.
    On first payment only: award the referrer 120 crystals (or 10% rub for bloggers).
    """
    referral = get_referral_by_referred(conn, referred_user_id)
    if referral is None:
        return
    if referral["blogger_reward_paid"] == 1:
        return

    # Count successful payments for the referred user (current payment already counted)
    paid_count = count_successful_payments(conn, referred_user_id)
    if paid_count != 1:
        # Only trigger on exactly the first successful payment
        return

    referrer = get_user_by_id(conn, referral["referrer_id"])
    if referrer is None:
        return

    # Atomically claim the reward slot — if another concurrent call wins, skip
    paid = update_referral_paid(conn, referral["id"])
    if not paid:
        return

    if referrer["is_blogger"]:
        # Blogger gets 10% of payment in rubles
        rub_reward = round(amount_rub * 0.10, 2)
        update_blogger_balance(conn, referrer["id"], rub_reward)
    else:
        # Regular user gets 120 crystals
        update_crystals(conn, referrer["id"], 120)
        insert_transaction(conn, referrer["id"], 120, "referral_bonus")
