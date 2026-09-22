"""
backend/test_explanation.py

Tests for explain_decision(): the single function that turns the four check
statuses into a verdict, a recommended action, and plain-language reasons.

Usage (from the repo root):
    pytest backend/test_explanation.py -v
"""

import itertools

import pytest

from explanation import PASS_STATUS, explain_decision

# The statuses each check can actually produce on the dashboard.
POSSIBLE_STATUSES = {
    "validation": ["Valid", "Invalid", "Pending"],
    "tamper": ["Clean", "Suspicious"],
    "face": ["Match", "No Match", "Pending"],
    "liveness": ["Live", "Spoof Detected", "Pending"],
}

ALL_PASS = {check: PASS_STATUS[check] for check in PASS_STATUS}


def outcome(**overrides):
    statuses = dict(ALL_PASS, **overrides)
    return explain_decision(
        statuses["validation"], statuses["tamper"], statuses["face"], statuses["liveness"]
    )


def test_all_pass_is_verified_and_clear():
    result = outcome()
    assert result["decision"] == "Verified"
    assert result["action"] == "Clear"
    assert result["reason_codes"] == ["ALL_CLEAR"]


@pytest.mark.parametrize("check,bad_status,code", [
    ("tamper", "Suspicious", "TAMPER_SUSPICIOUS"),
    ("validation", "Invalid", "VALIDATION_INVALID"),
    ("face", "No Match", "FACE_NO_MATCH"),
    ("liveness", "Spoof Detected", "LIVENESS_SPOOF"),
])
def test_each_hard_failure_alone_is_high_risk(check, bad_status, code):
    result = outcome(**{check: bad_status})
    assert result["decision"] == "High Risk"
    assert result["action"] == "Escalate"
    assert result["reason_codes"] == [code]


@pytest.mark.parametrize("check,code", [
    ("validation", "VALIDATION_PENDING"),
    ("tamper", "TAMPER_PENDING"),
    ("face", "FACE_PENDING"),
    ("liveness", "LIVENESS_PENDING"),
])
def test_each_pending_check_alone_is_suspicious(check, code):
    result = outcome(**{check: "Pending"})
    assert result["decision"] == "Suspicious"
    assert result["action"] == "Officer review"
    assert result["reason_codes"] == [code]


def test_no_live_photo_is_suspicious_with_two_reasons():
    """The most common real case: face and liveness both Pending."""
    result = outcome(face="Pending", liveness="Pending")
    assert result["decision"] == "Suspicious"
    assert result["reason_codes"] == ["FACE_PENDING", "LIVENESS_PENDING"]


def test_hard_failure_wins_the_decision_but_pending_checks_are_still_reported():
    """
    The DECISION is High Risk (worst signal wins), but the officer still sees
    every check that did not pass, not just the one that failed hardest.
    """
    result = outcome(tamper="Suspicious", face="Pending", liveness="Pending")
    assert result["decision"] == "High Risk"
    assert result["reason_codes"][0] == "TAMPER_SUSPICIOUS"
    assert "FACE_PENDING" in result["reason_codes"]
    assert "LIVENESS_PENDING" in result["reason_codes"]
    assert all(r["level"] == "suspicious" for r in result["reasons"][1:])


def test_hard_failure_beats_another_hard_failure_still_reports_both():
    result = outcome(tamper="Suspicious", face="No Match")
    assert result["decision"] == "High Risk"
    assert set(result["reason_codes"]) == {"TAMPER_SUSPICIOUS", "FACE_NO_MATCH"}


def test_all_four_hard_failures_reports_all_four():
    result = outcome(validation="Invalid", tamper="Suspicious", face="No Match", liveness="Spoof Detected")
    assert result["decision"] == "High Risk"
    assert len(result["reason_codes"]) == 4


def test_evidence_is_attached_to_the_matching_reason():
    result = explain_decision(
        "Invalid", "Clean", "Match", "Live",
        details={"validation": "Aadhaar checksum failed"},
    )
    assert result["reasons"][0]["evidence"] == "Aadhaar checksum failed"


def test_missing_evidence_is_an_empty_string_not_none():
    result = outcome(tamper="Suspicious")
    assert result["reasons"][0]["evidence"] == ""


def test_reason_order_is_deterministic():
    """Same inputs, called twice, must give the exact same order (for reason_codes stored on-chain)."""
    a = outcome(validation="Invalid", face="No Match")
    b = outcome(validation="Invalid", face="No Match")
    assert a["reason_codes"] == b["reason_codes"]


def test_unexpected_status_value_is_never_verified():
    """A status this function has never seen before must not slip through as a pass."""
    result = explain_decision("Weird", "Clean", "Match", "Live")
    assert result["decision"] != "Verified"
    assert result["reason_codes"] == ["VALIDATION_PENDING"]


@pytest.mark.parametrize(
    "validation,tamper,face,liveness",
    list(itertools.product(*POSSIBLE_STATUSES.values())),
)
def test_every_combination_agrees_with_the_original_fusion_rule(validation, tamper, face, liveness):
    """
    Differential test against the exact rule app.py used before this module
    existed, over every combination the dashboard can actually produce.
    """
    if tamper == "Suspicious" or validation == "Invalid" or face == "No Match" or liveness == "Spoof Detected":
        expected = "High Risk"
    elif "Pending" in (validation, tamper, face, liveness):
        expected = "Suspicious"
    else:
        expected = "Verified"

    result = explain_decision(validation, tamper, face, liveness)
    assert result["decision"] == expected, (validation, tamper, face, liveness)

    # The action must always match the decision, and codes must be unique.
    assert result["action"] == {"Verified": "Clear", "Suspicious": "Officer review", "High Risk": "Escalate"}[expected]
    assert len(result["reason_codes"]) == len(set(result["reason_codes"]))
    assert (len(result["reason_codes"]) == 0) == False  # always at least one reason
