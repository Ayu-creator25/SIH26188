"""
Face Verification Module
--------------------------
Compares the photo on the ID document against a live capture (webcam or
uploaded selfie) using DeepFace/face_recognition.

Expected contract (do not change without also updating backend/app.py):
    verify_face(id_photo_path: str, live_photo_path: str) -> dict
"""


def verify_face(id_photo_path, live_photo_path):
    """
    Compare the ID document photo against a live-captured photo.

    Args:
        id_photo_path (str): Path to the face image extracted from the ID.
        live_photo_path (str): Path to the live/webcam-captured photo.

    Returns:
        dict: {
            "status": "Match" | "No Match" | "Pending",
            "confidence": float,  # 0.0 - 1.0
            "details": str
        }
    """
    # TODO: implement DeepFace/face_recognition comparison
    return {
        "status": "Pending",
        "confidence": 0.0,
        "details": "Face verification not yet implemented."
    }


if __name__ == "__main__":
    result = verify_face("../data/id_face.jpg", "../data/live_face.jpg")
    print(result)