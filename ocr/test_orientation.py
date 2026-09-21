"""
ocr/test_orientation.py

Tests for orientation correction. No face-detection model is needed: a tiny
synthetic "card" carries coloured marker pixels, and a fake detector reads
them the way RetinaFace would read a real face.

Usage (from the repo root):
    pytest ocr/test_orientation.py -v
"""

import numpy as np
import pytest
from PIL import Image

import orientation

WIDTH, HEIGHT = 200, 120

# Marker colours in the upright synthetic card.
RED = (255, 0, 0)      # the two eyes
BLUE = (0, 0, 255)     # the two mouth corners


def make_upright_card():
    """A white card with two red 'eyes' above two blue 'mouth corners'."""
    pixels = np.full((HEIGHT, WIDTH, 3), 255, dtype=np.uint8)
    pixels[40, 70] = RED
    pixels[40, 130] = RED
    pixels[80, 85] = BLUE
    pixels[80, 115] = BLUE
    return Image.fromarray(pixels)


def points_of(image, color):
    """Return the (x, y) positions of every pixel with an exact colour."""
    pixels = np.asarray(image.convert("RGB"))
    ys, xs = np.where((pixels == color).all(axis=2))
    return sorted(zip(xs.tolist(), ys.tolist()))


def landmark_detector(image):
    """Fake RetinaFace: confident at ANY angle, and reports landmarks."""
    eyes, mouth = points_of(image, RED), points_of(image, BLUE)
    if len(eyes) != 2 or len(mouth) != 2:
        return []
    return [{
        "score": 0.99,
        "landmarks": {
            "right_eye": eyes[0], "left_eye": eyes[1],
            "mouth_right": mouth[0], "mouth_left": mouth[1],
        },
    }]


def score_only_detector(image):
    """Fake detector with no landmarks: only fires when the card is upright."""
    eyes, mouth = points_of(image, RED), points_of(image, BLUE)
    upright = len(eyes) == 2 and len(mouth) == 2 and eyes[0][1] < mouth[0][1] and eyes[0][0] < eyes[1][0] and abs(eyes[0][1] - eyes[1][1]) < 5
    return [{"score": 0.99, "landmarks": None}] if upright else []


def rotate_point_ccw(x, y, width, height, degrees):
    """Where a pixel lands after the image is rotated counter-clockwise."""
    for _ in range(degrees // 90):
        x, y, width, height = y, width - 1 - x, height, width
    return x, y


@pytest.mark.parametrize("sideways_by", [0, 90, 180, 270])
def test_landmarks_report_the_rotation_that_fixes_the_image(sideways_by):
    upright = {"right_eye": (70, 40), "left_eye": (130, 40),
               "mouth_right": (85, 80), "mouth_left": (115, 80)}
    rotated = {name: rotate_point_ccw(x, y, WIDTH, HEIGHT, sideways_by)
               for name, (x, y) in upright.items()}
    assert orientation.rotation_to_upright(rotated) == (360 - sideways_by) % 360


def test_missing_or_ambiguous_landmarks_return_none():
    assert orientation.rotation_to_upright(None) is None
    assert orientation.rotation_to_upright({}) is None
    # Eyes and mouth at the same height: "up" is meaningless
    flat = {"right_eye": (0, 0), "left_eye": (10, 0), "mouth_right": (0, 0), "mouth_left": (10, 0)}
    assert orientation.rotation_to_upright(flat) is None
    # Tilted 45 degrees: between two right angles, so ambiguous
    tilted = {"right_eye": (0, 0), "left_eye": (0, 0), "mouth_right": (-10, 10), "mouth_left": (-10, 10)}
    assert orientation.rotation_to_upright(tilted) is None


@pytest.mark.parametrize("sideways_by", [90, 180, 270])
@pytest.mark.parametrize("detector", [landmark_detector, score_only_detector])
def test_sideways_card_is_rotated_back_exactly(tmp_path, sideways_by, detector):
    upright = make_upright_card()
    source = tmp_path / "id.png"
    upright.transpose(orientation._TRANSPOSE[sideways_by]).save(source)

    outcome = orientation.correct_orientation(str(source), detect=detector)

    assert outcome["changed"] is True
    assert outcome["angle"] == (360 - sideways_by) % 360
    assert outcome["path"].endswith("id_oriented.png")
    assert np.array_equal(np.asarray(Image.open(outcome["path"])), np.asarray(upright))
    assert "rotated" in outcome["note"]


def test_upright_card_is_left_alone(tmp_path):
    source = tmp_path / "id.png"
    make_upright_card().save(source)

    outcome = orientation.correct_orientation(str(source), detect=landmark_detector)

    assert outcome == {"path": str(source), "angle": 0, "changed": False, "note": "", "scores": {0: 0.99}}
    assert not (tmp_path / "id_oriented.png").exists()


def test_image_without_a_face_is_left_alone(tmp_path):
    source = tmp_path / "back_of_card.png"
    Image.fromarray(np.full((HEIGHT, WIDTH, 3), 255, dtype=np.uint8)).save(source)

    outcome = orientation.correct_orientation(str(source), detect=lambda image: [])

    assert outcome["changed"] is False
    assert outcome["path"] == str(source)
    assert outcome["angle"] == 0


def test_low_confidence_faces_are_ignored(tmp_path):
    source = tmp_path / "id.png"
    make_upright_card().transpose(orientation._TRANSPOSE[90]).save(source)

    weak = lambda image: [{"score": 0.5, "landmarks": None}]
    outcome = orientation.correct_orientation(str(source), detect=weak)

    assert outcome["changed"] is False


def test_original_file_is_never_modified(tmp_path):
    source = tmp_path / "id.png"
    make_upright_card().transpose(orientation._TRANSPOSE[90]).save(source)
    before = source.read_bytes()

    orientation.correct_orientation(str(source), detect=landmark_detector)

    assert source.read_bytes() == before


def test_exif_rotation_tag_is_applied(tmp_path):
    upright = make_upright_card()
    source = tmp_path / "phone.jpg"
    exif = Image.Exif()
    exif[274] = 6  # "rotate 90 degrees clockwise to view correctly"
    # Store the pixels rotated the opposite way, as a phone would.
    upright.transpose(orientation._TRANSPOSE[90]).save(source, exif=exif, quality=100)

    outcome = orientation.correct_orientation(str(source), detect=landmark_detector)

    assert outcome["changed"] is True
    assert "rotation tag" in outcome["note"]
    fixed = np.asarray(Image.open(outcome["path"])).astype(int)
    assert np.abs(fixed - np.asarray(upright).astype(int)).mean() < 10  # JPEG blur only


def test_large_images_are_searched_on_a_downscaled_copy(tmp_path):
    sizes_seen = []

    def spy(image):
        sizes_seen.append(max(image.size))
        return []

    source = tmp_path / "big.png"
    Image.fromarray(np.full((1500, 2400, 3), 255, dtype=np.uint8)).save(source)
    orientation.correct_orientation(str(source), detect=spy)

    assert sizes_seen and max(sizes_seen) <= orientation.DETECTION_MAX_SIDE
