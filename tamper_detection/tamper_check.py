"""
Tampering Detection Module — SIH26188 (AI-Based Fake Identity and Document Screening)
Owner: Ashutosh

Purpose
-------
Uses Error Level Analysis (ELA) to flag signs of digital tampering in an
uploaded document image. ELA works by re-saving the image at a known JPEG
compression quality and measuring the pixel-level difference between the
original and the re-saved version. Regions that were pasted in from a
different source, edited, or re-compressed at a different quality tend to
show a different (usually higher, and localized) error signature than the
rest of an untouched image, which should show low, roughly uniform error.

This is a *signal*, not a verdict — same as face_verify. backend/app.py
combines this with OCR, field validation, and face match results before
producing a final risk explanation. This module must never decide
VERIFIED/SUSPICIOUS/HIGH RISK on its own.

Expected contract (do not change without also updating backend/app.py):
    check_tampering(image_path: str) -> dict

Limitations (documented on purpose — ELA is a heuristic, not proof)
---------------------------------------------------------------
- Works best on JPEGs. A lossless source (PNG) that's never touched a JPEG
  encoder will usually show very low, uniform error too, so "Clean" results
  are meaningful either way — but a skilled edit re-saved at a *matching*
  quality can, in principle, evade detection. Treat "Clean" as "no obvious
  signs found," not "verified authentic."
- Thresholds below are tuned for typical scanned/photographed ID documents,
  not a universal constant. They may need retuning against real samples.
"""

import os

import cv2
import numpy as np

# Tunable detection parameters — kept as module constants so they're easy
# to retune later without touching the function body.
#
# IMPORTANT — two things learned empirically during testing, not obvious
# from first principles:
#
# 1. Real ELA per-pixel error values are tiny (typically 0-10 on a 0-255
#    scale), because JPEG re-compression at a fixed quality barely changes
#    an already-stable image. A naive fixed threshold (e.g. 35) never
#    triggers on anything.
#
# 2. Raw "what fraction of pixels are elevated" is the wrong metric for
#    real ID documents. Text and sharp edges (exactly what ID documents are
#    full of — names, numbers, borders) create hundreds of small, scattered
#    high-error pixels along every letter/line edge, even in a completely
#    unedited image. That inflated a total-pixel-ratio metric enough to
#    falsely flag ordinary text documents as tampered.
#
#    The fix: look at the SIZE OF THE LARGEST CONTIGUOUS BLOB of elevated
#    pixels, not the total count. Genuine tampering (a pasted/edited region)
#    produces one concentrated blob. Text edges produce many tiny,
#    disconnected ones — so even though the *total* elevated-pixel count can
#    be similar, the *largest single blob* is a much cleaner signal.
ELA_QUALITY = 90              # JPEG quality used for the re-save comparison
THRESHOLD_STD_MULTIPLIER = 6  # "elevated" = error > mean + 6*std for this image
THRESHOLD_FLOOR = 1.5         # minimum threshold regardless of how flat the image is
LARGEST_BLOB_RATIO = 0.0002   # if the biggest connected blob covers > 0.02% of
                               # the image, flag as Suspicious. Calibrated against
                               # both text-document and photographic test cases:
                               # worst observed clean case was 0.0127% (dense text),
                               # weakest observed tampered case was 0.0329%
                               # (small pasted patch) — 0.02% sits between both
                               # with margin on each side.


def check_tampering(image_path):
    """
    Run tampering detection on a document image.

    Args:
        image_path (str): Path to the uploaded document image.

    Returns:
        dict: {
            "status": "Clean" | "Suspicious" | "Pending",
            "details": str
        }
        "Pending" is used for input errors (missing file, unreadable image)
        rather than raising — this keeps the pipeline running even if one
        module hits a bad file, matching the pattern used elsewhere.
    """
    if not image_path or not os.path.isfile(image_path):
        return _pending(f"Image not found: {image_path!r}")

    original = cv2.imread(image_path)
    if original is None:
        return _pending(f"Could not read image (unsupported format or corrupt file): {image_path!r}")

    # Re-encode the image in memory at a fixed JPEG quality, then decode it
    # back — this is the "re-save" step of classic ELA, done without
    # touching disk.
    success, encoded = cv2.imencode(".jpg", original, [cv2.IMWRITE_JPEG_QUALITY, ELA_QUALITY])
    if not success:
        return _pending("Failed to re-encode image for ELA comparison.")

    resaved = cv2.imdecode(encoded, cv2.IMREAD_COLOR)

    diff = cv2.absdiff(original, resaved)
    gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

    max_error = int(gray_diff.max())
    mean_error = float(gray_diff.mean())
    std_error = float(gray_diff.std())

    # Per-image adaptive threshold — see the constants comment above for why.
    pixel_threshold = max(mean_error + THRESHOLD_STD_MULTIPLIER * std_error, THRESHOLD_FLOOR)
    elevated_mask = (gray_diff > pixel_threshold).astype(np.uint8)

    # Look at the largest contiguous blob of elevated pixels, not the total
    # count — see the constants comment above for why this matters.
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(elevated_mask)
    largest_blob = int(stats[1:, cv2.CC_STAT_AREA].max()) if num_labels > 1 else 0
    total_pixels = int(gray_diff.size)
    largest_blob_ratio = largest_blob / total_pixels

    if largest_blob_ratio > LARGEST_BLOB_RATIO:
        status = "Suspicious"
        details = (
            f"Found a concentrated region of {largest_blob} pixels "
            f"({largest_blob_ratio * 100:.4f}% of the image) with compression error well "
            f"above this image's own baseline (pixel threshold {pixel_threshold:.2f}), "
            f"suggesting localized editing. Max error: {max_error}, mean error: {mean_error:.3f}."
        )
    else:
        status = "Clean"
        details = (
            f"No concentrated region of elevated compression error found "
            f"(largest contiguous region: {largest_blob} pixels, "
            f"{largest_blob_ratio * 100:.4f}% of the image), consistent with an unedited "
            f"image. Max error: {max_error}, mean error: {mean_error:.3f}."
        )

    return {"status": status, "details": details}


def _pending(message):
    return {"status": "Pending", "details": message}


if __name__ == "__main__":
    # Standalone smoke test — resolves relative to this file's location so
    # it works no matter what directory you run it from or which OS you're on.
    sample_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "sample_id_photo.jpg"
    )
    result = check_tampering(sample_path)
    print("Result:")
    for k, v in result.items():
        print(f"  {k}: {v}")