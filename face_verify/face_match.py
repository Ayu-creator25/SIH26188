"""
Face Verification Module — SIH26188 (AI-Based Fake Identity and Document Screening)
Owner: [your name here]

Purpose
-------
Compares the photo printed on an ID document against a live-captured photo
(e.g. a webcam selfie taken at the point of verification) to confirm the
person holding the document is the person the document was issued to.

This is a *signal*, not a verdict — backend/app.py combines this with OCR,
field validation, and tamper-detection results before Claude Sonnet 5
produces the final human-readable risk explanation. This module must never
decide VERIFIED/SUSPICIOUS/HIGH RISK on its own; it only reports a match
result for the pipeline to weigh.

Function contract (do not change the name or inputs/outputs without telling
the team — backend/app.py calls this exact signature):

    verify_face(id_photo_path: str, live_photo_path: str) -> dict

Returns
-------
dict with keys:
    "match"      : bool   — True if the two faces are judged the same person
    "confidence" : float  — 0-100, higher = more confident in the result
    "distance"   : float | None — raw model distance (lower = more similar)
    "status"     : str    — "MATCH" | "NO_MATCH" | "ERROR"
    "message"    : str    — human-readable explanation (safe to log/display)

Notes
-----
- Uses DeepFace (https://github.com/serengil/deepface) with the Facenet
  model. Chosen over `face_recognition`/dlib because it installs cleanly on
  Windows with plain pip (no C++ build tools / cmake needed), which matters
  for a hackathon team on a deadline.
- No PII is written anywhere by this module — it only returns a
  match/confidence result. Keep it that way per the zero-PII-on-chain rule.
- Never commit real ID photos or live-capture photos. Use synthetic test
  images (MIDV-2020) from the data/ folder per the README.
"""

import os
from typing import Optional

from deepface import DeepFace


def verify_face(id_photo_path: str, live_photo_path: str) -> dict:
    # --- basic input validation -------------------------------------------------
    for label, path in (("id_photo_path", id_photo_path), ("live_photo_path", live_photo_path)):
        if not path or not os.path.isfile(path):
            return _error(f"{label} does not point to a valid file: {path!r}")

    # --- run the comparison -------------------------------------------------
    try:
        result = DeepFace.verify(
            img1_path=id_photo_path,
            img2_path=live_photo_path,
            model_name="Facenet",
            detector_backend="retinaface",
            enforce_detection=True,  # raise if no face is found, rather than guessing
        )
    except ValueError as e:
        # DeepFace raises ValueError when it can't detect a face in one of the images
        return _error(f"Face detection failed: {e}")
    except Exception as e:  # noqa: BLE001 — surface any other model/runtime error safely
        return _error(f"Unexpected error during face verification: {e}")

    distance: float = result["distance"]
    threshold: float = result["threshold"]
    matched: bool = bool(result["verified"])

    # Convert model distance into an intuitive 0-100 confidence score.
    # distance == 0        -> 100% confidence
    # distance == threshold -> ~50% confidence (the decision boundary)
    # distance beyond 2x threshold -> floors at 0%
    confidence = max(0.0, min(100.0, (1 - (distance / (2 * threshold))) * 100))

    return {
        "match": matched,
        "confidence": round(confidence, 2),
        "distance": round(distance, 4),
        "status": "MATCH" if matched else "NO_MATCH",
        "message": (
            f"Faces {'match' if matched else 'do not match'} "
            f"(distance={distance:.4f}, threshold={threshold:.4f})."
        ),
    }


def _error(message: str) -> dict:
    return {
        "match": False,
        "confidence": 0.0,
        "distance": None,
        "status": "ERROR",
        "message": message,
    }


if __name__ == "__main__":
    # Standalone test — point these at two synthetic test images before running:
    #   python face_verify/face_match.py
    id_photo = "data/sample_id_photo.jpg"
    live_photo = "data/sample_live_photo.jpg"

    outcome = verify_face(id_photo, live_photo)
    print("Result:")
    for k, v in outcome.items():
        print(f"  {k}: {v}")