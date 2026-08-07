"""
Meetings router — the core data access layer for all meeting data.
Owner: Person A

Endpoints:
  POST /api/meetings/coco-submit   ← Coco calls this when meeting ends
  GET  /api/meetings               ← meetings.html list view
  GET  /api/meetings/{id}          ← meeting-detail.html
  GET  /api/meetings/{id}/status   ← room.html pipeline progress polling
"""
import json
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks

from backend.database    import meetings_db, new_id, now_iso
from backend.services    import coco as coco_service
from backend.models.schemas import (
    Meeting, MeetingDetail, MeetingStatus_Response,
    CocoSubmitResponse, TranscriptLine, Decision, ActionItem, Flag
)

router = APIRouter(prefix="/api/meetings", tags=["meetings"])
logger = logging.getLogger(__name__)


# ── Coco submission endpoint ───────────────────────────────────────────

@router.post("/coco-submit", response_model=CocoSubmitResponse)
async def coco_submit(
    background_tasks: BackgroundTasks,
    meeting_id:   str         = Form(...),
    title:        str         = Form("Untitled Meeting"),
    duration:     str         = Form("—"),
    participants: str         = Form("[]"),   # JSON string
    audio:        Optional[UploadFile] = File(None),
):
    """
    Called by room.html (Coco) when the meeting ends.
    Accepts the audio recording + participant list.
    Runs the full pipeline in the background.
    Returns immediately so the frontend can start polling for status.
    """
    logger.info(f"[Coco Submit] meeting_id={meeting_id}, title='{title}'")

    # Parse participants list
    try:
        participant_list = json.loads(participants)
    except Exception:
        participant_list = []

    # Ensure meeting exists in DB (may have been pre-created via /rooms/create)
    if meeting_id not in meetings_db:
        meetings_db[meeting_id] = {
            "id":                meeting_id,
            "title":             title,
            "date":              now_iso(),
            "duration":          duration,
            "participants":      [],
            "status":            "pending",
            "decisions_count":   0,
            "flags_count":       0,
            "action_items_count":0,
            "transcript":        [],
            "decisions":         [],
            "action_items":      [],
            "flags":             [],
            "pipeline_progress": 0,
            "pipeline_message":  "Starting pipeline...",
            "coco_recorded":     True,
        }

    # Save audio file if provided
    audio_path = None
    if audio and audio.filename:
        audio_bytes = await audio.read()
        if audio_bytes:
            mime = audio.content_type or "audio/webm"
            audio_path = await coco_service.save_audio(audio_bytes, meeting_id, mime)
            logger.info(f"Audio saved: {audio_path} ({len(audio_bytes):,} bytes)")

    # Run pipeline in background (non-blocking)
    background_tasks.add_task(
        coco_service.process_meeting,
        meeting_id    = meeting_id,
        audio_path    = audio_path,
        participants  = participant_list,
        title         = title,
        duration      = duration,
    )

    return CocoSubmitResponse(
        meeting_id=meeting_id,
        status="processing",
        message="Coco is processing your meeting. Poll /status for updates."
    )


# ── Meeting status (for polling) ──────────────────────────────────────

@router.get("/{meeting_id}/status", response_model=MeetingStatus_Response)
async def get_meeting_status(meeting_id: str):
    """
    Polled by room.html every ~1.5 seconds to show pipeline progress.
    Returns current step, progress %, message, and any flags found so far.
    """
    meeting = meetings_db.get(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")

    flags_raw = meeting.get("flags", [])
    flags = [Flag(**f) if isinstance(f, dict) else f for f in flags_raw]

    return MeetingStatus_Response(
        meeting_id = meeting_id,
        step       = meeting.get("status", "pending"),
        progress   = meeting.get("pipeline_progress", 0),
        message    = meeting.get("pipeline_message", ""),
        flags      = flags,
    )


# ── List all meetings ──────────────────────────────────────────────────

@router.get("", response_model=list[Meeting])
async def list_meetings():
    """Return all meetings for the meetings.html list view."""
    result = []
    for m in meetings_db.values():
        result.append(Meeting(
            id                 = m["id"],
            title              = m["title"],
            date               = m.get("date", now_iso()),
            duration           = m.get("duration", "—"),
            participants       = m.get("participants", []),
            status             = m.get("status", "pending"),
            decisions_count    = m.get("decisions_count", 0),
            flags_count        = m.get("flags_count", 0),
            action_items_count = m.get("action_items_count", 0),
        ))
    # Most recent first
    result.sort(key=lambda x: x.date, reverse=True)
    return result


# ── Meeting detail ─────────────────────────────────────────────────────

@router.get("/{meeting_id}", response_model=MeetingDetail)
async def get_meeting(meeting_id: str):
    """Return full meeting data for the meeting-detail.html page."""
    meeting = meetings_db.get(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")

    def _to_transcript(lines):
        return [TranscriptLine(**l) if isinstance(l, dict) else l for l in lines]

    def _to_decisions(items):
        return [Decision(**d) if isinstance(d, dict) else d for d in items]

    def _to_action_items(items):
        return [ActionItem(**a) if isinstance(a, dict) else a for a in items]

    def _to_flags(items):
        return [Flag(**f) if isinstance(f, dict) else f for f in items]

    return MeetingDetail(
        id           = meeting["id"],
        title        = meeting["title"],
        date         = meeting.get("date", ""),
        duration     = meeting.get("duration", "—"),
        participants = meeting.get("participants", []),
        transcript   = _to_transcript(meeting.get("transcript", [])),
        decisions    = _to_decisions(meeting.get("decisions", [])),
        action_items = _to_action_items(meeting.get("action_items", [])),
        flags        = _to_flags(meeting.get("flags", [])),
    )
