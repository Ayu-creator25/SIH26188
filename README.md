# SIH26188 - AI-Based Fake Identity and Document Screening System
Team: Innovatrix

## Setup
1. Clone the repo
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `source venv/Scripts/activate` (Git Bash on Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and fill in any API keys

## Structure
- `ocr/` - Tesseract/EasyOCR text extraction
- `validation/` - document field validation
- `tamper_detection/` - ELA-based tampering checks (OpenCV)
- `face_verify/` - DeepFace/face_recognition matching
- `blockchain/` - hashing + Ganache integration
- `backend/` - Flask/FastAPI app tying modules together
- `dashboard/` - frontend
- `data/` - MIDV-2020 dataset (not tracked in git — download separately)
