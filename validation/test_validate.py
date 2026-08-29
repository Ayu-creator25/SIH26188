"""
Standalone tests for validation module.
Run with: python validation/test_validate.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from validation.validate import validate_fields, validate_mrz_line


def test_valid_aadhaar():
    """Test 1: Valid Aadhaar text — expect Valid with aadhaar format check True."""
    text = "Name: RAHUL KUMAR\nDOB: 15/08/1995\nAadhaar: 9999 9999 9999"
    result = validate_fields(text)
    assert result["status"] == "Valid", f"Expected Valid, got {result['status']}"
    assert result["checks"]["format_valid"]["aadhaar"] is True
    assert result["checks"]["fields_present"]["name"] is True
    assert result["checks"]["fields_present"]["dob"] is True
    print("Test 1 PASSED: Valid Aadhaar")


def test_valid_passport_format():
    """Test 2: Valid passport number format."""
    text = "Name: PRIYA SHARMA\nPassport No: K1234567\nDOB: 20/03/1990"
    result = validate_fields(text)
    assert result["status"] == "Valid"
    assert result["checks"]["format_valid"]["passport"] is True
    print("Test 2 PASSED: Valid passport format")


def test_invalid_aadhaar_wrong_digits():
    """Test 3: Invalid Aadhaar (wrong digit count) — format check fails."""
    text = "Name: TEST USER\nAadhaar: 1234 5678 90"  # Only 10 digits
    result = validate_fields(text)
    assert result["checks"]["format_valid"]["aadhaar"] is False
    print("Test 3 PASSED: Invalid Aadhaar format correctly rejected")


def test_missing_required_fields():
    """Test 4: Missing required fields — expect Invalid or Pending."""
    text = "Some random text without any document fields"
    result = validate_fields(text)
    assert result["status"] in ("Invalid", "Pending")
    print("Test 4 PASSED: Missing fields handled correctly")


def test_mrz_valid_checksum():
    """Test 5: Valid MRZ line with correct checksums (official ICAO 9303 example)."""
    mrz_line = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
    assert len(mrz_line) == 44, f"Test data malformed: {len(mrz_line)} chars"
    result = validate_mrz_line(mrz_line)
    assert result["valid"] is True, f"Expected valid, got: {result['details']}"
    print("Test 5 PASSED: Valid MRZ checksum correctly accepted")


def test_corrupted_mrz_checksum():
    """Test 6: Corrupted MRZ checksum — expect valid=False."""
    mrz_line = "L898902C36UTO7408122F1204159ZE184226B<<<<<19"
    assert len(mrz_line) == 44, f"Test data malformed: {len(mrz_line)} chars"
    result = validate_mrz_line(mrz_line)
    assert result["valid"] is False, "Expected corrupted checksum to be rejected"
    print("Test 6 PASSED: Corrupted MRZ checksum correctly rejected")


def test_empty_text():
    """Test 7: Empty text — expect Pending or Invalid."""
    result = validate_fields("")
    assert result["status"] in ("Pending", "Invalid")
    print("Test 7 PASSED: Empty text returns Pending")


def test_hindi_name_label():
    """Test 8: Hindi name label detection."""
    text = "नाम: राहुल कुमार\nDOB: 15/08/1995"
    result = validate_fields(text)
    assert result["checks"]["fields_present"]["name"] is True
    print("Test 8 PASSED: Hindi name label detected")


def test_hindi_dob_label():
    """Test 9: Hindi DOB label detection."""
    text = "Name: Rahul\nजन्म तिथि: 15/08/1995"
    result = validate_fields(text)
    assert result["checks"]["fields_present"]["dob"] is True
    print("Test 9 PASSED: Hindi DOB label detected")


def test_invalid_date():
    """Test 10: Invalid date format."""
    text = "Name: TEST\nDOB: 99/99/9999"
    result = validate_fields(text)
    # Date validation should catch invalid dates
    assert result["checks"]["date_valid"] is False or result["status"] == "Invalid"
    print("Test 10 PASSED: Invalid date detected")


def test_multiple_id_numbers():
    """Test 11: Text with both Aadhaar and passport numbers."""
    text = "Name: TEST USER\nAadhaar: 9999 9999 9999\nPassport: K7654321"
    result = validate_fields(text)
    assert result["checks"]["format_valid"]["aadhaar"] is True
    assert result["checks"]["format_valid"]["passport"] is True
    print("Test 11 PASSED: Multiple ID formats detected")

def test_pincode_not_treated_as_date():
    """Test 12: A 6-digit PIN code must not be misread as an invalid date."""
    text = "Name: Test User\nDOB: 15/08/1995\nAadhaar: 9999 9999 9999\nAddress: Jharkhand 828113"
    result = validate_fields(text)
    assert result["checks"]["date_valid"] is True, "PIN code was incorrectly treated as a date"
    assert result["status"] == "Valid"
    print("Test 12 PASSED: PIN code not misread as a date")


def test_aadhaar_checksum_failure_marks_invalid():
    """Test 13: A 12-digit number with a bad checksum must fail overall, not just the format flag."""
    text = "Name: Test User\nDOB: 15/08/1995\nAadhaar: 1234 5678 9012"
    result = validate_fields(text)
    assert result["checks"]["format_valid"]["aadhaar"] is False
    assert result["status"] == "Invalid", "Fabricated Aadhaar number was not flagged as Invalid"
    print("Test 13 PASSED: Bad Aadhaar checksum correctly fails overall status")


def test_name_detected_without_label():
    """Test 14: A name with no 'Name:'/'नाम:' label (real Aadhaar cards do this) must still be detected."""
    text = "Government of India\nAyush Gupta\nDOB: 15/08/1995\nAadhaar: 9999 9999 9999"
    result = validate_fields(text)
    assert result["checks"]["fields_present"]["name"] is True
    print("Test 14 PASSED: Name detected without an explicit label")


def run_all_tests():
    """Run all test cases."""
    print("=" * 50)
    print("Running validation module tests")
    print("=" * 50)
    print()

    tests = [
        test_valid_aadhaar,
        test_valid_passport_format,
        test_invalid_aadhaar_wrong_digits,
        test_missing_required_fields,
        test_mrz_valid_checksum,
        test_corrupted_mrz_checksum,
        test_empty_text,
        test_hindi_name_label,
        test_hindi_dob_label,
        test_invalid_date,
        test_multiple_id_numbers,
        test_pincode_not_treated_as_date,
        test_aadhaar_checksum_failure_marks_invalid,
        test_name_detected_without_label,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAILED: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {test.__name__}: {e}")
            failed += 1

    print()
    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
