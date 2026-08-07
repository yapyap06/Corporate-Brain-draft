"""
CocoAgent — orchestrates the full post-meeting pipeline.
This is the brain of Coco. It receives a recording from room.html,
runs each pipeline step, and updates the meeting status so the frontend
can poll for progress.

Owner: Person A (pipeline orchestration)
"""
import os
import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path

from backend.database import meetings_db, new_id, now_iso
from backend.services import whisper_service, gemini_service, contradiction_service

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _set_status(meeting_id: str, step: str, progress: int, message: str = ""):
    """Update the meeting pipeline status (polled by frontend)."""
    if meeting_id in meetings_db:
        meetings_db[meeting_id]["status"]          = step
        meetings_db[meeting_id]["pipeline_progress"] = progress
        meetings_db[meeting_id]["pipeline_message"]  = message
        logger.info(f"[Coco] Meeting {meeting_id}: {step} ({progress}%) — {message}")


async def process_meeting(
    meeting_id: str,
    audio_path: str | None,
    participants: list[dict],
    title: str,
    duration: str,
) -> dict:
    """
    Full pipeline:
    1. Transcription (Whisper)
    2. Entity/decision extraction (Gemini)
    3. Contradiction detection
    4. Write to Neo4j / in-memory DB
    5. Mark done

    Runs in the background after Coco submits the meeting.
    """
    logger.info(f"[Coco] Starting pipeline for meeting {meeting_id}")

    # ── Step 1: Transcription ──────────────────────────────────────────
    _set_status(meeting_id, "transcribing", 10, "Whisper is converting speech to text...")
    await asyncio.sleep(0.2)  # Yield to event loop

    transcript = await whisper_service.transcribe(audio_path or "")
    _set_status(meeting_id, "transcribing", 30, f"Transcription complete — {len(transcript)} segments")

    # ── Step 2: Entity Extraction ──────────────────────────────────────
    _set_status(meeting_id, "extracting", 35, "Gemini is extracting decisions and action items...")
    await asyncio.sleep(0.1)

    decisions, action_items, participant_names, projects = await gemini_service.extract(
        transcript, meeting_id
    )

    # Map participant names from Coco's list if Gemini found generic "Speaker 1" labels
    real_names = [p["name"] for p in participants if p.get("role") != "bot"]
    decisions, action_items = _remap_speakers(decisions, action_items, real_names)

    # Update meeting title on action items
    for ai in action_items:
        ai["meeting_title"] = title

    _set_status(meeting_id, "extracting", 55,
                f"{len(decisions)} decisions · {len(action_items)} action items extracted")

    # ── Step 3: Contradiction Detection ───────────────────────────────
    _set_status(meeting_id, "contradiction", 60, "Checking against organizational memory...")
    await asyncio.sleep(0.1)

    flags = await contradiction_service.check_contradictions(
        decisions, meeting_id, meetings_db
    )

    # Index new decisions for future contradiction checks
    await contradiction_service.index_decisions(decisions, meeting_id)

    if flags:
        _set_status(meeting_id, "contradiction", 70,
                    f"{len(flags)} flag(s) detected — contradictions found")
    else:
        _set_status(meeting_id, "contradiction", 70, "No contradictions detected")

    # ── Step 4: Write to Graph (Neo4j / in-memory) ─────────────────────
    _set_status(meeting_id, "graph", 75, "Updating Corporate Memory Graph...")
    await asyncio.sleep(0.2)

    # TODO (Person B): Replace this with real Neo4j writes
    # await neo4j_service.write_meeting(meeting_id, decisions, action_items, participants)

    # In-memory write for demo
    meetings_db[meeting_id].update({
        "title":             title,
        "duration":          duration,
        "participants":      [p["name"] for p in participants if p.get("role") != "bot"],
        "transcript":        transcript,
        "decisions":         decisions,
        "action_items":      action_items,
        "flags":             flags,
        "decisions_count":   len(decisions),
        "flags_count":       len(flags),
        "action_items_count":len(action_items),
        "coco_recorded":     True,
        "processed_at":      now_iso(),
    })

    _set_status(meeting_id, "graph", 90, "Memory graph updated with new nodes and relationships")

    # ── Step 5: Done ───────────────────────────────────────────────────
    _set_status(meeting_id, "done", 100, "Meeting fully processed and available")
    logger.info(f"[Coco] Pipeline complete for meeting {meeting_id}")

    return meetings_db[meeting_id]


def _remap_speakers(decisions: list, action_items: list, real_names: list) -> tuple:
    """
    Replace generic "Speaker 1/2/3" labels with real participant names from Coco's list.
    This is a simple round-robin mapping — real diarization would do proper alignment.
    """
    if not real_names:
        return decisions, action_items

    mapping = {f"Speaker {i+1}": name for i, name in enumerate(real_names)}

    for d in decisions:
        if d.get("speaker") in mapping:
            d["speaker"] = mapping[d["speaker"]]

    for a in action_items:
        if a.get("assignee") in mapping:
            a["assignee"] = mapping[a["assignee"]]

    return decisions, action_items


async def save_audio(audio_bytes: bytes, meeting_id: str, mime_type: str = "audio/webm") -> str:
    """Save uploaded audio file and return the file path."""
    ext = "webm" if "webm" in mime_type else "ogg" if "ogg" in mime_type else "wav"
    filename = UPLOAD_DIR / f"{meeting_id}.{ext}"
    with open(filename, "wb") as f:
        f.write(audio_bytes)
    logger.info(f"[Coco] Audio saved: {filename} ({len(audio_bytes):,} bytes)")
    return str(filename)
