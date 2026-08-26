import easyocr
import sys
import os

def scan_document(image_path):
    """
    Takes a path to an image, runs OCR on it,
    and returns the extracted text.
    """
    if not os.path.exists(image_path):
        print(f"Error: file not found at {image_path}")
        return None

    print("Loading OCR model... (this takes longer the first time)")
    reader = easyocr.Reader(['en', 'hi'])  # 'en' = English

    print(f"Scanning: {image_path}")
    results = reader.readtext(image_path)

    extracted_lines = []
    for (bbox, text, confidence) in results:
        print(f"  Detected: '{text}'  (confidence: {confidence:.2f})")
        extracted_lines.append(text)

    full_text = "\n".join(extracted_lines)
    return full_text


if __name__ == "__main__":
    input_path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_id.jpg"

    output_text = scan_document(input_path)

    if output_text is not None:
        print("\n--- Extracted Text (Output) ---")
        print(output_text)

        output_path = "data/scan_output.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"\nSaved output to: {output_path}")