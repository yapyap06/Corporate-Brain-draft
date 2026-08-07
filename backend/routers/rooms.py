"""
Rooms router — create meeting rooms and handle Coco's join.
Owner: Person A (with Person D wiring the frontend room.html)
"""
import json
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks

from backend.database  import rooms_db, meetings_db, new_id, now_iso
from backend.models.schemas import Room, CreateRoomRequest

router = APIRouter(prefix="/api/rooms", tags=["rooms"])
logger = logging.getLogger(__name__)


@router.post("/create", response_model=Room)
async def create_room(req: CreateRoomRequest):
    """
    Create a new meeting room.
    Coco automatically joins when the room is created.
    Returns the room ID and a shareable join URL.
    """
    room_id    = new_id("room_")
    meeting_id = new_id("m_")
    date       = req.date or datetime.now(timezone.utc).isoformat()

    # Create the meeting entry (status = pending until Coco submits)
    meetings_db[meeting_id] = {
        "id":                meeting_id,
        "title":             req.title,
        "date":              date,
        "duration":          "—",
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
        "pipeline_message":  "Waiting for meeting to start",
        "coco_recorded":     False,
    }

    # Create the room
    rooms_db[room_id] = {
        "id":          room_id,
        "meeting_id":  meeting_id,
        "title":       req.title,
        "date":        date,
        "participants": [
            {
                "name":     "Coco",
                "role":     "bot",
                "joinedAt": now_iso(),
            }
        ],
        "status": "active",
    }

    logger.info(f"[Room] Created room {room_id} for meeting {meeting_id}: '{req.title}'")

    join_url = f"/room.html?id={room_id}"
    return Room(
        id=room_id,
        meeting_id=meeting_id,
        title=req.title,
        date=date,
        join_url=join_url,
        participants=rooms_db[room_id]["participants"],
        status="active",
    )


@router.get("/{room_id}", response_model=Room)
async def get_room(room_id: str):
    """Get current room state including participant list."""
    room = rooms_db.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")

    return Room(**room)


@router.post("/{room_id}/join")
async def join_room(room_id: str, participant_name: str, participant_role: str = "participant"):
    """Record a participant joining the room."""
    room = rooms_db.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")

    room["participants"].append({
        "name":     participant_name,
        "role":     participant_role,
        "joinedAt": now_iso(),
    })

    logger.info(f"[Room] {participant_name} joined room {room_id}")
    return {"status": "joined", "room_id": room_id}
