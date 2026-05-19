"""
rate_limiter.py — In-memory rate limiter for auth endpoints.

Uses a simple sliding window counter per (IP, endpoint) or (key, endpoint).
Thread-safe via threading.Lock.
"""

import os
import threading
import time
from collections import defaultdict

def _is_testing():
    return os.environ.get("TESTING", "").lower() in ("1", "true", "yes")


class RateLimiter:
    """Simple in-memory sliding window rate limiter."""

    def __init__(self):
        self._lock = threading.Lock()
        # key -> list of timestamps
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def is_limited(self, key: str, max_attempts: int, window_seconds: int) -> bool:
        """
        Check if the key has exceeded max_attempts within window_seconds.
        If not exceeded, record this attempt and return False.
        If exceeded, return True (caller should block the request).
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Clean old entries
            self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]

            if len(self._attempts[key]) >= max_attempts:
                return True

            self._attempts[key].append(now)
            return False

    def record_failure(self, key: str) -> None:
        """Record a failed attempt without checking the limit."""
        now = time.time()
        with self._lock:
            self._attempts[key].append(now)

    def cleanup(self, max_age: int = 3600) -> None:
        """Remove entries older than max_age seconds."""
        cutoff = time.time() - max_age
        with self._lock:
            empty_keys = []
            for key, timestamps in self._attempts.items():
                self._attempts[key] = [t for t in timestamps if t > cutoff]
                if not self._attempts[key]:
                    empty_keys.append(key)
            for key in empty_keys:
                del self._attempts[key]


# Global singleton
_limiter = RateLimiter()


def check_rate_limit(ip: str, endpoint: str, max_attempts: int = 5, window: int = 300) -> bool:
    """
    Returns True if the request should be BLOCKED (rate limited).

    Args:
        ip: Client IP address
        endpoint: Endpoint identifier (e.g., "login", "pin_auth")
        max_attempts: Max attempts allowed in the window
        window: Window in seconds (default: 300 = 5 minutes)
    """
    if _is_testing():
        return False
    key = f"{endpoint}:{ip}"
    return _limiter.is_limited(key, max_attempts, window)


def check_rate_limit_by_key(key: str, endpoint: str, max_attempts: int = 5, window: int = 300) -> bool:
    """
    Rate limit by arbitrary key (e.g., child_id for PIN attempts).
    Returns True if BLOCKED.
    """
    if _is_testing():
        return False
    full_key = f"{endpoint}:{key}"
    return _limiter.is_limited(full_key, max_attempts, window)


def get_client_ip(request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For behind nginx."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if hasattr(request, "client") and request.client:
        return request.client.host
    return "unknown"
