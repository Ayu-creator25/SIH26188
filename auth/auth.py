"""Authentication helpers for the BorderShield AI dashboard.

Provides two things:
    * check_credentials(): server-side username/password check.
    * login_required: decorator that blocks a route unless the user
      has a valid logged-in session.

All secrets are read from environment variables (loaded from the
git-ignored .env file) -- nothing sensitive is hard-coded here.
"""

import time
from threading import Lock
import hmac
import os
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import redirect, session, url_for

# Load .env from the repo root (one folder above auth/). If the file does
# not exist (e.g. on a hosting platform), this silently does nothing and
# the platform's real environment variables are used instead.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


# --- Login rate limiting (in-memory, per IP address) ---
# Not shared across multiple server processes -- fine for a single-instance
# prototype. A production deployment should move this to Redis or the
# database instead (see the production-rebuild roadmap, Phase 2).

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutes
FAILURE_WINDOW_SECONDS = 900  # failures further apart than this do not add up

_login_attempts = {}  # ip -> {"count": int, "locked_until": float or None, "last_failure": float}
_login_attempts_lock = Lock()


def is_locked_out(ip_address):
    """Return (True, seconds_remaining) if this IP is currently locked out,
    otherwise (False, 0)."""
    with _login_attempts_lock:
        record = _login_attempts.get(ip_address)
        if not record or not record["locked_until"]:
            return False, 0

        seconds_remaining = record["locked_until"] - time.time()
        if seconds_remaining <= 0:
            # Lockout has expired -- clear it so the next attempt is fresh.
            _login_attempts.pop(ip_address, None)
            return False, 0

        return True, int(seconds_remaining)


def record_failed_login(ip_address):
    """Count one failed attempt for this IP. Locks it out if the limit is hit.

    Failures only add up while they keep coming. An IP that has been quiet for
    FAILURE_WINDOW_SECONDS starts again from zero, so a few typos spread over
    days never lock anyone out (and the table cannot grow forever).
    """
    now = time.time()
    with _login_attempts_lock:
        quiet_ips = [
            ip for ip, rec in _login_attempts.items()
            if not rec["locked_until"] and now - rec["last_failure"] > FAILURE_WINDOW_SECONDS
        ]
        for ip in quiet_ips:
            del _login_attempts[ip]

        record = _login_attempts.setdefault(
            ip_address, {"count": 0, "locked_until": None, "last_failure": now}
        )
        record["count"] += 1
        record["last_failure"] = now
        if record["count"] >= MAX_FAILED_ATTEMPTS:
            record["locked_until"] = now + LOCKOUT_SECONDS


def reset_login_attempts(ip_address):
    """Clear an IP's failed-attempt count after a successful login."""
    with _login_attempts_lock:
        _login_attempts.pop(ip_address, None)


def check_credentials(username, password):
    """Return True only if username and password match the demo login.

    Fails closed: if the expected credentials are missing from the
    environment, nobody can log in (instead of everyone getting in).
    """
    expected_username = os.environ.get("AUTH_USERNAME", "")
    expected_password = os.environ.get("AUTH_PASSWORD", "")

    if not expected_username or not expected_password:
        return False

    # compare_digest takes the same time however many characters match,
    # which prevents timing attacks. It needs bytes to handle non-ASCII.
    username_ok = hmac.compare_digest(
        (username or "").encode("utf-8"), expected_username.encode("utf-8")
    )
    password_ok = hmac.compare_digest(
        (password or "").encode("utf-8"), expected_password.encode("utf-8")
    )

    # Use & (not "and") so both comparisons always run.
    return username_ok & password_ok


def login_required(view_function):
    """Decorator: redirect to /login unless the session says logged in.

    The check runs on the server for every request, so calling a URL
    directly (browser, curl, script) without a valid session is refused.
    """

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        # Only a simple flag lives in the session, never the password.
        if not session.get("logged_in"):
            # "login" must match the name of the login route function
            # defined in backend/app.py.
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)

    return wrapped_view