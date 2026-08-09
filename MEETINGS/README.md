# MEETINGS Module

> A self-contained module of **Corporate Brain**. Give this folder to any team member — they can run the full meeting intelligence pipeline independently.

## What it does

Upload a meeting video (MP4, MKV, MOV) or audio (MP3, WAV, M4A):

1. **Audio extraction** — ffmpeg strips the audio track to 16kHz mono WAV
2. **Speaker diarization** — PyAnnote 3.1 identifies who is speaking when
3. **Transcription** — Whisper converts speech to timestamped text
4. **Speaker alignment** — each transcript segment is labeled with a speaker
5. **Gemini Vision** — samples video frames every 10s, reads participant nameplates
6. **Name mapping** — SPEAKER_01 → "Sarah Park" using Vision + transcript context
7. **Gemini Analysis** — extracts decisions (with confidence), action items, and flags contradictions against organizational history
8. **Dashboard** — interactive `index.html` with searchable transcript, decisions, actions, and flags

---

## Quick Start

### 1. Copy environment file
```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY and HF_TOKEN
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

> **Note:** `torch` and `openai-whisper` are large downloads (~2GB for small model). Run once.

### 3. Start the API
```bash
# From the CorporateBrain root directory:
uvicorn MEETINGS.api:app --reload --port 8100
```

### 4. Open the dashboard
Visit **http://localhost:8100** — the dashboard is served automatically.

---

## Demo Mode (no API keys needed)
```env
DEMO_MODE=true
```
Runs a simulated pipeline with realistic dummy data so you can see the UI and API without spending API credits.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload` | Upload video/audio file → returns `job_id` |
| `GET`  | `/api/status/{job_id}` | Poll pipeline progress (0–100%) |
| `GET`  | `/api/meetings` | List all processed meetings |
| `GET`  | `/api/meeting/{job_id}` | Full meeting result |
| `DELETE` | `/api/meeting/{job_id}` | Delete a meeting |
| `GET`  | `/api/health` | Health check + config status |
| `GET`  | `/docs` | Interactive API docs (Swagger UI) |

---

## Folder Structure

```
MEETINGS/
├── api.py              ← FastAPI app (all endpoints + security)
├── pipeline.py         ← Full processing pipeline (coco2.py reorganized)
├── config.py           ← All settings from .env (no hardcoded secrets)
├── schemas.py          ← Pydantic data models
├── storage.py          ← JSON file persistence layer
├── index.html          ← Dashboard UI (served at /)
├── requirements.txt    ← All Python dependencies
├── .env.example        ← Template for environment variables
├── uploads/            ← Uploaded files (auto-created)
└── results/            ← Processed meeting JSON files (auto-created)
```

---

## Pre-requisites

- **Python 3.10+**
- **ffmpeg** — must be in PATH (`winget install ffmpeg` on Windows)
- **HuggingFace token** — accept PyAnnote model license at https://huggingface.co/pyannote/speaker-diarization-3.1
- **Gemini API key** — from https://aistudio.google.com/app/apikey
- **GPU recommended** — PyAnnote + Whisper are much faster on CUDA, but CPU works

---

## Security Notes

- All secrets live in `.env` — never committed to git
- File type whitelist: only video/audio MIME types accepted
- File size limit: 500MB (configurable)
- Path traversal protection on all `job_id` inputs
- CORS restricted to `FRONTEND_URL` in production
