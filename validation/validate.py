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
# Digit normalization (EasyOCR sometimes mixes Devanagari digits into
# otherwise-English fields, e.g. "DOB: 1९/11/२००६")
# ---------------------------------------------------------------------------

_DEVANAGARI_DIGITS = str.maketrans('०१२३४५६७८९', '0123456789')


def _normalize_digits(text):
    return text.translate(_DEVANAGARI_DIGITS)


# ---------------------------------------------------------------------------
# Verhoeff checksum (used for Aadhaar numbers)
# ---------------------------------------------------------------------------

_VERHOEFF_D = [
    [0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],
    [3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],
    [6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],
    [9,8,7,6,5,4,3,2,1,0],
]
_VERHOEFF_P = [
    [0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],
    [8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],
    [2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8],
]


def _verhoeff_valid(number_str):
    c = 0
    for i, digit in enumerate(reversed(number_str)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(digit)]]
    return c == 0


# ---------------------------------------------------------------------------
# MRZ check-digit utility (used for passports)
# ---------------------------------------------------------------------------

_MRZ_WEIGHTS = [7, 3, 1]


def _mrz_check_digit(char):
    if char.isdigit():
        return int(char)
    if char.isalpha():
        return ord(char.upper()) - ord('A') + 10
    if char == '<':
        return 0
    return 0


def _mrz_calculate_check_digit(data):
    total = 0
    for i, ch in enumerate(data):
        total += _mrz_check_digit(ch) * _MRZ_WEIGHTS[i % 3]
    return total % 10


def validate_mrz_line(mrz_line):
    """
    Validate a single TD3 MRZ line (44 chars, passport line 2).
    Returns dict with keys: valid (bool), details (str)
    """
    line = mrz_line.strip()
    length = len(line)

    if length != 44:
        return {"valid": False, "details": f"MRZ line has unexpected length {length} (expected 44)"}

    passport_field = line[0:9]
    passport_check = int(line[9]) if line[9].isdigit() else -1
    dob_field = line[13:19]
    dob_check = int(line[19]) if line[19].isdigit() else -1
    expiry_field = line[21:27]
    expiry_check = int(line[27]) if line[27].isdigit() else -1
    personal_field = line[28:42]
    personal_check = int(line[42]) if line[42].isdigit() else -1
    overall_check = int(line[43]) if line[43].isdigit() else -1

    errors = []

    if dob_check >= 0:
        expected = _mrz_calculate_check_digit(dob_field)
        if dob_check != expected:
            errors.append(f"DOB check digit mismatch (got {dob_check}, expected {expected})")

    if expiry_check >= 0:
        expected = _mrz_calculate_check_digit(expiry_field)
        if expiry_check != expected:
            errors.append(f"Expiry check digit mismatch (got {expiry_check}, expected {expected})")

    if passport_check >= 0:
        expected = _mrz_calculate_check_digit(passport_field)
        if passport_check != expected:
            errors.append(f"Passport number check digit mismatch (got {passport_check}, expected {expected})")

    if overall_check >= 0:
        composite = line[0:10] + line[13:20] + line[21:43]
        expected = _mrz_calculate_check_digit(composite)
        if overall_check != expected:
            errors.append(f"Overall check digit mismatch (got {overall_check}, expected {expected})")

    if errors:
        return {"valid": False, "details": "; ".join(errors)}

    return {"valid": True, "details": "MRZ check digits valid"}


# ---------------------------------------------------------------------------
# Date detection and validation
#
# NOTE: a bare 6-digit "YYMMDD" pattern was intentionally removed. It
# matched things like PIN codes (e.g. "828113") and misread them as
# invalid dates (month 81), incorrectly flagging valid documents.
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    (r'\b(\d{2})[/\-.](\d{2})[/\-.](\d{4})\b', "DMY"),
    (r'\b(\d{4})[/\-.](\d{2})[/\-.](\d{2})\b', "YMD"),
    (r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|'
     r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{4})\b', "DMY_MONTH"),
]

_MONTH_NAMES = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def _validate_date_components(day, month, year):
    try:
        year, month, day = int(year), int(month), int(day)
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
    found_dates = []
    all_valid = True

    for pattern, fmt in _DATE_PATTERNS:
        for match in re.finditer(pattern, text):
            if fmt == "DMY":
                day, month, year = match.group(1), match.group(2), match.group(3)
                valid, _ = _validate_date_components(day, month, year)
            elif fmt == "YMD":
                year, month, day = match.group(1), match.group(2), match.group(3)
                valid, _ = _validate_date_components(day, month, year)
            elif fmt == "DMY_MONTH":
                day, month_name, year = match.group(1), match.group(2), match.group(3)
                month_num = _MONTH_NAMES.get(month_name.lower(), 0)
                valid = False if month_num == 0 else _validate_date_components(day, month_num, year)[0]
            else:
                continue

            found_dates.append(match.group(0))
            if not valid:
                all_valid = False

    return found_dates, all_valid


# ---------------------------------------------------------------------------
# Field detection
# ---------------------------------------------------------------------------

_NAME_LABELS = [r'\bname\b', r'\bnaam\b', r'नाम', r'पूरा\s*नाम']
_DOB_LABELS = [r'\bDOB\b', r'\bD\.O\.B\.?\b', r'\bDate\s+of\s+Birth\b', r'जन्म\s*तिथि', r'जन्म\s*दिन']
_ID_LABELS = [
    r'\bAadhaar\b', r'\bUID\b', r'\bAadhar\b', r'\bPassport\s+No\.?\b',
    r'\bPassport\s+Number\b', r'\bID\s+No\.?\b', r'\bDL\s*No\.?\b', r'\bDriving\s+Licence\b',
]

_AADHAAR_PATTERN = re.compile(r'\b(\d{4}\s?\d{4}\s?\d{4})\b')
_PASSPORT_PATTERN = re.compile(r'\b([A-PR-WY]\d{7})\b', re.IGNORECASE)

# Aadhaar numbers are printed in groups ("1234 5678 9012"). A bare run of 12
# digits - a college registration number, a phone number with country code -
# is only treated as an Aadhaar candidate when the text also mentions Aadhaar
# or UID. Without this, any ID that carries a 12-digit number of its own would
# be flagged as an Aadhaar that "failed its checksum".
_AADHAAR_CUES = re.compile(r'aadhaar|aadhar|\bUID(?:AI)?\b|आधार', re.IGNORECASE)


def _find_aadhaar_number(text):
    """Return the first Aadhaar-shaped regex match in the text, or None."""
    has_cue = bool(_AADHAAR_CUES.search(text))
    for match in _AADHAAR_PATTERN.finditer(text):
        is_grouped = bool(re.search(r'\s', match.group(1)))
        if is_grouped or has_cue:
            return match
    return None


def _detect_fields(text):
    fields = {"name": False, "dob": False, "id_number": False}

    for label in _NAME_LABELS:
        if re.search(label, text, re.IGNORECASE):
            fields["name"] = True
            break

    # Fallback: many real ID cards (e.g. Aadhaar) print the name directly
    # with no "Name:"/"नाम:" label at all.
    if not fields["name"]:
        for line in text.splitlines():
            words = re.findall(r'[^\W\d_]{2,}', line, re.UNICODE)
            if len(words) >= 2:
                fields["name"] = True
                break

    for label in _DOB_LABELS:
        if re.search(label, text, re.IGNORECASE):
            fields["dob"] = True
            break

    for label in _ID_LABELS:
        if re.search(label, text, re.IGNORECASE):
            fields["id_number"] = True
            break
    if not fields["id_number"]:
        if _find_aadhaar_number(text) or _PASSPORT_PATTERN.search(text):
            fields["id_number"] = True

    return fields


def _detect_format(text):
    """
    Returns (formats: dict, aadhaar_candidate_found: bool).
    aadhaar_candidate_found is True whenever a 12-digit Aadhaar-shaped
    number exists, regardless of checksum validity - this lets the caller
    tell "no Aadhaar number here" apart from "a fabricated one is here".
    """
    formats = {"aadhaar": False, "passport": False}
    aadhaar_candidate_found = False

    aadhaar_match = _find_aadhaar_number(text)
    if aadhaar_match:
        digits_only = re.sub(r'\s', '', aadhaar_match.group(1))
        if len(digits_only) == 12:
            aadhaar_candidate_found = True
            if _verhoeff_valid(digits_only):
                formats["aadhaar"] = True

    passport_match = _PASSPORT_PATTERN.search(text)
    if passport_match:
        formats["passport"] = True

    return formats, aadhaar_candidate_found


# ---------------------------------------------------------------------------
# MRZ detection
# ---------------------------------------------------------------------------

def _find_mrz_lines(text):
    lines = text.strip().splitlines()
    mrz_groups = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if bool(re.match(r'^[A-Z0-9<]+$', line)) and len(line) in (30, 44):
            group = [line]
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if re.match(r'^[A-Z0-9<]+$', next_line) and len(next_line) in (30, 44):
                    group.append(next_line)
            mrz_groups.append(group)
        i += 1
    return mrz_groups


# ---------------------------------------------------------------------------
# Main validation function (public API - do not change signature)
# ---------------------------------------------------------------------------

def validate_fields(extracted_text):
    """
    Validate extracted OCR text against document rules. Provides signals
    only - this does NOT determine document authenticity on its own.
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

    text = _normalize_digits(extracted_text)

    fields = _detect_fields(text)
    formats, aadhaar_candidate_found = _detect_format(text)
    dates, dates_valid = _detect_and_validate_dates(text)

    mrz_groups = _find_mrz_lines(text)
    mrz_valid = None
    mrz_details = "No MRZ detected"
    if mrz_groups:
        mrz_result = validate_mrz_line(mrz_groups[0][-1])
        mrz_valid = mrz_result["valid"]
        mrz_details = mrz_result["details"]

    checks = {
        "fields_present": fields,
        "format_valid": formats,
        "date_valid": dates_valid,
        "mrz_valid": mrz_valid,
    }

    has_any_format = any(formats.values())
    has_any_date = len(dates) > 0
    aadhaar_checksum_failed = aadhaar_candidate_found and not formats["aadhaar"]

    # A bare name-fallback match alone isn't strong enough evidence that
    # this is really an ID document - almost any sentence has 2+ words.
    # dob/id_number/format/date/MRZ signals are what actually justify
    # rendering a verdict; a name-only match still routes to "Pending".
    has_meaningful_signal = (
        fields["dob"] or fields["id_number"] or has_any_format
        or has_any_date or mrz_valid is not None or aadhaar_candidate_found
    )

    if not has_meaningful_signal:
        return {
            "status": "Pending",
            "details": "No recognizable document fields detected in extracted text.",
            "checks": checks,
        }

    details = []
    details.append("Name field present" if fields["name"] else "Name field NOT detected")
    details.append("DOB field present" if fields["dob"] else "DOB field NOT detected")
    details.append("ID number field present" if fields["id_number"] else "ID number field NOT detected")

    if formats["aadhaar"]:
        details.append("Aadhaar checksum valid")
    if aadhaar_checksum_failed:
        details.append("Aadhaar number found but FAILED checksum validation")
    if formats["passport"]:
        details.append("Passport format valid")
    if has_any_date:
        details.append("Date(s) valid" if dates_valid else "One or more dates invalid")
    if mrz_valid is not None:
        details.append(mrz_details)

    all_pass = True
    if has_any_date and not dates_valid:
        all_pass = False
    if mrz_valid is False:
        all_pass = False
    if aadhaar_checksum_failed:
        all_pass = False

    return {
        "status": "Valid" if all_pass else "Invalid",
        "details": ". ".join(details) + ".",
        "checks": checks,
    }


if __name__ == "__main__":
    sample_text = "Name: Test User\nDOB: 01/01/2000\nAadhaar: 9999 9999 9999"
    result = validate_fields(sample_text)
    print("Sample Aadhaar text:")
    print(f"  Status: {result['status']}")
    print(f"  Details: {result['details']}")
    print(f"  Checks: {result['checks']}")