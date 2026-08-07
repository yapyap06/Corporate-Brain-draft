"""
In-memory database for Corporate Brain (demo / development mode).
In production, replace with Neo4j + PostgreSQL via Person B's neo4j_service.
"""
import uuid
from datetime import datetime
from typing import Dict, Optional

# ── In-memory stores ──────────────────────────────────────────────────
# These are shared state for all routers.  In production, these become
# real DB calls.  For the hackathon demo, they persist for the session.

rooms_db:    Dict[str, dict] = {}
meetings_db: Dict[str, dict] = {}
users_db:    Dict[str, dict] = {
    "u_001": {
        "id":    "u_001",
        "name":  "Alex Chen",
        "email": "alex.chen@acmecorp.com",
        "role":  "Product Manager",
        "org":   "Acme Corp"
    }
}

# ── Helpers ───────────────────────────────────────────────────────────

def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"

def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def seed_demo_data():
    """
    Pre-seed realistic meeting data so the UI has something to show
    even before any real meeting is processed through Coco.
    """
    from backend.models.schemas import MeetingStatus

    meetings_db["m_001"] = {
        "id":    "m_001",
        "title": "Q2 Business Review",
        "date":  "2026-07-28",
        "duration": "1h 22m",
        "participants": ["Alex Chen", "Sarah Park", "Tom Wright", "Diana Ross"],
        "status": "done",
        "decisions_count":    5,
        "flags_count":        2,
        "action_items_count": 7,
        "transcript": [
            {"timestamp": "00:00:12", "speaker": "Sarah Park",
             "text": "Alright, let's get started. We have a lot to cover — the Q2 numbers, the vendor situation for Project Alpha, and budget sign-off."},
            {"timestamp": "00:02:45", "speaker": "Tom Wright",
             "text": "I've reviewed both Provider X and Provider Y proposals. Provider X gives us 22% cost savings over 36 months, and their SLA terms are considerably better."},
            {"timestamp": "00:05:30", "speaker": "Alex Chen",
             "text": "That's a significant saving. What are the transition risks? We have a Q4 hard deadline on Project Alpha."},
            {"timestamp": "00:07:15", "speaker": "Tom Wright",
             "text": "The main risk is the 6-week migration window. We'd also need a full security audit first."},
            {"timestamp": "00:10:02", "speaker": "Diana Ross",
             "text": "I want to flag that we discussed a vendor freeze back in May. Did we formally lift that?"},
            {"timestamp": "00:12:40", "speaker": "Sarah Park",
             "text": "That freeze was a soft guideline. I'm comfortable proceeding. We'll document this decision."},
            {"timestamp": "00:14:32", "speaker": "Sarah Park",
             "text": "Let's make it official — we're switching to Provider X, effective Q4 2026."},
            {"timestamp": "00:31:15", "speaker": "Alex Chen",
             "text": "On budget — the Provider X transition requires about 15% uplift on Project Alpha."},
        ],
        "decisions": [
            {"decision_id": "d_001", "meeting_id": "m_001", "text": "Switch primary logistics vendor from Provider Y to Provider X effective Q4 2026", "confidence": "firm_commitment", "timestamp": "00:14:32", "speaker": "Sarah Park", "contradicts": "d_m003_001", "linked_meetings": ["m_003"]},
            {"decision_id": "d_002", "meeting_id": "m_001", "text": "Increase Project Alpha budget by 15% to accommodate vendor transition", "confidence": "soft_agreement", "timestamp": "00:31:15", "speaker": "Alex Chen", "contradicts": None, "linked_meetings": []},
            {"decision_id": "d_003", "meeting_id": "m_001", "text": "Conduct a full security audit of Provider X before contract signing", "confidence": "firm_commitment", "timestamp": "00:45:08", "speaker": "Tom Wright", "contradicts": None, "linked_meetings": []},
        ],
        "action_items": [
            {"id": "ai_001", "task": "Finalise Q3 budget proposal", "assignee": "Alex Chen", "deadline": "2026-08-10", "status": "overdue", "priority": "high", "meeting_id": "m_001", "meeting_title": "Q2 Business Review"},
            {"id": "ai_002", "task": "Evaluate three shortlisted vendors", "assignee": "Alex Chen", "deadline": "2026-08-15", "status": "open", "priority": "high", "meeting_id": "m_001", "meeting_title": "Q2 Business Review"},
            {"id": "ai_008", "task": "Run security audit on Provider X", "assignee": "Tom Wright", "deadline": "2026-08-20", "status": "open", "priority": "high", "meeting_id": "m_001", "meeting_title": "Q2 Business Review"},
        ],
        "flags": [
            {"id": "f_001", "meeting_id": "m_001", "type": "contradiction", "severity": "warning", "message": "Decision contradicts prior vendor freeze", "detail": "The decision to switch to Provider X contradicts the May 3rd freeze on new vendor onboarding until Q4.", "contradicts_meeting": "m_003", "contradicts_decision": "d_m003_001"},
        ]
    }

    meetings_db["m_002"] = {
        "id":    "m_002",
        "title": "Vendor Selection — Project Alpha",
        "date":  "2026-07-15",
        "duration": "48m",
        "participants": ["Alex Chen", "Tom Wright", "James Liu"],
        "status": "done",
        "decisions_count": 3, "flags_count": 0, "action_items_count": 4,
        "transcript": [], "decisions": [], "action_items": [], "flags": []
    }

    meetings_db["m_003"] = {
        "id":    "m_003",
        "title": "All-Hands — May Strategy Update",
        "date":  "2026-05-03",
        "duration": "2h 05m",
        "participants": ["Sarah Park", "Diana Ross", "James Liu", "Mike O'Brien"],
        "status": "done",
        "decisions_count": 8, "flags_count": 0, "action_items_count": 12,
        "transcript": [], "decisions": [
            {"decision_id": "d_m003_001", "meeting_id": "m_003", "text": "Freeze new vendor onboarding until Q4 2026", "confidence": "firm_commitment", "timestamp": "00:45:00", "speaker": "Sarah Park", "contradicts": None, "linked_meetings": []}
        ], "action_items": [], "flags": []
    }
