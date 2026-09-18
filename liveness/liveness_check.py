"""
liveness/liveness_check.py

Determines whether a captured face image is a real, live capture
or a spoof attempt (printed photo, phone/screen replay).

Wraps DeepFace's built-in MiniFASNet-based anti-spoofing model —
no custom model loading or training required.
"""

from deepface import DeepFace


def check_liveness(image_path):
    """
    Check whether the face in the given image is live or a spoof.

    Args:
        image_path (str): Path to the image file to check
            (typically a live webcam capture).

    Returns:
        dict: {
            "is_live": bool or None,  # True = real, False = spoof,
                                       # None = no face found
            "confidence": float,      # model confidence, 0.0-1.0
            "error": str or None,     # human-readable message on failure
        }
    """
    try:
        faces = DeepFace.extract_faces(
            img_path=image_path,
            anti_spoofing=True,
            detector_backend="retinaface",  # avoid the broken default 'opencv' backend
        )
    except ValueError as exc:
        # DeepFace raises ValueError when no face is detected
        return {"is_live": None, "confidence": 0.0, "error": f"No face detected: {exc}"}

    if not faces:
        return {"is_live": None, "confidence": 0.0, "error": "No face detected in image."}

    # If multiple faces are found, judge the largest — the likely intended subject
    largest_face = max(faces, key=lambda f: f["facial_area"]["w"] * f["facial_area"]["h"])

    return {
        "is_live": bool(largest_face["is_real"]),
        "confidence": float(round(largest_face["antispoof_score"], 3)),
        "error": None,
    }