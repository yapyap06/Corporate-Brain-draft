"""
storage.py — Simple JSON file persistence layer.
Each meeting is stored as a single JSON file in results/.
This keeps MEETINGS self-contained with no database dependency.
"""
import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from MEETINGS.config import settings
from MEETINGS.schemas import MeetingResult, MeetingListItem, JobStatus, PipelineStep

logger = logging.getLogger(__name__)


def _result_path(job_id: str) -> Path:
    return settings.RESULTS_DIR / f"{job_id}.json"

def _status_path(job_id: str) -> Path:
    return settings.RESULTS_DIR / f"{job_id}.status.json"


# ── Status tracking ───────────────────────────────────────────────────

def save_status(status: JobStatus) -> None:
    """Persist the current pipeline step so the frontend can poll it."""
    path = _status_path(status.job_id)
    path.write_text(status.model_dump_json(indent=2), encoding="utf-8")


def load_status(job_id: str) -> Optional[JobStatus]:
    path = _status_path(job_id)
    if not path.exists():
        return None
    return JobStatus.model_validate_json(path.read_text(encoding="utf-8"))


def set_step(job_id: str, step: PipelineStep, progress: int, message: str = "") -> None:
    """Convenience: update pipeline step and persist."""
    status = JobStatus(job_id=job_id, step=step, progress=progress, message=message)
    save_status(status)
    logger.info(f"[{job_id}] {step.value} ({progress}%) — {message}")


def set_error(job_id: str, error_message: str) -> None:
    status = JobStatus(
        job_id=job_id, step=PipelineStep.error,
        progress=0, message="Processing failed", error=error_message
    )
    save_status(status)
    logger.error(f"[{job_id}] ERROR: {error_message}")


# ── Result storage ────────────────────────────────────────────────────

def save_result(result: MeetingResult) -> None:
    path = _result_path(result.job_id)
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"[{result.job_id}] Result saved → {path}")


def load_result(job_id: str) -> Optional[MeetingResult]:
    path = _result_path(job_id)
    if not path.exists():
        return None
    return MeetingResult.model_validate_json(path.read_text(encoding="utf-8"))


def delete_meeting(job_id: str) -> bool:
    result_path = _result_path(job_id)
    status_path = _status_path(job_id)
    deleted = False
    for p in [result_path, status_path]:
        if p.exists():
            p.unlink()
            deleted = True
    return deleted


# ── Listing ───────────────────────────────────────────────────────────

def list_meetings() -> list[MeetingListItem]:
    """Return a summary list of all processed meetings."""
    items = []
    for path in sorted(settings.RESULTS_DIR.glob("*.json")):
        if path.name.endswith(".status.json"):
            continue
        try:
            result = MeetingResult.model_validate_json(path.read_text(encoding="utf-8"))
            status = load_status(result.job_id)
            items.append(MeetingListItem(
                job_id             = result.job_id,
                filename           = result.filename,
                processed_at       = result.processed_at,
                status             = status.step if status else PipelineStep.done,
                participants       = result.participants,
                decisions_count    = len(result.decisions),
                action_items_count = len(result.action_items),
                flags_count        = len(result.flags),
            ))
        except Exception as e:
            logger.warning(f"Failed to parse {path.name}: {e}")

    # Most recent first
    items.sort(key=lambda x: x.processed_at, reverse=True)
    return items


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
