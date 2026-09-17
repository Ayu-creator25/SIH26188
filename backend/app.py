from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
import os
import sys
import uuid

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ocr'))
from scan import scan_document

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'validation'))
from validate import validate_fields

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'face_verify'))
from face_match import verify_face

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'tamper_detection'))
from tamper_check import check_tampering

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'blockchain'))
from hash_record import create_record

app = Flask(
    __name__,
    template_folder='../dashboard/templates',
    static_folder='../dashboard/static'
)

app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'data', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png'}

FACE_STATUS_DISPLAY = {
    "MATCH": "Match",
    "NO_MATCH": "No Match",
    "ERROR": "Pending",
}


def is_allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def determine_overall_decision(validation_status, tamper_status, face_match_status):
    """
    Combine the three independent signals into one final verdict:
    Verified / Suspicious / High Risk.

    Rule: "worst signal wins". A hard failure on any check means
    High Risk. A check that couldn't be completed means Suspicious.
    Only a full clean pass on all three counts as Verified.
    """
    if tamper_status == "Suspicious":
        return "High Risk"
    if validation_status == "Invalid":
        return "High Risk"
    if face_match_status == "No Match":
        return "High Risk"

    if "Pending" in (validation_status, tamper_status, face_match_status):
        return "Suspicious"

    return "Verified"


def run_verification_pipeline(id_filepath, live_filepath):
    extracted_text = scan_document(id_filepath)
    validation_result = validate_fields(extracted_text)
    tamper_result = check_tampering(id_filepath)

    if live_filepath:
        face_result = verify_face(id_filepath, live_filepath)
        face_match_status = FACE_STATUS_DISPLAY.get(face_result["status"], "Pending")
        face_match_details = face_result["message"]
    else:
        face_match_status = "Pending"
        face_match_details = "No live photo captured."

    overall_decision = determine_overall_decision(
        validation_result["status"], tamper_result["status"], face_match_status
    )

    # Zero-PII blockchain audit trail: a fresh random ID (never the real
    # filename or document number) plus only the decision outcomes go
    # on-chain. If Ganache isn't reachable, degrade gracefully instead of
    # failing the whole scan over an audit-trail hiccup.
    document_id = str(uuid.uuid4())
    try:
        blockchain_result = create_record(document_id, {
            "decision": overall_decision,
            "validation_status": validation_result["status"],
            "tamper_status": tamper_result["status"],
            "face_match_status": face_match_status,
        })
    except Exception as e:
        print(f"Blockchain recording failed: {e}")
        blockchain_result = {"tx_hash": None, "record_hash": None, "status": "Pending"}

    return {
        "document_id": document_id,
        "extracted_text": extracted_text,
        "validation_status": validation_result["status"],
        "validation_details": validation_result["details"],
        "validation_checks": validation_result.get("checks", {}),
        "tamper_status": tamper_result["status"],
        "tamper_details": tamper_result["details"],
        "face_match_status": face_match_status,
        "face_match_details": face_match_details,
        "overall_decision": overall_decision,
        "blockchain_tx_hash": blockchain_result["tx_hash"],
        "blockchain_record_hash": blockchain_result["record_hash"],
        "blockchain_status": blockchain_result["status"],
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

    live_filepath = None
    live_file = request.files.get('live_photo')
    if live_file and live_file.filename != '' and is_allowed_file(live_file.filename):
        live_filename = "live_" + secure_filename(live_file.filename)
        live_filepath = os.path.join(UPLOAD_FOLDER, live_filename)
        live_file.save(live_filepath)

    try:
        pipeline_result = run_verification_pipeline(filepath, live_filepath)
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