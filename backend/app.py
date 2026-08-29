from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ocr'))
from scan import scan_document

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'validation'))
from validate import validate_fields

app = Flask(
    __name__,
    template_folder='../dashboard/templates',
    static_folder='../dashboard/static'
)

app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'data', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png'}


def is_allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def run_verification_pipeline(filepath):
    extracted_text = scan_document(filepath)
    validation_result = validate_fields(extracted_text)

    return {
        "extracted_text": extracted_text,
        "validation_status": validation_result["status"],
        "validation_details": validation_result["details"],
        "validation_checks": validation_result.get("checks", {}),
        "tamper_status": "Pending",
        "face_match_status": "Pending",
        "overall_decision": "Pending Review",
    }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/scan', methods=['POST'])
def scan():
    file = request.files.get('document')

    if not file or file.filename == '':
        return render_template('index.html', error="No file selected.")

    if not is_allowed_file(file.filename):
        return render_template('index.html', error="Only JPG and PNG images are supported.")

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        pipeline_result = run_verification_pipeline(filepath)
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return render_template(
            'index.html',
            error="Could not process this file. Please upload a valid, undamaged JPG or PNG image."
        )

    pipeline_result["filename"] = filename
    return render_template('results.html', result=pipeline_result)


if __name__ == '__main__':
    app.run(debug=True)