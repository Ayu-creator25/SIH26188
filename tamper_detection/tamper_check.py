"""
Tampering Detection Module
---------------------------
Uses Error Level Analysis (ELA) via OpenCV to flag signs of digital
tampering in the uploaded document image.

Expected contract (do not change without also updating backend/app.py):
    check_tampering(image_path: str) -> dict
"""


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
    """
    # TODO: implement ELA-based tampering detection with OpenCV
    return {
        "status": "Pending",
        "details": "Tamper detection not yet implemented."
    }


if __name__ == "__main__":
    result = check_tampering("../data/sample_id.jpg")
    print(result)