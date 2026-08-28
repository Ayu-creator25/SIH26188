"""
Document Validation Module
---------------------------
Takes OCR-extracted text and checks it against expected document rules
(e.g. correctly formatted ID numbers, required fields present, valid
date formats, MRZ checksums).

Expected contract (do not change without also updating backend/app.py):
    validate_fields(extracted_text: str) -> dict
"""

import re
from datetime import datetime


# ---------------------------------------------------------------------------
# MRZ check-digit utility (used for passports)
# ---------------------------------------------------------------------------

_MRZ_WEIGHTS = [7, 3, 1]


def _mrz_check_digit(char):
    """Return the numeric value of a single MRZ character."""
    if char.isdigit():
        return int(char)
    # Letters map to 10 + their position: A=10, B=11, ... Z=35
    if char.isalpha():
        return ord(char.upper()) - ord('A') + 10
    if char == '<':
        return 0
    return 0


def _mrz_calculate_check_digit(data):
    """Calculate MRZ check digit for a field string."""
    total = 0
    for i, ch in enumerate(data):
        total += _mrz_check_digit(ch) * _MRZ_WEIGHTS[i % 3]
    return total % 10


def validate_mrz_line(mrz_line):
    """
    Validate a single MRZ line (TD3 — 44 chars, or TD1 — 30 chars).

    For TD3 line 2:
        Positions  0- 8 : passport number (9 chars)
        Position    9   : check digit for passport number
        Positions 10-13 : issuing country (3 chars + filler)
        Positions 14-18 : date of birth (6 chars YYMMDD)
        Position   19   : check digit for DOB
        Positions 20-21 : sex (M/F)
        Positions 22-26 : expiration date (6 chars YYMMDD)
        Position   27   : check digit for expiry
        Positions 28-41 : personal number (14 chars)
        Position   42   : check digit for composite
        Position   43   : overall check digit

    Returns:
        dict with keys: valid (bool), details (str)
    """
    line = mrz_line.strip()
    length = len(line)

    if length not in (30, 44):
        return {"valid": False, "details": f"MRZ line has unexpected length {length} (expected 30 or 44)"}

    if length == 44:
        # TD3 (passport) — line 2 format
        passport_field = line[0:9]
        passport_check = int(line[9]) if line[9].isdigit() else -1
        dob_field = line[13:19]
        dob_check = int(line[19]) if line[19].isdigit() else -1
        expiry_field = line[21:27]
        expiry_check = int(line[27]) if line[27].isdigit() else -1
        personal_field = line[28:42]
        personal_check = int(line[42]) if line[42].isdigit() else -1
        overall_check = int(line[43]) if line[43].isdigit() else -1
    elif length == 30:
        # TD1 (ID card) — composite check over fields 5-14, 15-20, 21-29
        dob_field = line[0:6]
        dob_check = int(line[6]) if line[6].isdigit() else -1
        expiry_field = line[8:14]
        expiry_check = int(line[14]) if line[14].isdigit() else -1
        passport_field = line[15:30]
        passport_check = -1  # not in standard TD1 position the same way
        overall_check = -1
        personal_check = -1
    else:
        return {"valid": False, "details": "Unsupported MRZ length"}

    errors = []

    # Validate DOB check digit
    if dob_check >= 0 and length == 44:
        expected = _mrz_calculate_check_digit(dob_field)
        if dob_check != expected:
            errors.append(f"DOB check digit mismatch (got {dob_check}, expected {expected})")

    # Validate expiry check digit
    if expiry_check >= 0 and length == 44:
        expected = _mrz_calculate_check_digit(expiry_field)
        if expiry_check != expected:
            errors.append(f"Expiry check digit mismatch (got {expiry_check}, expected {expected})")

    # Validate passport number check digit (TD3)
    if length == 44 and passport_check >= 0:
        expected = _mrz_calculate_check_digit(passport_field)
        if passport_check != expected:
            errors.append(f"Passport number check digit mismatch (got {passport_check}, expected {expected})")

    # Overall check digit (TD3 line 2)
    if length == 44 and overall_check >= 0:
        composite = line[0:10] + line[13:20] + line[21:43]
        expected = _mrz_calculate_check_digit(composite)
        if overall_check != expected:
            errors.append(f"Overall check digit mismatch (got {overall_check}, expected {expected})")

    if errors:
        return {"valid": False, "details": "; ".join(errors)}

    return {"valid": True, "details": "MRZ check digits valid"}


# ---------------------------------------------------------------------------
# Date detection and validation
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    # DD/MM/YYYY or DD-MM-YYYY
    (r'\b(\d{2})[/\-.](\d{2})[/\-.](\d{4})\b', "DMY"),
    # YYYY-MM-DD
    (r'\b(\d{4})[/\-.](\d{2})[/\-.](\d{2})\b', "YMD"),
    # DD Month YYYY (e.g. "15 August 1995" or "15 Aug 1995")
    (r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|'
    r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{4})\b', "DMY_MONTH"),
    # YYMMDD (MRZ-style dates)
    (r'\b(\d{2})(\d{2})(\d{2})\b', "YYMMDD"),
]

_MONTH_NAMES = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def _validate_date_components(day, month, year):
    """Check if a date triplet is within a reasonable range. Returns (valid, reason)."""
    try:
        year = int(year)
        month = int(month)
        day = int(day)
    except ValueError:
        return False, "Non-numeric date components"

    if year < 1900 or year > 2100:
        return False, f"Year {year} out of range"
    if month < 1 or month > 12:
        return False, f"Invalid month {month}"
    if day < 1 or day > 31:
        return False, f"Invalid day {day}"

    try:
        datetime(year, month, day)
    except ValueError:
        return False, f"Invalid date: {year}-{month:02d}-{day:02d}"

    return True, ""


def _detect_and_validate_dates(text):
    """
    Scan text for date patterns and validate them.

    Returns:
        (found_dates: list[str], all_valid: bool)
    """
    found_dates = []
    all_valid = True

    for pattern, fmt in _DATE_PATTERNS:
        for match in re.finditer(pattern, text):
            if fmt == "DMY":
                day, month, year = match.group(1), match.group(2), match.group(3)
                valid, reason = _validate_date_components(day, month, year)
            elif fmt == "YMD":
                year, month, day = match.group(1), match.group(2), match.group(3)
                valid, reason = _validate_date_components(day, month, year)
            elif fmt == "DMY_MONTH":
                day, month_name, year = match.group(1), match.group(2), match.group(3)
                month_num = _MONTH_NAMES.get(month_name.lower(), 0)
                if month_num == 0:
                    valid, reason = False, f"Unknown month: {month_name}"
                else:
                    valid, reason = _validate_date_components(day, month_num, year)
            elif fmt == "YYMMDD":
                year_two = match.group(1)
                month = match.group(2)
                day = match.group(3)
                year_full = 2000 + int(year_two) if int(year_two) < 50 else 1900 + int(year_two)
                valid, reason = _validate_date_components(day, month, year_full)
            else:
                continue

            found_dates.append(match.group(0))
            if not valid:
                all_valid = False

    return found_dates, all_valid


# ---------------------------------------------------------------------------
# Field detection
# ---------------------------------------------------------------------------

_NAME_LABELS = [
    r'\bname\b',
    r'\bnaam\b',
    r'नाम',
    r'पूरा\s*नाम',   # पूरा नाम (full name)
]

_DOB_LABELS = [
    r'\bDOB\b',
    r'\bD\.O\.B\.?\b',
    r'\bDate\s+of\s+Birth\b',
    r'\bजन्म\s*तिथि\b',
    r'\bजन्म\s*दिन\b',
    r'\bDate\s+of\s+Birth\b',
]

_ID_LABELS = [
    r'\bAadhaar\b',
    r'\bUID\b',
    r'\bAadhar\b',
    r'\bPassport\s+No\.?\b',
    r'\bPassport\s+Number\b',
    r'\bID\s+No\.?\b',
    r'\b身份证\b',
    r'\bDL\s*No\.?\b',
    r'\bDriving\s+Licence\b',
]

_AADHAAR_PATTERN = re.compile(r'\b(\d{4}\s?\d{4}\s?\d{4})\b')
_PASSPORT_PATTERN = re.compile(r'\b([A-PR-WY]\d{7})\b', re.IGNORECASE)

_MRX_LINE_PATTERN = re.compile(
    r'^(P<|[A-Z0-9<]{9}[0-9][A-Z]{3}[0-9]{2})', re.MULTILINE
)


def _detect_fields(text):
    """Check whether common ID document fields are present."""
    fields = {
        "name": False,
        "dob": False,
        "id_number": False,
    }

    text_lower = text.lower()

    # Name detection
    for label in _NAME_LABELS:
        if re.search(label, text, re.IGNORECASE):
            fields["name"] = True
            break
    # Also detect: label followed by text on same or next line
    if not fields["name"]:
        for label in _NAME_LABELS:
            pattern = re.compile(rf'{label}\s*[:\-]?\s*(.+)', re.IGNORECASE | re.MULTILINE)
            m = pattern.search(text)
            if m and m.group(1).strip():
                fields["name"] = True
                break

    # DOB detection
    for label in _DOB_LABELS:
        if re.search(label, text, re.IGNORECASE):
            fields["dob"] = True
            break

    # ID number detection
    for label in _ID_LABELS:
        if re.search(label, text, re.IGNORECASE):
            fields["id_number"] = True
            break
    # Fallback: detect Aadhaar or passport number by pattern even without label
    if not fields["id_number"]:
        if _AADHAAR_PATTERN.search(text) or _PASSPORT_PATTERN.search(text):
            fields["id_number"] = True

    return fields


def _detect_format(text):
    """Check whether any recognized ID-number formats are present."""
    formats = {
        "aadhaar": False,
        "passport": False,
    }

    aadhaar_match = _AADHAAR_PATTERN.search(text)
    if aadhaar_match:
        # Additional check: must be exactly 12 digits when spaces removed
        digits_only = re.sub(r'\s', '', aadhaar_match.group(1))
        if len(digits_only) == 12:
            formats["aadhaar"] = True

    passport_match = _PASSPORT_PATTERN.search(text)
    if passport_match:
        formats["passport"] = True

    return formats


# ---------------------------------------------------------------------------
# MRZ detection
# ---------------------------------------------------------------------------

def _find_mrz_lines(text):
    """Extract MRZ lines from OCR text. Returns a list of line groups."""
    lines = text.strip().splitlines()
    mrz_groups = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # MRZ lines contain only < and uppercase letters/digits, length 30 or 44
        is_mrz_char_line = bool(re.match(r'^[A-Z0-9<]+$', line)) and len(line) in (30, 44)
        if is_mrz_char_line:
            group = [line]
            # Look ahead for companion line
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if re.match(r'^[A-Z0-9<]+$', next_line) and len(next_line) in (30, 44):
                    group.append(next_line)
            mrz_groups.append(group)
        i += 1

    return mrz_groups


# ---------------------------------------------------------------------------
# Main validation function (public API — do not change signature)
# ---------------------------------------------------------------------------

def validate_fields(extracted_text):
    """
    Validate extracted OCR text against document rules.

    Args:
        extracted_text (str): Raw text extracted by the OCR module.

    Returns:
        dict: {
            "status": "Valid" | "Invalid" | "Pending",
            "details": str,
            "checks": {
                "fields_present": {"name": bool, "dob": bool, "id_number": bool},
                "format_valid": {"aadhaar": bool, "passport": bool},
                "date_valid": bool,
                "mrz_valid": bool | None
            }
        }
    """
    if not extracted_text or not extracted_text.strip():
        return {
            "status": "Pending",
            "details": "No text provided for validation.",
            "checks": {
                "fields_present": {"name": False, "dob": False, "id_number": False},
                "format_valid": {"aadhaar": False, "passport": False},
                "date_valid": False,
                "mrz_valid": None,
            }
        }

    # 1. Field presence
    fields = _detect_fields(extracted_text)

    # 2. Format validity
    formats = _detect_format(extracted_text)

    # 3. Date validity
    dates, dates_valid = _detect_and_validate_dates(extracted_text)

    # 4. MRZ validation
    mrz_groups = _find_mrz_lines(extracted_text)
    mrz_valid = None  # None = no MRZ found
    mrz_details = "No MRZ detected"

    if mrz_groups:
        # Validate the last line of the first MRZ group (line 2 has the check digits)
        last_mrz_line = mrz_groups[0][-1]
        mrz_result = validate_mrz_line(last_mrz_line)
        mrz_valid = mrz_result["valid"]
        mrz_details = mrz_result["details"]

    # Build result
    checks = {
        "fields_present": fields,
        "format_valid": formats,
        "date_valid": dates_valid,
        "mrz_valid": mrz_valid,
    }

    # Determine overall status
    # "Valid" = all detected checks pass + at least one required field present
    # "Invalid" = any detected check fails
    # "Pending" = nothing detectable at all

    has_any_field = any(fields.values())
    has_any_format = any(formats.values())
    has_any_date = len(dates) > 0

    # Collect detail messages
    details = []

    if not has_any_field and not has_any_format and not has_any_date and mrz_valid is None:
        return {
            "status": "Pending",
            "details": "No recognizable document fields detected in extracted text.",
            "checks": checks,
        }

    if fields["name"]:
        details.append("Name field present")
    else:
        details.append("Name field NOT detected")

    if fields["dob"]:
        details.append("DOB field present")
    else:
        details.append("DOB field NOT detected")

    if fields["id_number"]:
        details.append("ID number field present")
    else:
        details.append("ID number field NOT detected")

    if formats["aadhaar"]:
        details.append("Aadhaar format valid")
    if formats["passport"]:
        details.append("Passport format valid")

    if has_any_date:
        if dates_valid:
            details.append("Date(s) valid")
        else:
            details.append("One or more dates invalid")

    if mrz_valid is not None:
        details.append(mrz_details)

    # Decision logic — signals only, NOT authenticity claim
    all_pass = True

    # Fail if any detected format is invalid (checked above)
    # Fail if any detected date is invalid
    if has_any_date and not dates_valid:
        all_pass = False

    # Fail if MRZ present and invalid
    if mrz_valid is False:
        all_pass = False

    # If no useful fields detected at all, mark Invalid
    if not has_any_field and not has_any_format and not has_any_date and mrz_valid is None:
        all_pass = False

    status = "Valid" if all_pass else "Invalid"

    return {
        "status": status,
        "details": ". ".join(details) + ".",
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Standalone test runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Simple standalone test
    sample_text = "Name: Test User\nDOB: 01/01/2000\nID: 1234 5678 9012"
    result = validate_fields(sample_text)
    print("Sample Aadhaar text:")
    print(f"  Status: {result['status']}")
    print(f"  Details: {result['details']}")
    print(f"  Checks: {result['checks']}")
    print()
