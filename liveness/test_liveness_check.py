"""
liveness/test_liveness_check.py

Manual test — runs check_liveness() against the three test images
already captured (real face, printed-photo spoof, screen-replay spoof)
to confirm the module matches the earlier smoke-test results.

Usage:
    python liveness/test_liveness_check.py
"""

from liveness_check import check_liveness

TEST_IMAGES = {
    "real face":     "data/uploads/live_live_capture.jpg",
    "printed photo": "data/uploads/spoof_test.jpg",
    "screen replay": "data/uploads/replay_test.jpg",
}

for label, path in TEST_IMAGES.items():
    result = check_liveness(path)
    print(f"{label:15s} -> {result}")