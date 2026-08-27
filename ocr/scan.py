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
    if not os.path.exists(image_path):
        print(f"Error: file not found at {image_path}")
        return None

    reader = get_reader()
    print(f"Scanning: {image_path}")
    results = reader.readtext(image_path)

    extracted_lines = []
    for (bbox, text, confidence) in results:
        print(f"  Detected: '{text}'  (confidence: {confidence:.2f})")
        extracted_lines.append(text)

    return "\n".join(extracted_lines)


if __name__ == "__main__":
    input_path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_id.jpg"
    output_text = scan_document(input_path)
    if output_text is not None:
        print("\n--- Extracted Text (Output) ---")
        print(output_text)
        with open("data/scan_output.txt", "w", encoding="utf-8") as f:
            f.write(output_text)
        print("\nSaved output to: data/scan_output.txt")