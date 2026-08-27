# AI Assistant Handoff — SIH26188

If you're using an AI assistant (Claude, ChatGPT, etc.) to help build your module,
most AI chat tools **cannot access a private GitHub repo directly** — so instead
of just sharing the repo link, paste in the actual content below.

---

## Step 1: Copy this entire file into your first message to the AI

## Step 2: Also paste in two more things

1. **The project README.md** — open `README.md` in this repo, copy all of it, paste it into the chat.
2. **Your module's starter file** — open the `.py` file for whichever folder you're assigned
   (e.g. `validation/validate.py`), copy all of it, paste it in too.

## Step 3: Use this prompt template
I'm working on a hackathon project (SIH26188 — an AI-based fake identity and
document screening system for SIH 2026). My team already has a working GitHub
repo with a completed OCR module and a basic dashboard. I've been assigned to
build the [MODULE NAME] module — e.g. validation, tamper_detection,
face_verify, or blockchain.

Here's our project README:
[paste README.md content here]

Here's the starter file I need to implement:
[paste your module's .py file content here]

Please help me:

Understand exactly what this module needs to do and how it fits the pipeline
Create my own git branch for this (feature/[module-name])
Implement the function step-by-step, explaining as we go
Test it locally before I commit
Commit, push, and open a pull request into main when it's done
I'm on Windows, using [Git Bash / PowerShell], Python 3.12, with my own venv
already set up per the README.


---

## Before you paste anything — important

- **Never upload or paste real ID documents, personal photos, Aadhaar numbers,
  or any other real personal data into an AI chat.** Use synthetic test images
  only — ask the team for the shared test dataset (MIDV-2020 samples).
- If your module needs a sample image to test against, use a placeholder/
  synthetic file, not a real one.

## Why this file exists

Instead of everyone re-explaining the whole project from scratch to their AI
assistant, or trying to share a private repo link that most tools can't open,
paste this file + the README + your module's stub. That's enough for any
capable AI to understand exactly where the project stands and pick up your
part correctly — same branch-per-module workflow, same function contracts,
no drift from what the rest of the team is doing.