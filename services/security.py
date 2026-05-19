"""
security.py — Security middleware and helpers for kidion.

- Security headers middleware
- Weak PIN validation
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )

        # Content Security Policy — allow own domain, Google Fonts, inline styles/scripts
        # (inline needed for Jinja templates + existing JS)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

        return response


# --- Weak PIN validation ---

# All same digits: 0000, 1111, ..., 9999
_SAME_DIGITS = {str(d) * 4 for d in range(10)}

# Sequential ascending: 0123, 1234, 2345, ..., 6789
_SEQUENTIAL_ASC = {
    "".join(str(d) for d in range(start, start + 4))
    for start in range(7)
}

# Sequential descending: 9876, 8765, ..., 3210
_SEQUENTIAL_DESC = {
    "".join(str(d) for d in range(start, start - 4, -1))
    for start in range(9, 2, -1)
}

# Common weak PINs
_COMMON_PINS = {
    "1122", "2233", "1212", "2121", "1221", "2112",
    "1010", "2020", "6969", "1357", "2468",
}

WEAK_PINS = _SAME_DIGITS | _SEQUENTIAL_ASC | _SEQUENTIAL_DESC | _COMMON_PINS


def is_weak_pin(pin: str) -> bool:
    """Check if a 4-digit PIN is too weak (easily guessable)."""
    return pin in WEAK_PINS
