"""
ocr/test_scan_privacy.py

The text on an ID card (name, ID number, address) is personal data. These
tests make sure scan.py returns it to the app but never prints it, and never
prints the uploaded file's name either.

No OCR model is needed: a fake "easyocr" returns made-up text, the way the
real one would read a card.

Usage (from the repo root):
    pytest ocr/test_scan_privacy.py -v
"""

import runpy
import sys
import types
from pathlib import Path

import pytest

# Made-up personal details, so the tests can look for them in the terminal output.
NAME = "Rahul Testkumar"
ID_NUMBER = "1234 5678 9012"
ADDRESS = "Test Lane, Test City 828113"
READ_BY_THE_OCR = [
    ([[0, 0]], NAME, 0.90),
    ([[0, 1]], ID_NUMBER, 0.80),
    ([[0, 2]], ADDRESS, 0.70),
]
UPLOADED_NAME = "rahul_testkumar_aadhaar.jpg"
SCAN_PY = Path(__file__).resolve().parent / "scan.py"
APP_PY = Path(__file__).resolve().parent.parent / "backend" / "app.py"


@pytest.fixture()
def scan_module(monkeypatch):
    """scan.py loaded with a fake easyocr, so no model is downloaded or run."""

    class FakeReader:
        def __init__(self, languages):
            pass

        def readtext(self, image_path):
            return READ_BY_THE_OCR

    fake_easyocr = types.ModuleType("easyocr")
    fake_easyocr.Reader = FakeReader
    monkeypatch.setitem(sys.modules, "easyocr", fake_easyocr)
    monkeypatch.syspath_prepend(str(SCAN_PY.parent))
    sys.modules.pop("scan", None)  # load it again, so the model cache starts empty
    import scan
    yield scan
    sys.modules.pop("scan", None)


@pytest.fixture()
def uploaded_image(tmp_path):
    path = tmp_path / UPLOADED_NAME
    path.write_bytes(b"not a real image")
    return path


def everything_printed(capsys):
    captured = capsys.readouterr()
    return captured.out + captured.err


def test_the_text_is_still_returned_to_the_app(scan_module, uploaded_image):
    text = scan_module.scan_document(str(uploaded_image))
    assert text == f"{NAME}\n{ID_NUMBER}\n{ADDRESS}"


def test_nothing_the_ocr_reads_reaches_the_terminal(scan_module, uploaded_image, capsys):
    scan_module.scan_document(str(uploaded_image))
    printed = everything_printed(capsys)
    for secret in (NAME, "Rahul", "Testkumar", ID_NUMBER, "5678", ADDRESS, "828113"):
        assert secret not in printed


def test_the_uploaded_file_name_is_not_printed(scan_module, uploaded_image, capsys):
    scan_module.scan_document(str(uploaded_image))
    printed = everything_printed(capsys)
    assert "rahul" not in printed.lower()
    assert str(uploaded_image.parent) not in printed


def test_a_summary_with_counts_only_is_printed(scan_module, uploaded_image, capsys):
    scan_module.scan_document(str(uploaded_image))
    assert "Read 3 text regions (average confidence: 0.80)" in everything_printed(capsys)


def test_a_missing_file_message_has_no_path(scan_module, tmp_path, capsys):
    missing = tmp_path / UPLOADED_NAME
    assert scan_module.scan_document(str(missing)) is None
    printed = everything_printed(capsys)
    assert "not found" in printed
    assert "rahul" not in printed.lower()


def test_reading_nothing_returns_an_empty_string(scan_module, uploaded_image, monkeypatch, capsys):
    monkeypatch.setattr(scan_module.get_reader(), "readtext", lambda path: [])
    assert scan_module.scan_document(str(uploaded_image)) == ""
    assert "Read 0 text regions" in everything_printed(capsys)


def run_scan_from_the_command_line(monkeypatch, tmp_path, *arguments):
    (tmp_path / "data").mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)  # the command line tool saves into ./data
    monkeypatch.setattr(sys, "argv", ["scan.py", *arguments])
    runpy.run_path(str(SCAN_PY), run_name="__main__")


def test_the_command_line_hides_the_text_by_default(
        scan_module, uploaded_image, tmp_path, monkeypatch, capsys):
    run_scan_from_the_command_line(monkeypatch, tmp_path, str(uploaded_image))
    printed = everything_printed(capsys)
    assert NAME not in printed
    assert ID_NUMBER not in printed
    assert "--show-text" in printed
    assert not (tmp_path / "data" / "scan_output.txt").exists()


def test_the_command_line_shows_the_text_only_when_asked(
        scan_module, uploaded_image, tmp_path, monkeypatch, capsys):
    run_scan_from_the_command_line(monkeypatch, tmp_path, str(uploaded_image), "--show-text")
    assert NAME in everything_printed(capsys)
    assert (tmp_path / "data" / "scan_output.txt").read_text(encoding="utf-8") == (
        f"{NAME}\n{ID_NUMBER}\n{ADDRESS}"
    )


def test_the_app_never_prints_the_uploaded_file_name():
    printing_lines = [
        line for line in APP_PY.read_text(encoding="utf-8").splitlines() if "print(" in line
    ]
    assert printing_lines  # the check below must have something to look at
    assert not [line for line in printing_lines if "filename" in line]
