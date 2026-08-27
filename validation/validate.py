"""
Document Validation Module
---------------------------
Takes OCR-extracted text and checks it against expected document rules
(e.g. correctly formatted ID numbers, required fields present, valid
date formats).

Expected contract (do not change without also updating backend/app.py):
    validate_fields(extracted_text: str) -> dict
"""


def validate_fields(extracted_text):
    """
    Validate extracted OCR text against document rules.

    Args:
        extracted_text (str): Raw text extracted by the OCR module.

    Returns:
        dict: {
            "status": "Valid" | "Invalid" | "Pending",
            "details": str  # short human-readable explanation
        }
    """
    # TODO: implement real validation rules
    return {
        "status": "Pending",
        "details": "Validation not yet implemented."
    }


if __name__ == "__main__":
    sample_text = "Name: Test User\nDOB: 01/01/2000\nID: 0000 0000 0000"
    result = validate_fields(sample_text)
    print(result)