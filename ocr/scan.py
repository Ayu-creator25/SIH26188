import easyocr
import sys
import os

_reader = None  # cached model, loaded once


def get_reader():
    global _reader
    if _reader is None:
        print("Loading OCR model...")
        _reader = easyocr.Reader(['en', 'hi'])
    return _reader


def scan_document(image_path):
    """
    Read the text on an ID image and return it as one string, or None if the
    file does not exist.

    Privacy: the text on an ID card is personal data (name, ID numbers,
    address). It is returned to the caller but never printed. The terminal only
    shows how many pieces of text were read and how sure the OCR was, and the
    uploaded file's name is not printed either.
    """
    if not os.path.exists(image_path):
        print("Error: the image file was not found.")
        return None

    reader = get_reader()
    print("Scanning document...")
    results = reader.readtext(image_path)

    extracted_lines = [text for (_bbox, text, _confidence) in results]
    confidences = [confidence for (_bbox, _text, confidence) in results]
    average = sum(confidences) / len(confidences) if confidences else 0.0
    print(f"  Read {len(extracted_lines)} text regions (average confidence: {average:.2f})")

    return "\n".join(extracted_lines)


if __name__ == "__main__":
    # Usage: python ocr/scan.py <image> [--show-text]
    # The text is only printed (and saved) when you ask for it, because it can
    # contain personal data.
    show_text = "--show-text" in sys.argv[1:]
    arguments = [a for a in sys.argv[1:] if a != "--show-text"]
    input_path = arguments[0] if arguments else "data/sample_id.jpg"
    output_text = scan_document(input_path)
    if output_text is not None and show_text:
        print("\n--- Extracted Text (Output) ---")
        print(output_text)
        with open("data/scan_output.txt", "w", encoding="utf-8") as f:
            f.write(output_text)
        print("\nSaved output to: data/scan_output.txt")
    elif output_text is not None:
        print("Text not shown (it can contain personal data). Add --show-text to print it.")
