# SIH26188 — AI-Based Fake Identity and Document Screening System

**Team: Think Forge** | Smart India Hackathon 2026

An AI + blockchain pipeline that screens ID documents (passport, Aadhaar, etc.) for authenticity. Every scan runs OCR extraction, field validation, tamper detection, face verification and liveness (anti-spoofing) detection, combines them into one verdict, and writes a zero-PII audit record to a local blockchain. The dashboard is protected by a login.

---

## Contents

1. [How a scan works](#how-a-scan-works)
2. [Tech stack](#tech-stack)
3. [Setup](#setup-do-this-first-every-teammate)
4. [Running the dashboard](#running-the-dashboard)
5. [Live photo: face match and liveness](#live-photo-face-match-and-liveness)
6. [Authentication](#authentication)
7. [Project structure and module ownership](#project-structure-and-module-ownership)
8. [Module reference](#module-reference)
9. [Git workflow](#git-workflow)
10. [Troubleshooting](#troubleshooting)
11. [Important rules](#important-rules)
12. [Known limitations](#known-limitations)

---

## How a scan works

```
                        ┌─► OCR (EasyOCR) ──► Validation ───────────┐
 ID image (JPG/PNG) ────┤                                           │
                        └─► Tamper detection (ELA) ─────────────────┤
                                                                    ├─► Decision ──► Blockchain
 Live photo (optional) ─┬─► Face match (DeepFace + RetinaFace) ─────┤     fusion       audit record
                        └─► Liveness (DeepFace anti-spoofing) ──────┘
```

Four independent checks feed the final decision:

| Check | Module | Result shown on the dashboard |
|---|---|---|
| Validation | `validation/` | Valid / Invalid / Pending |
| Tamper Check | `tamper_detection/` | Clean / Suspicious |
| Face Match | `face_verify/` | Match / No Match / Pending |
| Liveness | `liveness/` | Live / Spoof Detected / Pending |

**Decision rule: the worst signal wins.**

| Overall decision | When |
|---|---|
| **High Risk** | Any hard failure: tamper is Suspicious, validation is Invalid, face is No Match, or liveness is Spoof Detected |
| **Suspicious** | No hard failure, but at least one check is Pending (it could not complete, for example no live photo was captured or no face was found) |
| **Verified** | All four checks passed cleanly |

Because Face Match and Liveness both need the live photo, **a scan without a live photo can never be Verified**. It ends as Suspicious at best.

The blockchain audit step shows **Recorded** when the record was written, or **Pending** when the local node is not reachable. A Pending ledger never blocks a scan.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Flask (server-rendered HTML/CSS/JS dashboard) |
| OCR | EasyOCR (English + Hindi), runs on PyTorch |
| Validation | Aadhaar Verhoeff checksum, passport MRZ, date checks |
| Tamper detection | Adaptive Error Level Analysis (ELA) with blob-based detection |
| Face verification | DeepFace + RetinaFace (TensorFlow) |
| Liveness / anti-spoofing | DeepFace anti-spoofing (MiniFASNet), runs on PyTorch |
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
3. Activate it:
   - Git Bash: `source venv/Scripts/activate`
   - PowerShell/CMD: `venv\Scripts\activate`
4. Install dependencies:
```bash
   pip install -r requirements.txt
```
5. Confirm it worked: `python --version` should show `3.12.x`, and your terminal prompt should show `(venv)`.
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
7. If `import cv2` fails after install, see the troubleshooting section below. It is a known conflict, not something broken in your setup.

---

## Running the dashboard

```bash
python backend/app.py
```
Startup can take up to a minute while the AI models load.

Then open `http://127.0.0.1:5000` in your browser:

1. You are sent to the **sign-in page**. Log in with the `AUTH_USERNAME` / `AUTH_PASSWORD` from your `.env`.
2. Upload a JPG/PNG ID image (drag and drop or click). Maximum size is 10 MB.
3. Optionally capture a live photo (see the next section).
4. Click **Scan Document**. The results page shows the extracted text, the four check cards, the blockchain audit panel and the overall decision.
5. Use **Sign out** in the top-right corner when you are done.

The first scan is slower than later ones because models are loaded (or downloaded) on first use.

**Heads up**: this project uses both PyTorch (OCR and liveness) and TensorFlow (face verification) together, so the install is large and a scan needs a fair amount of RAM.

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

### Testing liveness on its own

Run from the **repo root**:
```bash
python liveness/test_liveness_check.py
```
It checks three local images in `data/uploads/`: a real capture (`live_live_capture.jpg`), a printed-photo spoof (`spoof_test.jpg`) and a screen-replay spoof (`replay_test.jpg`). These are **not in the repo** (photos of faces are never committed), so capture your own with the dashboard camera, a printout and a phone screen.

---

## Authentication

The dashboard is behind a login. The password check happens **only on the server**.

```
Visitor ──► /scan ──► login_required: "session says logged in?"
                          ├─ yes ──► scan runs
                          └─ no  ──► redirected to /login
```

| Route | Access |
|---|---|
| `/login` | Open (shows the form, checks the submitted login) |
| `/logout` | Open (clears the session, returns to `/login`) |
| `/` | Login required |
| `/scan` | Login required |

**How it stays secure**

- Credentials live only in `.env` (git-ignored) and are never in the page source.
- After login the browser holds only a signed session cookie containing a logged-in flag, never the password.
- Every protected route re-checks the session on the server, so calling `/scan` directly (browser, `curl`, a script) without logging in is refused before anything is saved.
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
├── auth/              # login_required decorator + credential check
├── backend/           # Flask app (app.py) tying every module together
├── blockchain/        # SHA-256 record + Ganache audit trail
├── dashboard/
│   ├── static/        # style.css
│   └── templates/     # index.html, results.html, login.html
├── data/              # test images and uploads (git-ignored, never commit)
├── face_verify/       # ID photo vs. live photo matching
├── liveness/          # anti-spoofing check on the live photo
├── ocr/               # text extraction
├── tamper_detection/  # ELA-based tampering checks
├── validation/        # document field validation
├── .env.example       # template for your local .env
├── requirements.txt
└── README.md
```

| Folder | Purpose | Owner | Status |
|---|---|---|---|
| `ocr/` | Text extraction (EasyOCR, English + Hindi) | Ayush | ✅ Done |
| `backend/` | Flask app tying everything together | Ayush | ✅ Done. OCR, validation, tamper, face verify, liveness, blockchain and auth all wired in |
| `dashboard/` | Upload UI, results page, sign-in page, live webcam capture | Ayush | ✅ Done |
| `validation/` | Document field validation (Aadhaar checksum, passport MRZ, dates) | Ayush | ✅ Done |
| `tamper_detection/` | ELA-based tampering checks | Ashutosh | ✅ Done |
| `face_verify/` | Face match (ID photo vs. live capture) | *Priyantan & Asuthosh* | ✅ Done, integrated into dashboard |
| `liveness/` | Anti-spoofing check on the live capture (DeepFace + MiniFASNet) | Ayush | ✅ Done, integrated into pipeline and results page |
| `blockchain/` | SHA-256 hash + Ganache audit trail | Ayush | ✅ Done, integrated into pipeline and results page |
| `auth/` | Dashboard login (server-side session, `.env` credentials) | Ayush | ✅ Done, protects `/` and `/scan` |
| `data/` | Test images (never commit real documents) | n/a | n/a |

---

## Module reference

`backend/app.py` calls each module with these exact signatures:

| Module file | Called in `app.py` as | Returns |
|---|---|---|
| `ocr/scan.py` | `scan_document(id_filepath)` | Extracted text (string) |
| `validation/validate.py` | `validate_fields(extracted_text)` | Dict with `status` (Valid / Invalid), `details`, optional `checks` |
| `tamper_detection/tamper_check.py` | `check_tampering(id_filepath)` | Dict with `status` (Clean / Suspicious), `details` |
| `face_verify/face_match.py` | `verify_face(id_filepath, live_filepath)` | Dict with `status` (MATCH / NO_MATCH / ERROR), `message` |
| `liveness/liveness_check.py` | `check_liveness(live_filepath)` | Dict with `is_live` (True / False / None), `confidence` (0.0 to 1.0), `error` |
| `blockchain/hash_record.py` | `create_record(document_id, result_summary)` | Dict with `tx_hash`, `record_hash`, `status` |
| `auth/auth.py` | `check_credentials(username, password)` and `@login_required` | `True` / `False`, and a route guard |

**Don't change a function's name or its inputs/outputs** without telling the team. `backend/app.py` depends on these exact signatures.

Each module can be run on its own before it goes through the dashboard, from the repo root:
```bash
python validation/test_validate.py
python tamper_detection/test_tamper_check.py
python liveness/test_liveness_check.py
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

**Before every commit**, run `git status` and check that neither `.env` nor anything from `data/uploads/` is listed. Add files by name (`git add <files>`) instead of `git add .` when you are unsure.

---

## Troubleshooting

### "WinError 4551 - Application Control policy has blocked this file"

Caused by Windows 11's **Smart App Control** blocking an unsigned torch DLL. It is not a bug in this project. `requirements.txt` already pins `torch==2.5.1`, an older, more widely trusted build that avoids the block for most people. If you still hit this error:

1. Confirm you are actually installing from this file (not a cached newer torch): `pip uninstall torch torchvision -y`, then `pip install -r requirements.txt` again.
2. If it still fails, install via conda instead and use that environment for running the project:
```bash
   conda create -n sih python=3.12
   conda activate sih
   pip install -r requirements.txt
```
3. Last resort: Windows Security → App & browser control → turn off Smart App Control. **One-way toggle**, only reversible via a full Windows reset. Avoid on shared machines.

### "ModuleNotFoundError: No module named 'cv2'"

Caused by a conflict between `opencv-python` and `opencv-python-headless`. Both provide the same `cv2` module and corrupt each other's files if both get installed. `deepface` (used for face verification and liveness) declares a dependency on plain `opencv-python`, but this project uses the headless version everywhere else. If you hit this after installing:
```bash
pip uninstall opencv-python -y
pip install opencv-python-headless --force-reinstall
```
This can recur any time `requirements.txt` is reinstalled from scratch, since `deepface`'s own dependency declaration has not changed. Just re-run the two lines above if it happens again.

### "RuntimeError: SECRET_KEY is missing. Create the .env file first."

The app could not find your `.env`. Check that it is in the **repo root** (next to `README.md`), that it is named exactly `.env` (Notepad can silently save it as `.env.txt`), and that it contains a `SECRET_KEY=` line. Setup step 6 shows how to create it.

### "Invalid username or password" although the login is right

- `AUTH_USERNAME` or `AUTH_PASSWORD` is missing or empty in `.env`. The app fails closed, so nobody can log in until both are set.
- Spaces around `=` or quotes around the values in `.env`.
- You edited `.env` while the server was running. Stop the server (`Ctrl+C`) and start it again.

### "Camera unavailable"

Use `http://127.0.0.1:5000` or `localhost` (browsers block cameras on other plain-HTTP addresses), allow camera access in the browser prompt, and close any other app using the camera. You can still scan without a live photo.

### Ledger Status shows "Pending"

The local Ganache node is not running or not reachable. Start Ganache and scan again. All other checks are unaffected.

### "Address already in use" when starting the server

An old server is still running. Press `Ctrl+C` in its terminal, or close that terminal, then start again.

---

## Important rules

- **Never commit real ID documents, personal data, or live-capture photos.** Use synthetic test images (MIDV-2020 dataset). Everything uploaded through the dashboard is saved to `data/uploads/`, which is git-ignored.
- **Never commit `.env`.** It holds the secret key and the login password, and it is already in `.gitignore`. A secret that reaches a commit stays in git history even after the file is deleted.
- **Only placeholders go in `.env.example`**, because that file is committed.
- **Never commit `venv/`.** It is already in `.gitignore`. Everyone creates their own locally.
- **Zero-PII on blockchain.** Only hashes, timestamps and decision outcomes go on-chain, never raw document data.
- **Keep every route protected.** Any new route that reaches the pipeline or uploaded data must be wrapped with `@login_required`.

---

## Known limitations

- **One shared demo login.** There are no per-user accounts and no rate limiting on failed logins. This is fine for a local demo but must be revisited before the app is exposed publicly.
- **Development server.** `python backend/app.py` runs Flask's development server with debug on. Use it for local demos only. A public deployment should use `gunicorn` (already in `requirements.txt`), turn debug off, and mark the session cookie as Secure.
- **Blockchain is local.** The audit trail needs a Ganache node on the same machine. Without it the ledger shows Pending.
- **Windows-generated requirements.** `requirements.txt` includes Windows-only packages (`pywin32`, `win-inet-pton`), so installing on Linux hosting needs those lines removed.
- **Image quality matters.** Blurry or low-resolution scans can produce unreadable OCR text. When a check cannot complete it shows Pending and the overall decision becomes Suspicious rather than Verified.