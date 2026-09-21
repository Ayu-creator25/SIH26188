from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ocr'))
from scan import scan_document
from orientation import correct_orientation

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'validation'))
from validate import validate_fields

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'face_verify'))
from face_match import verify_face

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'tamper_detection'))
from tamper_check import check_tampering

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'blockchain'))
from hash_record import create_record
from audit_store import get_w3, list_records, save_record, verify_record

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'liveness'))
from liveness_check import check_liveness

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'auth'))
from auth import check_credentials, login_required

app = Flask(
    __name__,
    template_folder='../dashboard/templates',
    static_folder='../dashboard/static'
)

app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB
# Key used to sign the session cookie (loaded from .env by auth.py).
# Fail loudly at startup instead of crashing later on the first login.
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError("SECRET_KEY is missing. Create the .env file first.")

# Stops other websites from sending our cookie with cross-site requests.
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'data', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png'}

FACE_STATUS_DISPLAY = {
    "MATCH": "Match",
    "NO_MATCH": "No Match",
    "ERROR": "Pending",
}

LIVENESS_STATUS_DISPLAY = {
    True: "Live",
    False: "Spoof Detected",
    None: "Pending",
}


def is_allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def determine_overall_decision(validation_status, tamper_status, face_match_status, liveness_status):
    """
    Combine the four independent signals into one final verdict:
    Verified / Suspicious / High Risk.

    Rule: "worst signal wins". A hard failure on any check means
    High Risk. A check that couldn't be completed means Suspicious.
    Only a full clean pass on all four counts as Verified.
    """
    if tamper_status == "Suspicious":
        return "High Risk"
    if validation_status == "Invalid":
        return "High Risk"
    if face_match_status == "No Match":
        return "High Risk"
    if liveness_status == "Spoof Detected":
        return "High Risk"

    if "Pending" in (validation_status, tamper_status, face_match_status, liveness_status):
        return "Suspicious"

    return "Verified"


def run_verification_pipeline(id_filepath, live_filepath):
    # Phone photos of ID cards are often sideways. Straighten the card first so
    # OCR and face matching see it upright. Tamper detection keeps the ORIGINAL
    # file, because error level analysis depends on its original compression.
    try:
        orientation = correct_orientation(id_filepath)
    except Exception as e:
        print(f"Orientation correction failed: {e}")
        orientation = {"path": id_filepath, "note": ""}
    working_filepath = orientation["path"]

    extracted_text = scan_document(working_filepath)
    validation_result = validate_fields(extracted_text)
    tamper_result = check_tampering(id_filepath)

    if live_filepath:
        try:
            liveness_result = check_liveness(live_filepath)
            liveness_status = LIVENESS_STATUS_DISPLAY.get(liveness_result["is_live"], "Pending")
            liveness_details = liveness_result["error"] or f"Confidence: {liveness_result['confidence']}"
        except Exception as e:
            print(f"Liveness check failed: {e}")
            liveness_status = "Pending"
            liveness_details = "Liveness check could not be completed."

        face_result = verify_face(working_filepath, live_filepath)
        face_match_status = FACE_STATUS_DISPLAY.get(face_result["status"], "Pending")
        face_match_details = face_result["message"]
    else:
        liveness_status = "Pending"
        liveness_details = "No live photo captured."
        face_match_status = "Pending"
        face_match_details = "No live photo captured."

    overall_decision = determine_overall_decision(
        validation_result["status"], tamper_result["status"], face_match_status, liveness_status
    )

    document_id = str(uuid.uuid4())

    # This exact dict is hashed onto the blockchain AND saved off-chain, so the
    # record can be re-hashed later to prove it was not altered. No PII in it.
    record_summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "decision": overall_decision,
        "validation_status": validation_result["status"],
        "tamper_status": tamper_result["status"],
        "face_match_status": face_match_status,
        "liveness_status": liveness_status,
    }
    try:
        blockchain_result = create_record(document_id, record_summary)
    except Exception as e:
        print(f"Blockchain recording failed: {e}")
        blockchain_result = {"tx_hash": None, "record_hash": None, "status": "Pending"}

    if blockchain_result["status"] == "Recorded":
        try:
            save_record(
                document_id,
                record_summary,
                blockchain_result["tx_hash"],
                blockchain_result["record_hash"],
            )
        except Exception as e:
            # The scan still succeeds, but this record cannot be verified later.
            print(f"Saving the audit record failed: {e}")

    return {
        "document_id": document_id,
        "orientation_note": orientation.get("note", ""),
        "extracted_text": extracted_text,
        "validation_status": validation_result["status"],
        "validation_details": validation_result["details"],
        "validation_checks": validation_result.get("checks", {}),
        "tamper_status": tamper_result["status"],
        "tamper_details": tamper_result["details"],
        "face_match_status": face_match_status,
        "face_match_details": face_match_details,
        "liveness_status": liveness_status,
        "liveness_details": liveness_details,
        "overall_decision": overall_decision,
        "blockchain_tx_hash": blockchain_result["tx_hash"],
        "blockchain_record_hash": blockchain_result["record_hash"],
        "blockchain_status": blockchain_result["status"],
    }


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Show the login form (GET) or check the submitted login (POST)."""
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if check_credentials(username, password):
            session.clear()  # start from a fresh session
            session['logged_in'] = True  # only a flag, never the password
            return redirect(url_for('index'))
        return render_template(
            'login.html', error="Invalid username or password."
        ), 401
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Clear the session and send the user back to the login page."""
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/scan', methods=['POST'])
@login_required
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


@app.route('/verify/<document_id>')
@login_required
def verify(document_id):
    """Re-hash one stored record and compare it with the blockchain."""
    return render_template(
        'verify.html', document_id=document_id, result=verify_record(document_id)
    )


@app.route('/audit')
@login_required
def audit():
    """List recent records, each checked against the blockchain."""
    records = list_records(limit=25)
    try:
        w3 = get_w3()
    except Exception:
        w3 = None  # verify_record() reports "Ledger Offline" for each row
    for record in records:
        record["verification"] = verify_record(record["document_id"], w3=w3)
    return render_template('audit.html', records=records)


if __name__ == '__main__':
    app.run(debug=True)