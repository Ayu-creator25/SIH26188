"""
backend/test_results_navigation.py

Tests for moving around the dashboard: the stored scan results, the redirect
after a scan, the "Back to scan results" button on the integrity check page,
and the navigation links that every page has.

Like backend/test_login_security.py, these run the REAL app with the heavy AI
modules (OCR, face matching, tamper check, liveness, blockchain) swapped for
tiny stand-ins, and they never read your .env file.

Usage (from the repo root):
    pytest backend/test_results_navigation.py -v
"""

import io
import re
import sys
import types
from pathlib import Path
from urllib.parse import urlparse

import pytest

from recent_results import RecentResults

BACKEND_DIR = Path(__file__).resolve().parent
USERNAME = "officer"
PASSWORD = "correct-horse"  # a made-up test password, not a real one
RESULT_LIFETIME_SECONDS = 15 * 60


class FakeClock:
    """A clock the tests can move forward, so nothing ever has to wait."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


# --- The store on its own ---------------------------------------------------

def test_a_stored_result_can_be_recalled():
    store = RecentResults(ttl_seconds=60, max_items=5, clock=FakeClock())
    store.remember("scan-1", {"decision": "Verified"})
    assert store.recall("scan-1") == {"decision": "Verified"}
    assert store.has("scan-1")


def test_an_unknown_result_is_not_available():
    store = RecentResults(ttl_seconds=60, max_items=5, clock=FakeClock())
    assert store.recall("never-stored") is None
    assert not store.has("never-stored")


def test_results_expire_after_the_time_limit():
    clock = FakeClock()
    store = RecentResults(ttl_seconds=60, max_items=5, clock=clock)
    store.remember("scan-1", {"decision": "Verified"})
    clock.advance(59)
    assert store.has("scan-1")
    clock.advance(2)
    assert store.recall("scan-1") is None


def test_the_oldest_results_are_dropped_when_there_are_too_many():
    store = RecentResults(ttl_seconds=60, max_items=2, clock=FakeClock())
    for name in ("scan-1", "scan-2", "scan-3"):
        store.remember(name, {"id": name})
    assert not store.has("scan-1")
    assert store.has("scan-2")
    assert store.has("scan-3")


def test_clear_forgets_everything():
    store = RecentResults(ttl_seconds=60, max_items=5, clock=FakeClock())
    store.remember("scan-1", {})
    store.clear()
    assert not store.has("scan-1")


# --- The real app -----------------------------------------------------------

def _stand_in(name, **attributes):
    """Build a tiny fake module that only offers what app.py imports."""
    module = types.ModuleType(name)
    module.__dict__.update(attributes)
    return module


def _make_stand_ins():
    recorded_scans = []  # one entry per call, so a test can count real scans

    def create_record(document_id, summary):
        recorded_scans.append(document_id)
        return {"tx_hash": "0xstub", "record_hash": "stubhash", "status": "Recorded"}

    return {
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
            "hash_record", create_record=create_record, RECORDED_SCANS=recorded_scans
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
def dashboard(monkeypatch, tmp_path):
    """The real app with a logged-in test browser and a clock the test controls."""
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)  # ignore .env
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-real")
    monkeypatch.setenv("AUTH_USERNAME", USERNAME)
    monkeypatch.setenv("AUTH_PASSWORD", PASSWORD)
    monkeypatch.delenv("SESSION_TIMEOUT_MINUTES", raising=False)

    stand_ins = _make_stand_ins()
    for name, module in stand_ins.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.syspath_prepend(str(BACKEND_DIR))

    sys.modules.pop("app", None)
    sys.modules.pop("auth", None)
    import app as app_module

    clock = FakeClock()
    monkeypatch.setattr(
        app_module, "recent_results", RecentResults(RESULT_LIFETIME_SECONDS, 20, clock=clock)
    )
    # Keep the test uploads out of the real data/uploads folder.
    monkeypatch.setattr(app_module, "UPLOAD_FOLDER", str(tmp_path))

    client = app_module.app.test_client()
    log_in(client)
    yield types.SimpleNamespace(
        app=app_module.app, client=client, clock=clock,
        recorded_scans=stand_ins["hash_record"].RECORDED_SCANS,
    )

    sys.modules.pop("app", None)
    sys.modules.pop("auth", None)


def log_in(client):
    return client.post("/login", data={"username": USERNAME, "password": PASSWORD})


def scan_a_document(client):
    """Upload a pretend ID card and return the response (a redirect to the results page)."""
    data = {"document": (io.BytesIO(b"not a real image"), "test-card.png")}
    return client.post("/scan", data=data, content_type="multipart/form-data")


def results_path_of(response):
    """The /results/<id> address a scan redirected to."""
    return urlparse(response.headers["Location"]).path


def test_a_scan_redirects_to_its_own_results_page(dashboard):
    response = scan_a_document(dashboard.client)
    assert response.status_code == 302
    assert re.fullmatch(r"/results/[0-9a-f-]{36}", results_path_of(response))


def test_the_results_page_can_be_reloaded_without_scanning_again(dashboard):
    path = results_path_of(scan_a_document(dashboard.client))
    first = dashboard.client.get(path)
    second = dashboard.client.get(path)
    assert first.status_code == 200
    assert second.status_code == 200
    assert b"Scan Results" in first.data
    assert len(dashboard.recorded_scans) == 1  # reloading did not run the pipeline again


def test_the_integrity_page_links_back_to_the_scan_results(dashboard):
    path = results_path_of(scan_a_document(dashboard.client))
    document_id = path.rsplit("/", 1)[-1]
    page = dashboard.client.get(f"/verify/{document_id}")
    assert page.status_code == 200
    assert b"Back to scan results" in page.data
    assert f'href="/results/{document_id}"'.encode() in page.data


def test_the_integrity_page_for_an_old_scan_has_no_results_link(dashboard):
    page = dashboard.client.get("/verify/an-old-record-id")
    assert b"Back to scan results" not in page.data
    assert b"Back to audit log" in page.data


def test_results_are_no_longer_available_after_the_time_limit(dashboard):
    path = results_path_of(scan_a_document(dashboard.client))
    dashboard.clock.advance(RESULT_LIFETIME_SECONDS + 1)
    response = dashboard.client.get(path)
    assert response.status_code == 404
    assert b"no longer available" in response.data


def test_signing_out_forgets_the_stored_results(dashboard):
    path = results_path_of(scan_a_document(dashboard.client))
    dashboard.client.get("/logout")
    log_in(dashboard.client)
    assert dashboard.client.get(path).status_code == 404


def test_the_results_page_needs_a_login(dashboard):
    logged_out = dashboard.app.test_client()
    response = logged_out.get("/results/anything")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


@pytest.mark.parametrize("page", ["upload", "audit", "integrity", "results"])
def test_every_page_has_the_navigation_links(dashboard, page):
    if page == "results":
        path = results_path_of(scan_a_document(dashboard.client))
    else:
        path = {"upload": "/", "audit": "/audit", "integrity": "/verify/anything"}[page]
    html = dashboard.client.get(path).data
    assert b'<a href="/" class="topbar__mark">BORDERSHIELD</a>' in html
    assert b'<a href="/" class="topbar__logout">New scan</a>' in html
    assert b'<a href="/audit" class="topbar__logout">Audit log</a>' in html
    assert b'<a href="/logout" class="topbar__logout">Sign out</a>' in html
