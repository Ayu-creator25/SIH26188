"""
Decision Explanation
--------------------
Combines the four independent checks into ONE verdict (Verified / Suspicious /
High Risk) and explains it in plain language, with a stable reason code for
each finding and a recommended action for the officer.

The verdict and its explanation come from the same function, so they can never
disagree. The rules are "worst signal wins":

    * any hard failure                     -> High Risk   (Escalate)
    * no hard failure, but a check could
      not be completed                     -> Suspicious  (Officer review)
    * every check passed cleanly           -> Verified    (Clear)

A status that is not the expected "pass" value counts as "could not be
completed", so an unexpected status can never produce a Verified result.

The recommendation is advisory: an officer makes the final decision.
"""

# The one status that counts as a clean pass for each check.
PASS_STATUS = {
    "validation": "Valid",
    "tamper": "Clean",
    "face": "Match",
    "liveness": "Live",
}

# Hard failures, in the order they are reported.
_HARD_FAILURES = [
    ("tamper", "Suspicious", "TAMPER_SUSPICIOUS",
     "Image analysis found a region of the document image that looks edited."),
    ("validation", "Invalid", "VALIDATION_INVALID",
     "A field check failed (for example an ID number checksum, a date or the passport MRZ)."),
    ("face", "No Match", "FACE_NO_MATCH",
     "The live face does not match the portrait on the document."),
    ("liveness", "Spoof Detected", "LIVENESS_SPOOF",
     "The live photo looks like a printed photo or a screen, not a live person."),
]

# Reasons for a check that could not be completed, in reporting order.
_PENDING_REASONS = [
    ("validation", "VALIDATION_PENDING",
     "There were not enough readable ID fields to validate. This may be an "
     "unsupported document type or an unclear image."),
    ("tamper", "TAMPER_PENDING",
     "The tamper check could not be completed."),
    ("face", "FACE_PENDING",
     "Face matching could not be completed (no live photo, or no face was found)."),
    ("liveness", "LIVENESS_PENDING",
     "The liveness check could not be completed (no live photo, or no face was found)."),
]

_ALL_CLEAR = ("ALL_CLEAR", "All four checks passed: validation, tamper, face match and liveness.")

_ACTIONS = {
    "Verified": ("Clear", "Clear: no issues were found."),
    "Suspicious": ("Officer review", "Officer review: at least one check could not be completed."),
    "High Risk": ("Escalate", "Escalate: at least one check failed."),
}


def explain_decision(validation_status, tamper_status, face_match_status,
                     liveness_status, details=None):
    """
    Return the verdict and its explanation.

    Args:
        validation_status, tamper_status, face_match_status, liveness_status:
            The four check statuses as shown on the dashboard.
        details (dict, optional): Evidence text per check, keyed "validation",
            "tamper", "face" and "liveness". Shown next to a finding; never
            stored in the audit record.

    Returns:
        dict: {
            "decision": "Verified" | "Suspicious" | "High Risk",
            "action": "Clear" | "Officer review" | "Escalate",
            "action_text": str,
            "reason_codes": [str, ...],   # stable codes, safe to store
            "reasons": [{"code", "text", "evidence", "level"}, ...],
        }
    """
    statuses = {
        "validation": validation_status,
        "tamper": tamper_status,
        "face": face_match_status,
        "liveness": liveness_status,
    }
    details = details or {}
    reasons = []

    # 1. Hard failures make the result High Risk.
    for check, status, code, text in _HARD_FAILURES:
        if statuses[check] == status:
            reasons.append(_reason(code, text, details.get(check), "high-risk"))

    # 2. Any check that neither passed nor hard-failed could not be completed.
    failed_checks = {check for check, status, _, _ in _HARD_FAILURES if statuses[check] == status}
    for check, code, text in _PENDING_REASONS:
        if check not in failed_checks and statuses[check] != PASS_STATUS[check]:
            reasons.append(_reason(code, text, details.get(check), "suspicious"))

    if any(reason["level"] == "high-risk" for reason in reasons):
        decision = "High Risk"
    elif reasons:
        decision = "Suspicious"
    else:
        decision = "Verified"
        reasons.append(_reason(_ALL_CLEAR[0], _ALL_CLEAR[1], None, "verified"))

    action, action_text = _ACTIONS[decision]
    return {
        "decision": decision,
        "action": action,
        "action_text": action_text,
        "reason_codes": [reason["code"] for reason in reasons],
        "reasons": reasons,
    }


def _reason(code, text, evidence, level):
    """Build one reason entry."""
    return {
        "code": code,
        "text": text,
        "evidence": str(evidence).strip() if evidence else "",
        "level": level,
    }
