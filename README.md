# SIH26188 — AI-Based Fake Identity and Document Screening System

**Team: Think Forge** | Smart India Hackathon 2026

An AI + blockchain pipeline that screens ID documents (passport, Aadhaar, university ID, etc.) for authenticity. Every scan runs OCR extraction, field validation, tamper detection, face verification and liveness (anti-spoofing) detection, combines them into one explained verdict, and writes a zero-PII, tamper-evident audit record to a local blockchain that can be independently re-verified at any time. The dashboard is protected by a login.

---

## For evaluators — what this demonstrates

| Built and working | Not built (future scope) |
|---|---|
| OCR (EasyOCR, English + Hindi) | PDF document upload (JPG/PNG only) |
| Rule-based field validation (Aadhaar checksum, passport MRZ, dates) | Encryption at rest for uploaded images |
| Tamper detection (Error Level Analysis) | Per-teammate login accounts |
| Face match + liveness/anti-spoofing (DeepFace) | Login rate limiting / brute-force protection |
| Automatic orientation correction for sideways photos | Cloud-based (LLM) explanation layer — kept local by design |
| Explainable decision fusion with a recommended action | Smart contract / multi-node blockchain |
| Tamper-evident blockchain audit trail, **independently re-verifiable** | Public deployment (HTTPS, WSGI server) |
| Server-side login gate | Formal accuracy/false-positive evaluation on a labelled dataset |

Everything in the left column is real, running code with committed unit tests — see [Module reference](#module-reference) for exactly which test file covers which claim. Nothing in this README describes a feature that isn't in the repository.

---

## Contents

1. [How a scan works](#how-a-scan-works)
2. [Tech stack](#tech-stack)
3. [Setup](#setup-do-this-first-every-teammate)
4. [Running the dashboard](#running-the-dashboard)
5. [Live photo: face match and liveness](#live-photo-face-match-and-liveness)
6. [Automatic orientation correction](#automatic-orientation-correction)
7. [Why This Decision: explainable results](#why-this-decision-explainable-results)
8. [Blockchain integrity check and audit log](#blockchain-integrity-check-and-audit-log)
9. [Authentication](#authentication)
10. [Project structure and module ownership](#project-structure-and-module-ownership)
11. [Module reference](#module-reference)
12. [Git workflow](#git-workflow)
13. [Troubleshooting](#troubleshooting)
14. [Important rules](#important-rules)
15. [Known limitations](#known-limitations)

---

## How a scan works

**From the ID image:**
```
ID image (JPG/PNG) → Orientation fix → OCR (EasyOCR) → Validation
ID image (JPG/PNG) → Tamper detection (ELA, on the ORIGINAL file)
```

**From the optional live photo:**
```
Live photo → Face match (DeepFace + RetinaFace)
Live photo → Liveness (DeepFace anti-spoofing)
```

**Combining everything:**
```
All four check results → Decision + explanation → "Why This Decision" panel
                                                 → Blockchain audit record
                                                    (re-verifiable any time)
```

Four independent checks feed the final decision:

| Check | Module | Result shown on the dashboard |
|---|---|---|
| Validation | `validation/` | Valid / Invalid / Pending |
| Tamper Check | `tamper_detection/` | Clean / Suspicious |
| Face Match | `face_verify/` | Match / No Match / Pending |
| Liveness | `liveness/` | Live / Spoof Detected / Pending |

**Decision rule: the worst signal wins.** Each verdict also carries a recommended action — the system never auto-approves or auto-rejects a document; an officer always makes the final call.

| Overall decision | Recommended action | When |
|---|---|---|
| **High Risk** | Escalate | Any hard failure: tamper is Suspicious, validation is Invalid, face is No Match, or liveness is Spoof Detected |
| **Suspicious** | Officer review | No hard failure, but at least one check is Pending (it could not complete — for example no live photo was captured, an unsupported document type, or no face was found) |
| **Verified** | Clear | All four checks passed cleanly |

Because Face Match and Liveness both need the live photo, **a scan without a live photo can never be Verified** — it ends as Suspicious at best. See [Why This Decision](#why-this-decision-explainable-results) for how each verdict is explained.

The blockchain audit step shows **Recorded** when the record was written, or **Pending** when the local node is not reachable. A Pending ledger never blocks a scan — the check that comes after it, [integrity verification](#blockchain-integrity-check-and-audit-log), is what actually proves the record was not tampered with later.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Flask (server-rendered HTML/CSS/JS dashboard) |
| OCR | EasyOCR (English + Hindi), runs on PyTorch |
| Orientation correction | RetinaFace face-landmark geometry (no extra model — reuses the face-detection dependency) |
| Validation | Aadhaar Verhoeff checksum, passport MRZ, date checks |
| Tamper detection | Adaptive Error Level Analysis (ELA) with blob-based detection |
| Face verification | DeepFace + RetinaFace (TensorFlow) |
| Liveness / anti-spoofing | DeepFace anti-spoofing (MiniFASNet), runs on PyTorch |
| Decision fusion | Rule-based, local — no external API call, no per-scan cost |
| Audit trail | Ganache (local blockchain) + Web3.py, plain transaction, no smart contract |
| Authentication | Flask server-side session, credentials loaded from `.env` |

---

## Setup (do this first, every teammate)

1. Clone the repo:
```bash
   git clone https://github.com/Ayu-creator25/SIH26188.git
   cd SIH26188
```
2. Create your own virtual environment (never shared, never committed):
```bash
   py -3.12 -m venv venv
```
3. Activate it — **do this in every new terminal window**, before running Python, pip or pytest:
   - Git Bash: `source venv/Scripts/activate`
   - PowerShell/CMD: `venv\Scripts\activate`
   - Confirm it worked: your prompt should show `(venv)` at the start of the line.
4. Install dependencies:
```bash
   pip install -r requirements.txt
```
5. Confirm it worked: `python --version` should show `3.12.x`.
6. **Create your `.env` file** (the app will not start without it):
   - Copy the template. Git Bash: `cp .env.example .env`. PowerShell/CMD: `copy .env.example .env`
   - Generate a random secret key and paste it after `SECRET_KEY=`:
```bash
   python -c "import secrets; print(secrets.token_hex(32))"
```
   - Choose your own `AUTH_USERNAME` and `AUTH_PASSWORD`. No spaces around `=`, no quotes, and avoid `#`, `$` and spaces inside the password.
   - Check it loaded. This prints only the length of each value, never the values:
```bash
   python -c "from dotenv import dotenv_values; print({k: len(v or '') for k, v in dotenv_values('.env').items()})"
```
   You should see all three keys with non-zero lengths (`SECRET_KEY` should be 64).
7. **Start Ganache** (see [Blockchain integrity check](#blockchain-integrity-check-and-audit-log)) if you want the audit trail and integrity check to be active. The app runs without it — the ledger just shows Pending.
8. If `import cv2` fails after install, or Windows blocks a `.pyd`/`.dll` file on first run, see [Troubleshooting](#troubleshooting) — these are known, non-fatal issues, not something broken in your setup.

---

## Running the dashboard

```bash
python backend/app.py
```
Startup can take up to a minute while the AI models load.

Then open `http://127.0.0.1:5000` in your browser:

1. You are sent to the **sign-in page**. Log in with the `AUTH_USERNAME` / `AUTH_PASSWORD` from your `.env`.
2. Upload a JPG/PNG ID image (drag and drop or click). Maximum size is 10 MB.
3. Optionally capture a live photo (see [Live photo](#live-photo-face-match-and-liveness)).
4. Click **Scan Document**. The results page shows the extracted text, the four check cards, the **Why This Decision** explanation, and the blockchain audit panel.
5. Use **Audit log** in the top bar to see every past scan and its live integrity status, or **Sign out** when you are done.

The first scan is slower than later ones because models are loaded (or downloaded) on first use.

**Heads up**: this project uses both PyTorch (OCR, liveness, and orientation correction) and TensorFlow (face verification) together, so the install is large and a scan needs a fair amount of RAM.

**Blockchain**: the audit trail needs a local Ganache node running. If Ganache is not running, everything else still works and the Ledger Status shows **Pending**.

---

## Live photo: face match and liveness

On the upload page, click **Start Camera**, then **Capture Photo**. The live photo is optional, but without it the Face Match and Liveness checks stay Pending.

The one captured photo feeds **two independent checks**:

| Check | Question it answers | Module |
|---|---|---|
| Face Match | Is the person in the live photo the same person as in the ID photo? | `face_verify/` |
| Liveness | Is the live photo a real person, or a spoof (printed photo, phone/screen replay)? | `liveness/` |

### How liveness results are shown

| `is_live` returned | Dashboard shows | Meaning |
|---|---|---|
| `True` | **Live** | A real, live capture |
| `False` | **Spoof Detected** | Printed-photo or screen-replay attack. Forces the overall decision to High Risk |
| `None` | **Pending** | No face found, no live photo, or the check could not run |

The results page also shows a **Liveness check detail** line with the model confidence (0.0 to 1.0) or the reason it could not complete.

### How it works

`liveness/liveness_check.py` wraps DeepFace's built-in anti-spoofing model (MiniFASNet) with the RetinaFace detector. No custom training or model files are needed. If several faces are in the frame, the largest one is judged.

### Camera notes

- Browsers only allow camera access on `localhost` / `127.0.0.1` or over HTTPS.
- If the camera is blocked or missing, the page says so and you can still scan without it.
- For a reliable liveness reading, hold the camera at arm's length so the face and shoulders are in frame, facing a light source. A very close-up shot can occasionally be misread as a spoof.

### Testing liveness on its own

Run from the **repo root**:
```bash
python liveness/test_liveness_check.py
```
It checks three local images in `data/uploads/`: a real capture, a printed-photo spoof, and a screen-replay spoof. These are **not in the repo** (photos of faces are never committed), so capture your own with the dashboard camera, a printout and a phone screen.

---

## Automatic orientation correction

Phone photos of ID cards are frequently saved sideways (no rotation tag is set by the camera app). An OCR engine and a face detector both fail on a sideways image, which used to make a perfectly genuine document read as High Risk for the wrong reason.

`ocr/orientation.py` fixes this automatically, before OCR or face matching run:

1. Find the portrait on the uploaded ID with RetinaFace.
2. Read its landmarks. "Up" is defined as the direction from the mouth to the eyes.
3. Rotate a lossless copy of the image so the face is upright.

- OCR and Face Match use the straightened copy.
- **Tamper detection always uses the original file**, because Error Level Analysis depends on the exact original JPEG compression.
- If no face can be found, or the correction fails for any reason, the pipeline automatically falls back to the original image — a scan never fails because of this step.
- When a correction was applied, the results page shows a line under **Image preparation** explaining what was done (e.g. "the card was sideways, so it was rotated 90 degrees").

Covered by `ocr/test_orientation.py` (17 tests).

---

## Why This Decision: explainable results

Every scan's verdict comes with a **Why This Decision** panel on the results page — the same function that decides Verified / Suspicious / High Risk also generates the explanation, so the two can never disagree.

Each finding has:
- A **plain-language reason** (e.g. "The live face does not match the portrait on the document.")
- The specific **evidence** from that check (e.g. a face-distance score, or the OCR/validation detail string)
- A stable **reason code** (e.g. `FACE_NO_MATCH`, `TAMPER_SUSPICIOUS`, `VALIDATION_PENDING`) — only these short codes, never the free-text evidence, are stored in the blockchain-hashed audit record, keeping it free of document-specific detail.

If a check that hard-failed and a check that is separately Pending both apply, **both** are reported — an officer sees the complete picture, not just the most severe finding.

Implemented in `backend/explanation.py`, covered by `backend/test_explanation.py` (71 tests, including a differential test against every combination of check outcomes the dashboard can produce).

---

## Blockchain integrity check and audit log

Writing a hash to a blockchain is only meaningful if you can later prove a stored record still matches it. This system implements that full loop, not just the write:

**When a scan completes:**
1. A SHA-256 hash is made of `{document ID, timestamp, decision, check statuses, reason codes}`.
2. That hash (and only the hash) is written to Ganache.
3. The full record it was made from is stored off-chain, in `data/audit_records/` — no PII, git-ignored.

**Later, on demand** (the results page's **Verify integrity** button, `/verify/<id>`, or the **Audit log** page):
1. The stored record is re-hashed.
2. That hash is compared with the hash found in the Ganache transaction.
3. Match → 🟢 **Integrity Verified**. Mismatch → 🔴 **Tamper Detected**.

**What this proves**: the stored record has not been altered since it was written.
**What it does NOT prove**: that the scanned document itself is genuine — that is what the four checks above are for.

| Page | What it shows |
|---|---|
| Results page → **Verify integrity** button | Checks one record: recomputed hash, on-chain hash, and the transaction hash |
| **Audit log** (top nav) | Every stored scan, newest first, each with a live integrity status |

Integrity status can be:

| Status | Meaning |
|---|---|
| 🟢 Integrity Verified | The stored record matches the blockchain |
| 🔴 Tamper Detected | The stored record was edited after it was written |
| Not Found On Chain | No transaction exists for this record (e.g. the Ganache workspace was reset since the scan) |
| Ledger Offline | Ganache is not reachable right now |
| No Stored Record | No off-chain record exists for that ID |

**To see it catch a tamper attempt**: open a record's JSON file in `data/audit_records/`, edit the `decision` field, save, and refresh its `/verify/<id>` page — the status flips to Tamper Detected. Undo the edit and it flips back, with no false alarms.

Implemented in `blockchain/audit_store.py` (record storage, hashing, verification) and `blockchain/hash_record.py` (the on-chain write), covered by `blockchain/test_audit_store.py` (14 tests).

---

## Authentication

The dashboard is behind a login. The password check happens **only on the server**.

Every protected route asks one question: does the session say logged in? If yes, the route runs. If no, the visitor is redirected to `/login` — no exceptions, checked server-side on every request.

| Route | Access |
|---|---|
| `/login` | Open (shows the form, checks the submitted login) |
| `/logout` | Open (clears the session, returns to `/login`) |
| `/` | Login required |
| `/scan` | Login required |
| `/verify/<document_id>` | Login required |
| `/audit` | Login required |

**How it stays secure**

- Credentials live only in `.env` (git-ignored) and are never in the page source.
- After login the browser holds only a signed session cookie containing a logged-in flag, never the password.
- Every protected route re-checks the session on the server, so calling a route directly (browser, `curl`, a script) without logging in is refused before anything is saved.
- It fails closed: if `AUTH_USERNAME` or `AUTH_PASSWORD` is missing, nobody can log in.
- The app refuses to start if `SECRET_KEY` is missing.

**Configuration (`.env`)**

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs the session cookie so it cannot be forged. Long and random |
| `AUTH_USERNAME` | Demo login username |
| `AUTH_PASSWORD` | Demo login password |

`.env.example` is committed with placeholder values only. **Never put real values in `.env.example`**, and never commit `.env`.

**Quick self-test** (server running, no login):
```bash
curl -i -X POST http://127.0.0.1:5000/scan
```
Expected: `302 FOUND` with `Location: /login`.

---

## Project structure and module ownership

```
SIH26188/
├── auth/                  # login_required decorator + credential check
├── backend/
│   ├── app.py             # Flask app tying every module together
│   └── explanation.py     # decision fusion + plain-language "Why This Decision"
├── blockchain/
│   ├── hash_record.py     # writes the record hash to Ganache
│   └── audit_store.py     # stores the full record off-chain + re-verifies it on demand
├── dashboard/
│   ├── static/            # style.css
│   └── templates/         # index, results, login, verify, audit
├── data/                  # test images, uploads, audit records (git-ignored, never commit)
├── face_verify/           # ID photo vs. live photo matching
├── liveness/               # anti-spoofing check on the live photo
├── ocr/
│   ├── scan.py             # text extraction
│   └── orientation.py      # auto-straightens sideways ID photos
├── tamper_detection/       # ELA-based tampering checks
├── validation/              # document field validation
├── .env.example            # template for your local .env
├── requirements.txt
└── README.md
```

| Folder | Purpose | Status |
|---|---|---|
| `ocr/` | Text extraction (EasyOCR) + orientation correction | ✅ Done |
| `backend/` | Flask app + decision explanation, tying everything together | ✅ Done |
| `dashboard/` | Upload UI, results page, sign-in page, integrity check page, audit log, live webcam capture | ✅ Done |
| `validation/` | Document field validation (Aadhaar checksum, passport MRZ, dates) | ✅ Done |
| `tamper_detection/` | ELA-based tampering checks | ✅ Done |
| `face_verify/` | Face match (ID photo vs. live capture) | ✅ Done, integrated into dashboard |
| `liveness/` | Anti-spoofing check on the live capture (DeepFace + MiniFASNet) | ✅ Done, integrated into pipeline and results page |
| `blockchain/` | SHA-256 hash, Ganache audit trail, and re-verification | ✅ Done, integrated into pipeline, results page and audit log |
| `auth/` | Dashboard login (server-side session, `.env` credentials) | ✅ Done, protects every data-bearing route |
| `data/` | Test images and audit records (never commit real documents) | n/a |

> Team ownership by name has been removed from this table pending confirmation of correct spelling for all contributors — see the note at the end of this document.

---

## Module reference

`backend/app.py` calls each module with these exact signatures:

| Module file | Called as | Returns |
|---|---|---|
| `ocr/orientation.py` | `correct_orientation(id_filepath)` | Dict with `path` (image to use), `angle`, `changed`, `note` |
| `ocr/scan.py` | `scan_document(image_path)` | Extracted text (string) |
| `validation/validate.py` | `validate_fields(extracted_text)` | Dict with `status` (Valid / Invalid / Pending), `details`, `checks` |
| `tamper_detection/tamper_check.py` | `check_tampering(id_filepath)` | Dict with `status` (Clean / Suspicious), `details` |
| `face_verify/face_match.py` | `verify_face(id_filepath, live_filepath)` | Dict with `status` (MATCH / NO_MATCH / ERROR), `message` |
| `liveness/liveness_check.py` | `check_liveness(live_filepath)` | Dict with `is_live` (True / False / None), `confidence`, `error` |
| `backend/explanation.py` | `explain_decision(validation_status, tamper_status, face_match_status, liveness_status, details)` | Dict with `decision`, `action`, `action_text`, `reason_codes`, `reasons` |
| `blockchain/hash_record.py` | `create_record(document_id, result_summary)` | Dict with `tx_hash`, `record_hash`, `status` |
| `blockchain/audit_store.py` | `save_record(...)`, `verify_record(document_id)`, `list_records(limit)` | Saves/verifies/lists off-chain audit records |
| `auth/auth.py` | `check_credentials(username, password)`, `@login_required` | `True` / `False`, and a route guard |

**Don't change a function's name or its inputs/outputs** without telling the team. `backend/app.py` depends on these exact signatures.

### Running the test suite

Every module below has a committed, repeatable test file. Run all of them from the repo root:
```bash
pytest validation ocr blockchain backend -v
```
Or one file at a time, e.g.:
```bash
pytest validation/test_validate.py -v
pytest validation/test_validate_context.py -v
pytest ocr/test_orientation.py -v
pytest blockchain/test_audit_store.py -v
pytest backend/test_explanation.py -v
```
A module can also be run on its own outside pytest:
```bash
python liveness/test_liveness_check.py
python tamper_detection/test_tamper_check.py
```

---

## Git workflow

1. Before starting, sync with main:
```bash
   git checkout main
   git pull
```
2. Create your own branch (never work directly on `main`):
```bash
   git checkout -b feature/your-module-name
```
3. Commit and push as you go:
```bash
   git add <files>
   git commit -m "clear description of what changed"
   git push -u origin feature/your-module-name
```
4. When your module works, open a Pull Request on GitHub into `main`. Someone reviews, then merges.
5. Stick to your own folder. This alone avoids almost all merge conflicts. `requirements.txt` is the one shared file; if you add a package, regenerate it with `pip freeze > requirements.txt` rather than hand-editing, so nothing gets missed.

**Before every commit**, run `git status` and check that neither `.env` nor anything from `data/` is listed. Add files by name (`git add <files>`) instead of `git add .` when you are unsure.

---

## Troubleshooting

### "WinError 4551" or Windows Security says "Part of this app has been blocked"

Caused by Windows 11's **Smart App Control** blocking an unsigned native file — this has been seen on `torch`'s DLLs and on `scipy`'s `_sparsetools.pyd` (a `scikit-image` dependency used by tamper detection). It is not a bug in this project.

1. First, just dismiss the popup and try the action again (upload/scan) — in testing this has been **non-fatal**: the blocked accelerated code path is skipped and the feature still completes, just slightly slower.
2. If a feature does fail because of it: confirm you're installing the pinned versions in `requirements.txt` (`pip uninstall torch torchvision -y`, then `pip install -r requirements.txt` again), or install via conda instead:
```bash
   conda create -n sih python=3.12
   conda activate sih
   pip install -r requirements.txt
```
3. Last resort: Windows Security → App & browser control → turn off Smart App Control. **One-way toggle**, only reversible via a full Windows reset. Avoid on shared machines.

### "ModuleNotFoundError: No module named 'cv2'"

Caused by a conflict between `opencv-python` and `opencv-python-headless`. Both provide the same `cv2` module and corrupt each other's files if both get installed. `deepface` declares a dependency on plain `opencv-python`, but this project uses the headless version everywhere else. If you hit this after installing:
```bash
pip uninstall opencv-python -y
pip install opencv-python-headless --force-reinstall
```
This can recur any time `requirements.txt` is reinstalled from scratch. Just re-run the two lines above if it happens again.

### "RuntimeError: SECRET_KEY is missing. Create the .env file first."

The app could not find your `.env`. Check that it is in the **repo root** (next to `README.md`), that it is named exactly `.env` (Notepad can silently save it as `.env.txt`), and that it contains a `SECRET_KEY=` line.

### "Invalid username or password" although the login is right

- `AUTH_USERNAME` or `AUTH_PASSWORD` is missing or empty in `.env`. The app fails closed, so nobody can log in until both are set.
- Spaces around `=` or quotes around the values in `.env`.
- You edited `.env` while the server was running. Stop the server (`Ctrl+C`) and start it again.

### "Camera unavailable"

Use `http://127.0.0.1:5000` or `localhost` (browsers block cameras on other plain-HTTP addresses), allow camera access in the browser prompt, and close any other app using the camera. You can still scan without a live photo.

### Ledger Status shows "Pending", or the audit log shows "Not Found On Chain"

Ganache is not running, or it was restarted/reset since a given scan. Start Ganache and scan again — older records that predate a Ganache reset will keep showing "Not Found On Chain," which is the correct, honest status for them.

### "Address already in use" when starting the server

An old server is still running. Press `Ctrl+C` in its terminal, or close that terminal, then start again.

### `pytest: command not found`

Your virtual environment isn't active in this terminal. Run the activation command from [Setup](#setup-do-this-first-every-teammate) step 3 first — it's needed in every new terminal window.

---

## Important rules

- **Never commit real ID documents, personal data, or live-capture photos.** Use synthetic test images (MIDV-2020 dataset). Everything uploaded through the dashboard is saved to `data/uploads/`, which is git-ignored.
- **Never commit `.env`.** It holds the secret key and the login password, and it is already in `.gitignore`. A secret that reaches a commit stays in git history even after the file is deleted.
- **Only placeholders go in `.env.example`**, because that file is committed.
- **Never commit `venv/`.** It is already in `.gitignore`. Everyone creates their own locally.
- **Zero-PII on the blockchain and in the audit record.** Only a document ID, timestamp, check statuses, and reason codes are hashed and stored — never OCR text, filenames, or images.
- **Keep every route protected.** Any new route that reaches the pipeline or stored data must be wrapped with `@login_required`.

---

## Known limitations

- **No formal accuracy evaluation yet.** The system has been exercised with unit tests (see [Module reference](#module-reference)) and manual scans against sample documents, but no false-positive/false-negative rate has been measured on a labelled dataset. Treat demo outcomes as illustrative, not as a benchmarked accuracy figure.
- **One shared demo login.** There are no per-user accounts and no rate limiting on failed logins. This is fine for a local demo but must be revisited before the app is exposed publicly.
- **Development server.** `python backend/app.py` runs Flask's development server with debug on. Use it for local demos only. A public deployment should use `gunicorn` (already in `requirements.txt`), turn debug off, and mark the session cookie as Secure.
- **Blockchain is local.** The audit trail and integrity check need a Ganache node on the same machine. Without it, new scans show ledger status Pending, and existing records show integrity status "Ledger Offline" until it's running again.
- **A bare 12-digit number is only checked as an Aadhaar number when it is printed in groups (e.g. "1234 5678 9012") or the text mentions Aadhaar/UID.** This avoids false positives on other 12-digit numbers (e.g. a college registration number), at the cost of not checksum-validating a fabricated Aadhaar number typed as one unbroken run of digits with no label.
- **JPG/PNG only.** PDF upload is not implemented.
- **Windows-generated requirements.** `requirements.txt` includes Windows-only packages (`pywin32`, `win-inet-pton`), so installing on Linux hosting needs those lines removed.
- **Image quality matters.** Blurry or low-resolution scans can produce unreadable OCR text. When a check cannot complete it shows Pending and the overall decision becomes Suspicious rather than Verified — the system is deliberately conservative rather than guessing.
