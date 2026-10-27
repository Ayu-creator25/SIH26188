"""
backend/test_login_security.py

Tests for the login protections: access control, the failed-login lockout,
the idle session timeout and the debug-mode setting.

These run the REAL backend/app.py and auth/auth.py. Only the heavy AI modules
(OCR, face matching, tamper check, liveness, blockchain) are swapped for tiny
stand-ins, so the tests are fast and need no models, camera or Ganache. They
never read your .env file: the test login is created fresh for every test.

Usage (from the repo root):
    pytest backend/test_login_security.py -v
"""

import re
import sys
import types
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent
USERNAME = "officer"
PASSWORD = "correct-horse"  # a made-up test password, not a real one


def _stand_in(name, **functions):
    """Build a tiny fake module that only offers the functions app.py imports."""
    module = types.ModuleType(name)
    module.__dict__.update(functions)
    return module


STAND_INS = {
    "scan": _stand_in("scan", scan_document=lambda path: ""),
    "orientation": _stand_in(
        "orientation", correct_orientation=lambda path: {"path": path, "note": ""}
    ),
    "face_match": _stand_in(
        "face_match", verify_face=lambda a, b: {"status": "ERROR", "message": ""}
    ),
    "tamper_check": _stand_in(
        "tamper_check", check_tampering=lambda path: {"status": "Clean", "details": ""}
    ),
    "liveness_check": _stand_in(
        "liveness_check",
        check_liveness=lambda path: {"is_live": None, "confidence": 0, "error": None},
    ),
    "hash_record": _stand_in(
        "hash_record",
        create_record=lambda doc_id, summary: {
            "tx_hash": None, "record_hash": None, "status": "Pending"
        },
    ),
    "audit_store": _stand_in(
        "audit_store",
        get_w3=lambda: None,
        list_records=lambda limit=25: [],
        save_record=lambda *args, **kwargs: None,
        verify_record=lambda document_id, w3=None: {},
    ),
}


@pytest.fixture()
def app_client(monkeypatch):
    """Give each test the real app, a test browser and a fresh lockout table."""
    # Ignore the developer's real .env so the tests behave the same everywhere.
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-real")
    monkeypatch.setenv("AUTH_USERNAME", USERNAME)
    monkeypatch.setenv("AUTH_PASSWORD", PASSWORD)
    monkeypatch.delenv("SESSION_TIMEOUT_MINUTES", raising=False)

    # monkeypatch puts everything back afterwards, so other tests see the real modules.
    for name, module in STAND_INS.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.syspath_prepend(str(BACKEND_DIR))

    # Import app and auth again so every test starts with an empty lockout table.
    sys.modules.pop("app", None)
    sys.modules.pop("auth", None)
    import app as app_module
    import auth as auth_module

    yield app_module, auth_module, app_module.app.test_client()

    sys.modules.pop("app", None)
    sys.modules.pop("auth", None)


def log_in(client, password=PASSWORD, ip="127.0.0.1"):
    """Submit the login form as a visitor with the given IP address."""
    return client.post(
        "/login",
        data={"username": USERNAME, "password": password},
        environ_base={"REMOTE_ADDR": ip},
    )


def fail_logins(client, times, ip="127.0.0.1"):
    """Send wrong passwords and return the status code of each answer."""
    return [log_in(client, "wrong-password", ip).status_code for _ in range(times)]


def make_older(auth_module, ip, field, seconds):
    """Pretend a stored time ("locked_until" or "last_failure") was `seconds` earlier."""
    auth_module._login_attempts[ip][field] -= seconds


# --- Access control ---------------------------------------------------------

def test_pages_need_a_login(app_client):
    _, _, client = app_client
    for path in ("/", "/audit", "/verify/anything"):
        response = client.get(path)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
    assert client.post("/scan").status_code == 302


def test_sign_out_ends_the_session(app_client):
    _, _, client = app_client
    assert log_in(client).status_code == 302
    assert client.get("/").status_code == 200
    client.get("/logout")
    assert client.get("/").status_code == 302


# --- Failed-login lockout ---------------------------------------------------

def test_five_wrong_passwords_then_locked_out(app_client):
    _, _, client = app_client
    assert fail_logins(client, 5) == [401] * 5
    locked = log_in(client, "wrong-password")
    assert locked.status_code == 429
    assert b"Too many failed attempts" in locked.data


def test_correct_password_is_refused_while_locked(app_client):
    _, _, client = app_client
    fail_logins(client, 5)
    assert log_in(client).status_code == 429
    assert client.get("/").status_code == 302  # still not logged in


def test_lockout_only_affects_the_ip_that_failed(app_client):
    _, _, client = app_client
    fail_logins(client, 5, ip="10.0.0.1")
    assert log_in(client, ip="10.0.0.1").status_code == 429
    assert log_in(client, ip="10.0.0.2").status_code == 302


def test_lockout_ends_after_the_wait(app_client):
    _, auth_module, client = app_client
    fail_logins(client, 5)
    # Pretend the five minutes are over by moving the unlock time into the past.
    make_older(auth_module, "127.0.0.1", "locked_until", auth_module.LOCKOUT_SECONDS + 1)
    assert log_in(client).status_code == 302


def test_a_successful_login_resets_the_counter(app_client):
    _, _, client = app_client
    fail_logins(client, 4)
    assert log_in(client).status_code == 302
    client.get("/logout")
    assert fail_logins(client, 4) == [401] * 4  # not locked: the count started again


def test_failures_far_apart_do_not_add_up(app_client):
    _, auth_module, client = app_client
    fail_logins(client, 4)
    # Pretend the last failure was longer ago than the failure window.
    make_older(auth_module, "127.0.0.1", "last_failure", auth_module.FAILURE_WINDOW_SECONDS + 1)
    assert fail_logins(client, 4) == [401] * 4  # still no lockout


def test_quiet_ip_addresses_are_forgotten(app_client):
    _, auth_module, client = app_client
    fail_logins(client, 2, ip="10.0.0.1")
    make_older(auth_module, "10.0.0.1", "last_failure", auth_module.FAILURE_WINDOW_SECONDS + 1)
    fail_logins(client, 1, ip="10.0.0.2")  # any new failure tidies the table
    assert "10.0.0.1" not in auth_module._login_attempts


# --- Idle session timeout ---------------------------------------------------

def test_login_cookie_expires_after_15_minutes(app_client):
    _, _, client = app_client
    response = log_in(client)
    cookie = next(h for h in response.headers.getlist("Set-Cookie") if h.startswith("session="))
    expires = parsedate_to_datetime(re.search(r"Expires=([^;]+)", cookie).group(1))
    minutes_left = (expires - datetime.now(timezone.utc)).total_seconds() / 60
    assert 14 <= minutes_left <= 15.5
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_server_rejects_a_login_older_than_the_timeout(app_client, monkeypatch):
    _, _, client = app_client
    log_in(client)
    assert client.get("/").status_code == 200

    # Move only the cookie signer's clock forward 16 minutes (not the whole system clock).
    import itsdangerous.timed as timed
    real_timestamp = timed.TimestampSigner.get_timestamp
    monkeypatch.setattr(
        timed.TimestampSigner, "get_timestamp", lambda self: real_timestamp(self) + 16 * 60
    )
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# --- Server settings --------------------------------------------------------

def test_debug_mode_is_off():
    source = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
    assert "debug=True" not in source
    assert "debug=False" in source
