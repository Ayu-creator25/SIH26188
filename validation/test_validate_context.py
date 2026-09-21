"""
validation/test_validate_context.py

Tests for one rule in validate.py: a bare run of 12 digits is only treated as
an Aadhaar number when it is printed in groups ("1234 5678 9012") or the text
mentions Aadhaar / UID. Without that rule, a genuine ID carrying its own
12-digit number (a college registration number, say) was rated Invalid.

Usage (from the repo root):
    pytest validation/test_validate_context.py -v
"""

from validate import _verhoeff_valid, validate_fields


def make_valid_aadhaar():
    """Build a 12-digit number that passes the Verhoeff checksum."""
    prefix = "23456789012"
    return next(prefix + str(d) for d in range(10) if _verhoeff_valid(prefix + str(d)))


def make_invalid_aadhaar():
    """Build a 12-digit number that FAILS the Verhoeff checksum."""
    return next(n for n in ("123456789012", "123456789013") if not _verhoeff_valid(n))


def grouped(number):
    return f"{number[:4]} {number[4:8]} {number[8:]}"


GOOD = make_valid_aadhaar()
BAD = make_invalid_aadhaar()

# What EasyOCR should read from the upright university ID card.
UNIVERSITY_ID_TEXT = """CENTURION UNIVERSITY OF
TECHNOLOGY AND MANAGEMENT (CUTM)
Bhubaneswar Campus, Jatani, Odisha
Identity Card
Name
TEST STUDENT
Programme
Bachelor of Technology
Regd. No.
240101123456
Validity
2025 - 2029"""


def test_registration_number_is_not_mistaken_for_an_aadhaar():
    """The bug: the card's 12-digit registration number failed the Aadhaar checksum."""
    assert not _verhoeff_valid("240101123456")  # would have been flagged before
    result = validate_fields(UNIVERSITY_ID_TEXT)
    assert result["status"] == "Pending"
    assert "FAILED" not in result["details"]
    assert result["checks"]["format_valid"]["aadhaar"] is False


def test_bare_twelve_digits_without_a_cue_are_ignored():
    for text in (BAD, GOOD, "Regd. No. " + BAD, "919876543210"):
        assert validate_fields(text)["status"] == "Pending"


def test_grouped_valid_aadhaar_is_valid():
    text = f"Name: Test User\nDOB: 01/01/2000\nMALE\n{grouped(GOOD)}"
    result = validate_fields(text)
    assert result["status"] == "Valid"
    assert result["checks"]["format_valid"]["aadhaar"] is True


def test_grouped_invalid_aadhaar_is_still_flagged():
    text = f"Name: Test User\nDOB: 15/08/1995\nAadhaar: {grouped(BAD)}"
    result = validate_fields(text)
    assert result["status"] == "Invalid"
    assert "FAILED checksum" in result["details"]


def test_grouped_number_is_flagged_even_without_an_aadhaar_label():
    result = validate_fields(f"Name: Test User\nDOB: 01/01/2000\nMALE\n{grouped(BAD)}")
    assert result["status"] == "Invalid"


def test_ocr_that_puts_each_group_on_its_own_line_still_counts_as_grouped():
    text = f"Name: Test User\nDOB: 01/01/2000\nMALE\n{GOOD[:4]}\n{GOOD[4:8]}\n{GOOD[8:]}"
    assert validate_fields(text)["checks"]["format_valid"]["aadhaar"] is True


def test_bare_number_with_an_aadhaar_cue_is_checked():
    for cue in ("Aadhaar", "Aadhar", "UID", "UIDAI", "आधार"):
        bad = validate_fields(f"Name: Test User\nDOB: 15/08/1995\n{cue} {BAD}")
        assert bad["status"] == "Invalid", cue
        good = validate_fields(f"Name: Test User\nDOB: 15/08/1995\n{cue} {GOOD}")
        assert good["status"] == "Valid", cue


def test_the_existing_fake_test_image_text_is_still_invalid():
    text = "Name: Test User\nDOB: 15/08/1995\nAadhaar: 1234 5678 9012"
    result = validate_fields(text)
    assert result["status"] in ("Invalid", "Valid")  # depends only on the checksum
    assert result["status"] == ("Valid" if _verhoeff_valid("123456789012") else "Invalid")


def test_other_signals_are_untouched():
    """Passport numbers, dates and an invalid date still behave as before."""
    passport = validate_fields("Passport No: P1234567\nDOB: 01/01/2000")
    assert passport["checks"]["format_valid"]["passport"] is True
    assert validate_fields("Name: X\nDOB: 31/02/2001")["status"] == "Invalid"
    assert validate_fields("")["status"] == "Pending"
