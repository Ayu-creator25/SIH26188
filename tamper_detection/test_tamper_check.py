"""
Tests for tamper_detection/tamper_check.py

Deliberately self-contained: every test image is generated on the fly with
numpy/OpenCV rather than loaded from data/. That keeps these tests
reproducible on any teammate's machine without needing a shared image file
to exist in the same place, and avoids ever needing a real (or even
synthetic-but-committed) ID photo just to test this module.

Run with:
    pytest tamper_detection/test_tamper_check.py -v
"""

import cv2
import numpy as np
import pytest

from tamper_check import check_tampering


# --------------------------------------------------------------------------
# Fixtures: build synthetic "clean" and "tampered" JPEGs in a temp directory
# --------------------------------------------------------------------------

@pytest.fixture
def clean_image_path(tmp_path):
    """A smooth gradient + mild noise image, saved once — like an unedited scan."""
    rng = np.random.default_rng(42)
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    for y in range(400):
        img[y, :, 0] = int(50 + y * 0.3)
        img[y, :, 1] = int(80 + y * 0.2)
        img[y, :, 2] = int(120 + y * 0.1)
    noise = rng.integers(0, 15, img.shape, dtype=np.uint8)
    img = cv2.add(img, noise)

    path = tmp_path / "clean.jpg"
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return str(path)


@pytest.fixture
def busy_clean_image_path(tmp_path):
    """A naturally high-texture (but still unedited) image — regression guard
    against false positives on legitimately detailed photos."""
    rng = np.random.default_rng(7)
    img = rng.integers(40, 200, (400, 600, 3), dtype=np.uint8)
    img = cv2.GaussianBlur(img, (5, 5), 0)

    path = tmp_path / "busy_clean.jpg"
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return str(path)


@pytest.fixture
def tampered_image_path(tmp_path):
    """Same base image as clean_image_path, but with a patch pasted in that
    has a different prior compression history (simulating a copy-pasted /
    edited region) before the final save."""
    rng = np.random.default_rng(42)
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    for y in range(400):
        img[y, :, 0] = int(50 + y * 0.3)
        img[y, :, 1] = int(80 + y * 0.2)
        img[y, :, 2] = int(120 + y * 0.1)
    noise = rng.integers(0, 15, img.shape, dtype=np.uint8)
    img = cv2.add(img, noise)

    # Patch with its own, much lower-quality compression history, pasted in.
    patch_raw = rng.integers(0, 255, (80, 120, 3), dtype=np.uint8)
    _, enc = cv2.imencode(".jpg", patch_raw, [cv2.IMWRITE_JPEG_QUALITY, 15])
    patch = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    img[150:230, 250:370] = patch

    path = tmp_path / "tampered.jpg"
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return str(path)


@pytest.fixture
def corrupt_image_path(tmp_path):
    """A file with a .jpg extension that isn't a real image."""
    path = tmp_path / "corrupt.jpg"
    path.write_bytes(b"this is not a real jpeg file")
    return str(path)


@pytest.fixture
def text_document_path(tmp_path):
    """A synthetic *unedited* text document — regression fixture for a real
    bug found during manual testing: printed text (dense black-on-light
    edges, exactly what a real ID document's fields look like) produces
    hundreds of tiny scattered elevated-error pixels on JPEG re-compression,
    which falsely tripped an earlier raw-pixel-ratio version of this check.
    This must always come back Clean."""
    img = np.full((400, 600, 3), 235, dtype=np.uint8)
    lines = [
        "MOCK DOCUMENT - NOT REAL ID",
        "Name: TEST PERSON EXTRA LONG NAME HERE",
        "DOB: 01/01/2000",
        "ID No: 0000-0000-0000-0000",
        "Address: 123 Fake Street, Testville",
        "Issued: 01/01/2020   Expires: 01/01/2030",
        "Authority: MOCK ISSUING AUTHORITY",
    ]
    for i, line in enumerate(lines):
        cv2.putText(img, line, (20, 40 + i * 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

    path = tmp_path / "text_document.jpg"
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return str(path)


@pytest.fixture
def tampered_text_document_path(tmp_path):
    """Same text document as text_document_path, but with one field pasted
    over with content that has a different compression history — this must
    still be caught as Suspicious even though the image is full of text."""
    img = np.full((400, 600, 3), 235, dtype=np.uint8)
    lines = [
        "MOCK DOCUMENT - NOT REAL ID",
        "Name: TEST PERSON EXTRA LONG NAME HERE",
        "DOB: 01/01/2000",
        "ID No: 0000-0000-0000-0000",
        "Address: 123 Fake Street, Testville",
        "Issued: 01/01/2020   Expires: 01/01/2030",
        "Authority: MOCK ISSUING AUTHORITY",
    ]
    for i, line in enumerate(lines):
        cv2.putText(img, line, (20, 40 + i * 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

    rng = np.random.default_rng(1)
    patch_raw = rng.integers(0, 255, (40, 200, 3), dtype=np.uint8)
    _, enc = cv2.imencode(".jpg", patch_raw, [cv2.IMWRITE_JPEG_QUALITY, 15])
    patch = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    img[125:165, 20:220] = patch

    path = tmp_path / "tampered_text_document.jpg"
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return str(path)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_clean_image_returns_clean(clean_image_path):
    result = check_tampering(clean_image_path)
    assert result["status"] == "Clean"


def test_busy_but_unedited_image_does_not_false_positive(busy_clean_image_path):
    result = check_tampering(busy_clean_image_path)
    assert result["status"] == "Clean"


def test_tampered_image_returns_suspicious(tampered_image_path):
    result = check_tampering(tampered_image_path)
    assert result["status"] == "Suspicious"


def test_text_document_does_not_false_positive(text_document_path):
    """Regression test for a real bug: an earlier version of this module
    flagged unedited text documents as Suspicious because text-character
    edges create many small elevated-error pixels. Must stay Clean."""
    result = check_tampering(text_document_path)
    assert result["status"] == "Clean"


def test_tampered_text_document_returns_suspicious(tampered_text_document_path):
    """A tampered document should still be caught even when the image is
    full of text (i.e. the fix for the false positive above shouldn't have
    also broken detection on text-heavy images)."""
    result = check_tampering(tampered_text_document_path)
    assert result["status"] == "Suspicious"


def test_missing_file_returns_pending():
    result = check_tampering("this/path/does/not/exist.jpg")
    assert result["status"] == "Pending"


def test_empty_path_returns_pending():
    result = check_tampering("")
    assert result["status"] == "Pending"


def test_none_path_returns_pending():
    result = check_tampering(None)
    assert result["status"] == "Pending"


def test_corrupt_file_returns_pending(corrupt_image_path):
    result = check_tampering(corrupt_image_path)
    assert result["status"] == "Pending"


def test_return_shape_has_expected_keys(clean_image_path):
    result = check_tampering(clean_image_path)
    assert set(result.keys()) == {"status", "details"}
    assert isinstance(result["status"], str)
    assert isinstance(result["details"], str)
    assert result["status"] in {"Clean", "Suspicious", "Pending"}