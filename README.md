# SIH26188 — AI-Based Fake Identity and Document Screening System
**Team: Innovatrix** | Smart India Hackathon 2026

An AI + blockchain pipeline that screens ID documents (passport, Aadhaar, etc.) for authenticity — OCR extraction, field validation, tampering detection, and face verification, with a zero-PII blockchain audit trail.

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

---

## Running the dashboard

```bash
python backend/app.py
```
Then open `http://127.0.0.1:5000` in your browser. Upload a JPG/PNG ID image to see OCR extraction, validation, and results run end-to-end.

---

## Project structure & module ownership

| Folder | Purpose | Owner | Status |
|---|---|---|---|
| `ocr/` | Text extraction (EasyOCR, English + Hindi) | Ayush | ✅ Done |
| `backend/` | Flask app tying everything together | Ayush | ✅ Basic version done |
| `dashboard/` | Upload UI + results page | Ayush | ✅ Basic version done |
| `validation/` | Document field validation (Aadhaar checksum, passport MRZ, dates) | Ayush | ✅ Done |
| `tamper_detection/` | ELA-based tampering checks | *[Name]* | 🔲 Stub only |
| `face_verify/` | Face match (ID photo vs. live capture) | *Priyantan & Asuthosh* | 🔲 Stub only |
| `blockchain/` | SHA-256 hash + Ganache audit trail | *[Name]* | 🔲 Stub only |
| `data/` | Test images (never commit real documents) | — | — |

---

## Working on your module

Each unfinished module already has a starter file with the exact function it needs to implement — check the docstring at the top of your file for the expected inputs/outputs:

- `validation/validate.py` → `validate_fields(extracted_text)` — ✅ reference implementation, see `validation/test_validate.py` for how it's tested
- `tamper_detection/tamper_check.py` → `check_tampering(image_path)`
- `face_verify/face_match.py` → `verify_face(id_photo_path, live_photo_path)`
- `blockchain/hash_record.py` → `create_record(document_id, result_summary)`

You can run your file directly to test it standalone before it's wired into the dashboard:
```bash
python validation/test_validate.py
```

**Don't change the function name or its inputs/outputs** without telling the team — `backend/app.py` calls these exact signatures.

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
5. Stick to your own folder — this alone avoids almost all merge conflicts. `requirements.txt` is the one shared file; if you add a package, just append it.

---

## Troubleshooting: "WinError 4551 - Application Control policy has blocked this file"

Caused by Windows 11's **Smart App Control** blocking an unsigned torch DLL — not a bug in this project. Fix, in order:

1. `pip uninstall torch torchvision -y` then `pip install torch torchvision` (sometimes works, zero risk)
2. If not: install torch via conda instead (its build avoids the block), then use that environment for running the project:

   conda create -n sih python=3.12
   conda activate sih
   conda install pytorch torchvision -c pytorch
   pip install -r requirements.txt --no-deps
   pip install flask easyocr

3. Last resort: Windows Security → App & browser control → turn off Smart App Control. **One-way toggle** — only reversible via full Windows reset. Avoid on shared machines.

## Important rules

- **Never commit real ID documents or personal data.** Use synthetic test images (MIDV-2020 dataset) — see `data/` folder notes.
- **Never commit `venv/`** — it's already in `.gitignore`. Everyone creates their own locally.
- **Zero-PII on blockchain** — only hashes, timestamps, and decision outcomes go on-chain, never raw document data.