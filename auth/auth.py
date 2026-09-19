"""Authentication helpers for the BorderShield AI dashboard.

Provides two things:
    * check_credentials(): server-side username/password check.
    * login_required: decorator that blocks a route unless the user
      has a valid logged-in session.

All secrets are read from environment variables (loaded from the
git-ignored .env file) -- nothing sensitive is hard-coded here.
"""

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