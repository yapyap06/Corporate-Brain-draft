"""
api.py — FastAPI application for the MEETINGS module.

Endpoints:
  POST   /api/upload            Upload video/audio → start processing job
  GET    /api/status/{job_id}   Poll pipeline progress (step + %)
  GET    /api/meetings          List all processed meetings
  GET    /api/meeting/{job_id}  Full meeting result
  DELETE /api/meeting/{job_id}  Delete a meeting
  GET    /api/health            Health + config check
  GET    /                      Serve index.html dashboard

Run:
  uvicorn MEETINGS.api:app --reload --port 8100
"""
import uuid
import logging
import mimetypes
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI, UploadFile, File, HTTPException,
    BackgroundTasks, Request
)
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from MEETINGS.config  import settings
from MEETINGS.schemas import (
    UploadResponse, JobStatus, MeetingResult,
    MeetingListItem, PipelineStep
)
from MEETINGS.storage import (
    load_status, load_result, list_meetings,
    delete_meeting, set_step, now_iso
)
from MEETINGS.pipeline import run_full_pipeline

logger = logging.getLogger(__name__)

# ── Allowed file types (security: whitelist) ──────────────────────────
ALLOWED_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm",   # Video
    ".mp3", ".wav", ".m4a", ".ogg", ".flac",   # Audio
}
ALLOWED_MIME_TYPES = {
    "video/mp4", "video/x-matroska", "video/quicktime",
    "video/x-msvideo", "video/webm",
    "audio/mpeg", "audio/wav", "audio/x-wav",
    "audio/mp4", "audio/ogg", "audio/flac",
    "audio/x-m4a", "application/octet-stream",   # Fallback for some clients
}

MAX_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024


# ── App lifespan ──────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )
    logger.info("=" * 60)
    logger.info("  MEETINGS API starting up")
    logger.info(f"  DEMO_MODE   = {settings.DEMO_MODE}")
    logger.info(f"  GEMINI_KEY  = {'SET' if settings.GEMINI_API_KEY else 'NOT SET'}")
    logger.info(f"  HF_TOKEN    = {'SET' if settings.HF_TOKEN else 'NOT SET'}")
    logger.info(f"  WHISPER     = {settings.WHISPER_MODEL}")
    logger.info(f"  UPLOAD_DIR  = {settings.UPLOAD_DIR}")
    logger.info(f"  RESULTS_DIR = {settings.RESULTS_DIR}")
    logger.info("=" * 60)

    # Warn about missing config (don't hard-fail — demo mode is fine)
    errors = settings.validate()
    for e in errors:
        logger.warning(f"  CONFIG: {e}")

    yield

    logger.info("MEETINGS API shutting down")


# ── App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "Corporate Brain — MEETINGS API",
    description = "Upload video/audio meetings → PyAnnote diarization + Whisper transcription + Gemini intelligence extraction",
    version     = "1.0.0",
    lifespan    = lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = settings.ALLOWED_ORIGINS + ["*"],  # Restrict in production
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ── Dashboard (serve index.html) ──────────────────────────────────────
_HERE = Path(__file__).parent

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """Serve the Meetings dashboard UI."""
    index = _HERE / "index.html"
    if index.exists():
        return HTMLResponse(content=index.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>index.html not found in MEETINGS folder.</h2>", status_code=404)


# ── Health ────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {
        "status":      "ok",
        "demo_mode":   settings.DEMO_MODE,
        "gemini_key":  bool(settings.GEMINI_API_KEY),
        "hf_token":    bool(settings.HF_TOKEN),
        "whisper":     settings.WHISPER_MODEL,
        "meetings":    len(list(settings.RESULTS_DIR.glob("*.json")) if settings.RESULTS_DIR.exists() else []),
    }


# ── Upload ────────────────────────────────────────────────────────────
@app.post("/api/upload", response_model=UploadResponse)
async def upload_meeting(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload a video or audio file.
    - Validates file type and size
    - Saves to uploads/ with a unique job_id filename
    - Starts the pipeline in the background
    - Returns immediately with job_id for polling
    """
    # ── Validate extension ──
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # ── Validate MIME type ──
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        logger.warning(f"Unusual MIME type: {content_type} — allowing but flagging")

    # ── Read file (enforce size limit) ──
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) // 1024 // 1024}MB). Max: {settings.MAX_FILE_SIZE_MB}MB"
        )
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # ── Save with job_id as filename ──
    job_id    = uuid.uuid4().hex[:12]
    save_path = settings.UPLOAD_DIR / f"{job_id}{suffix}"
    save_path.write_bytes(content)
    logger.info(f"Upload saved: {save_path} ({len(content):,} bytes)")

    # ── Set initial status ──
    set_step(job_id, PipelineStep.queued, 0, "Queued — pipeline starting...")

    # ── Launch background pipeline ──
    background_tasks.add_task(
        run_full_pipeline,
        job_id    = job_id,
        file_path = str(save_path),
        filename  = file.filename or f"meeting{suffix}",
    )

    return UploadResponse(
        job_id   = job_id,
        filename = file.filename or f"meeting{suffix}",
        message  = "Upload received. Processing started. Poll /api/status/{job_id} for progress.",
        status   = PipelineStep.queued,
    )


# ── Status polling ────────────────────────────────────────────────────
@app.get("/api/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """
    Poll this endpoint while the pipeline runs.
    Returns step name, progress (0–100), and message.
    Frontend polls every ~1.5 seconds.
    """
    _validate_job_id(job_id)
    status = load_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return status


# ── Meeting list ──────────────────────────────────────────────────────
@app.get("/api/meetings", response_model=list[MeetingListItem])
async def get_meetings():
    """Return all processed meetings (summary list for the dashboard index view)."""
    return list_meetings()


# ── Full meeting result ───────────────────────────────────────────────
@app.get("/api/meeting/{job_id}", response_model=MeetingResult)
async def get_meeting(job_id: str):
    """Return the full meeting result — transcript, decisions, action items, flags."""
    _validate_job_id(job_id)

    # Check if still processing
    status = load_status(job_id)
    if status and status.step not in (PipelineStep.done, PipelineStep.error):
        raise HTTPException(
            status_code=202,
            detail=f"Meeting still processing: {status.step.value} ({status.progress}%)"
        )

    result = load_result(job_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Meeting '{job_id}' not found")
    return result


# ── Delete meeting ────────────────────────────────────────────────────
@app.delete("/api/meeting/{job_id}")
async def delete_meeting_endpoint(job_id: str):
    """Delete a meeting and its uploaded file."""
    _validate_job_id(job_id)
    deleted = delete_meeting(job_id)

    # Also delete uploaded file
    for ext in ALLOWED_EXTENSIONS:
        p = settings.UPLOAD_DIR / f"{job_id}{ext}"
        if p.exists():
            p.unlink()
            break

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Meeting '{job_id}' not found")
    return {"status": "deleted", "job_id": job_id}


# ── Input validation helper ───────────────────────────────────────────
def _validate_job_id(job_id: str) -> None:
    """Prevent path traversal attacks by validating job_id format."""
    if not job_id.replace("-", "").replace("_", "").isalnum() or len(job_id) > 64:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
