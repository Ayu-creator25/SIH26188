"""
Orientation Correction
----------------------
Phone photos of ID cards are often stored sideways or upside down (the
camera saved the pixels as-is and no EXIF rotation tag was set). EasyOCR then
reads garbage and face matching fails on a sideways portrait, so a genuine
document can end up rated High Risk.

This module turns the image upright BEFORE OCR and face matching:

    1. Apply the EXIF orientation tag if the photo has one.
    2. Find the portrait on the card with RetinaFace and read its landmarks.
       The direction from the mouth to the eyes tells us which way is "up".
    3. Rotate by a multiple of 90 degrees so the face is upright, and save the
       result as a lossless PNG next to the original.

The original file is never modified. Tamper detection should keep using it,
because error level analysis depends on the original JPEG compression.

Usage from the repo root:
    python ocr/orientation.py data/uploads/<image>
"""

import math
import os
import sys

import numpy as np
from PIL import Image, ImageOps

# Detection runs on a downscaled copy: much faster, and the portrait on an ID
# card is still large enough to be found.
DETECTION_MAX_SIDE = 900

# A face must be detected with at least this confidence to be trusted.
MIN_FACE_SCORE = 0.9

# If the "up" direction is more than this far from a right angle, the
# landmarks are too tilted to decide from and are treated as ambiguous.
MAX_TILT_DEGREES = 35

_TRANSPOSE = {
    90: Image.Transpose.ROTATE_90,    # counter-clockwise
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_270,
}


def rotation_to_upright(landmarks):
    """
    Return how many degrees (0, 90, 180 or 270, counter-clockwise) the image
    must be rotated to make this face upright, or None if it cannot be told.

    The "up" direction of a face points from the middle of the mouth to the
    middle of the eyes. Using midpoints means the left/right eye labels do not
    matter.
    """
    try:
        eyes = (landmarks["right_eye"], landmarks["left_eye"])
        mouth = (landmarks["mouth_right"], landmarks["mouth_left"])
        up_x = (eyes[0][0] + eyes[1][0]) / 2 - (mouth[0][0] + mouth[1][0]) / 2
        up_y = (eyes[0][1] + eyes[1][1]) / 2 - (mouth[0][1] + mouth[1][1]) / 2
    except (KeyError, TypeError, IndexError):
        return None

    if math.hypot(up_x, up_y) < 1e-6:
        return None

    # Image y grows downward, so an upright face has up = (0, -1) -> 0 degrees.
    angle = math.degrees(math.atan2(up_x, -up_y)) % 360
    snapped = (round(angle / 90) % 4) * 90
    off_axis = abs((angle - snapped + 180) % 360 - 180)
    return snapped if off_axis <= MAX_TILT_DEGREES else None


def _rotate(image, angle):
    """Rotate counter-clockwise by 0, 90, 180 or 270 degrees, without loss."""
    return image if angle == 0 else image.transpose(_TRANSPOSE[angle])


def _downscale(image):
    """Return a copy small enough for fast face detection."""
    small = image.copy()
    small.thumbnail((DETECTION_MAX_SIDE, DETECTION_MAX_SIDE))
    return small


def _best_face(faces):
    """Pick the most confident face from a detector's output, or None."""
    return max(faces, key=lambda face: face["score"]) if faces else None


def retinaface_detector(image):
    """
    Detect faces with RetinaFace (already a project dependency).

    Returns a list of {"score": float, "landmarks": dict or None}.
    The import is lazy so that this module loads without TensorFlow.
    """
    from retinaface import RetinaFace

    bgr = np.ascontiguousarray(np.asarray(image.convert("RGB"))[:, :, ::-1])
    found = RetinaFace.detect_faces(bgr, threshold=0.5)
    if not isinstance(found, dict):
        return []
    return [
        {"score": float(face["score"]), "landmarks": face.get("landmarks")}
        for face in found.values()
    ]


def _is_upright(face):
    """True if the face is confident and (when landmarks exist) upright."""
    if face is None or face["score"] < MIN_FACE_SCORE:
        return False
    return rotation_to_upright(face.get("landmarks")) in (None, 0)


def _find_upright_angle(small, detect):
    """Return (angle, scores) where angle is the rotation that makes the card upright."""
    scores = {}
    face = _best_face(detect(small))
    scores[0] = face["score"] if face else 0.0

    candidates = [90, 270, 180]
    if face and face["score"] >= MIN_FACE_SCORE:
        suggested = rotation_to_upright(face.get("landmarks"))
        if suggested in (None, 0):
            return 0, scores  # already upright (or the landmarks cannot say)
        # The landmarks point at the likely fix, so try that angle first.
        candidates = [suggested] + [a for a in candidates if a != suggested]

    for angle in candidates:
        face = _best_face(detect(_rotate(small, angle)))
        scores[angle] = face["score"] if face else 0.0
        if _is_upright(face):
            return angle, scores

    return 0, scores  # no portrait found at any angle: leave the image alone


def correct_orientation(image_path, detect=None):
    """
    Make an uploaded ID image upright.

    Args:
        image_path (str): Path to the uploaded image (never modified).
        detect: Optional face detector (used by the tests). Defaults to RetinaFace.

    Returns:
        dict: {
            "path": str,      # image to use for OCR and face matching
            "angle": int,     # degrees counter-clockwise applied by face search
            "changed": bool,  # True if a corrected copy was written
            "note": str,      # short human-readable summary
            "scores": dict,   # face confidence per angle that was tried
        }
    """
    detect = detect or retinaface_detector

    with Image.open(image_path) as opened:
        exif_orientation = opened.getexif().get(274, 1)
        image = ImageOps.exif_transpose(opened).convert("RGB")
    exif_applied = exif_orientation not in (0, 1)

    angle, scores = _find_upright_angle(_downscale(image), detect)

    if angle == 0 and not exif_applied:
        return {"path": image_path, "angle": 0, "changed": False, "note": "", "scores": scores}

    output_path = os.path.splitext(image_path)[0] + "_oriented.png"
    _rotate(image, angle).save(output_path)

    parts = []
    if exif_applied:
        parts.append("the photo's rotation tag was applied")
    if angle:
        parts.append(f"the card was sideways, so it was rotated {angle} degrees")
    return {
        "path": output_path,
        "angle": angle,
        "changed": True,
        "note": "Image straightened automatically: " + " and ".join(parts) + ".",
        "scores": scores,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python ocr/orientation.py <image>")
    outcome = correct_orientation(sys.argv[1])
    print("Face confidence per angle tried:", outcome["scores"])
    print("Rotation applied (degrees counter-clockwise):", outcome["angle"])
    print("Image to use:", outcome["path"])
    print(outcome["note"] or "Image was already upright (or no portrait was found).")
