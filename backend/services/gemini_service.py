"""
Gemini Extraction Service — turns a transcript into structured decisions,
action items, participants, and projects.
Owner: Person B

Real path: calls Gemini 2.5 Flash via google-generativeai.
Demo path: returns realistic extracted data when GEMINI_API_KEY is missing.
"""
import os
import json
import uuid
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not installed. Using demo extraction.")


def _init_gemini():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if api_key and GEMINI_AVAILABLE:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel("gemini-2.0-flash")
    return None


_EXTRACTION_PROMPT = """
You are an AI analyst reviewing a meeting transcript. Extract the following in JSON format:

1. decisions: list of decisions made. Each has:
   - text: the decision text (clear, complete sentence)
   - confidence: "firm_commitment" | "soft_agreement" | "unresolved"
   - timestamp: best matching timestamp from transcript (HH:MM:SS)
   - speaker: who made/announced the decision

2. action_items: list of tasks assigned. Each has:
   - task: clear description of what needs to be done
   - assignee: person responsible (use "Unassigned" if unclear)
   - deadline: deadline if mentioned (ISO date or null)
   - priority: "high" | "medium" | "low"

3. participants: list of people who SPOKE in the meeting (their names as mentioned)

4. projects: list of project or product names mentioned

Return ONLY valid JSON, no explanation text. Format:
{
  "decisions": [...],
  "action_items": [...],
  "participants": [...],
  "projects": [...]
}

TRANSCRIPT:
"""


async def extract(
    transcript: List[dict],
    meeting_id: str
) -> Tuple[List[dict], List[dict], List[str], List[str]]:
    """
    Extract structured data from a transcript.

    Returns: (decisions, action_items, participant_names, project_names)
    """
    demo_mode = os.getenv("DEMO_MODE", "true").lower() == "true"
    model = None if demo_mode else _init_gemini()

    if model is None:
        logger.info("Using demo extraction (Gemini not configured or DEMO_MODE=true)")
        return _demo_extraction(transcript, meeting_id)

    # Format transcript for prompt
    transcript_text = "\n".join(
        f"[{line['timestamp']}] {line['speaker']}: {line['text']}"
        for line in transcript
    )

    try:
        response = model.generate_content(_EXTRACTION_PROMPT + transcript_text)
        raw = response.text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)

        decisions = []
        for i, d in enumerate(data.get("decisions", [])):
            decisions.append({
                "decision_id": f"d_{meeting_id}_{i+1:03d}",
                "meeting_id":  meeting_id,
                "text":        d.get("text", ""),
                "confidence":  d.get("confidence", "soft_agreement"),
                "timestamp":   d.get("timestamp", "00:00:00"),
                "speaker":     d.get("speaker", "Unknown"),
                "contradicts": None,
                "linked_meetings": [],
            })

        action_items = []
        for i, a in enumerate(data.get("action_items", [])):
            action_items.append({
                "id":          f"ai_{meeting_id}_{i+1:03d}",
                "task":        a.get("task", ""),
                "assignee":    a.get("assignee", "Unassigned"),
                "deadline":    a.get("deadline"),
                "status":      "open",
                "priority":    a.get("priority", "medium"),
                "meeting_id":  meeting_id,
                "meeting_title": "",
            })

        participants = data.get("participants", [])
        projects     = data.get("projects", [])

        logger.info(
            f"Extraction complete: {len(decisions)} decisions, "
            f"{len(action_items)} action items, {len(participants)} participants"
        )
        return decisions, action_items, participants, projects

    except Exception as e:
        logger.error(f"Gemini extraction failed: {e}")
        return _demo_extraction(transcript, meeting_id)


def _demo_extraction(transcript: List[dict], meeting_id: str):
    """Realistic demo extraction when Gemini is unavailable."""
    decisions = [
        {
            "decision_id": f"d_{meeting_id}_001",
            "meeting_id":  meeting_id,
            "text":        "Switch primary logistics vendor to Provider X, effective Q4 2026",
            "confidence":  "firm_commitment",
            "timestamp":   "00:11:05",
            "speaker":     "Speaker 1",
            "contradicts": None,
            "linked_meetings": [],
        },
        {
            "decision_id": f"d_{meeting_id}_002",
            "meeting_id":  meeting_id,
            "text":        "Increase Project Alpha budget by 15% to cover vendor transition costs",
            "confidence":  "soft_agreement",
            "timestamp":   "00:13:45",
            "speaker":     "Speaker 3",
            "contradicts": None,
            "linked_meetings": [],
        },
        {
            "decision_id": f"d_{meeting_id}_003",
            "meeting_id":  meeting_id,
            "text":        "Security audit of Provider X is a mandatory precondition before contract signing",
            "confidence":  "firm_commitment",
            "timestamp":   "00:06:30",
            "speaker":     "Speaker 2",
            "contradicts": None,
            "linked_meetings": [],
        },
    ]

    action_items = [
        {
            "id":          f"ai_{meeting_id}_001",
            "task":        "Complete security audit of Provider X infrastructure",
            "assignee":    "Speaker 2",
            "deadline":    "2026-08-20",
            "status":      "open",
            "priority":    "high",
            "meeting_id":  meeting_id,
            "meeting_title": "",
        },
        {
            "id":          f"ai_{meeting_id}_002",
            "task":        "Submit formal budget increase request to finance committee",
            "assignee":    "Speaker 3",
            "deadline":    "2026-08-15",
            "status":      "open",
            "priority":    "high",
            "meeting_id":  meeting_id,
            "meeting_title": "",
        },
        {
            "id":          f"ai_{meeting_id}_003",
            "task":        "Set up bi-weekly steering committee meetings for vendor transition",
            "assignee":    "Speaker 4",
            "deadline":    None,
            "status":      "open",
            "priority":    "medium",
            "meeting_id":  meeting_id,
            "meeting_title": "",
        },
        {
            "id":          f"ai_{meeting_id}_004",
            "task":        "Begin vendor procurement negotiations with Provider X",
            "assignee":    "Speaker 1",
            "deadline":    "2026-09-01",
            "status":      "open",
            "priority":    "high",
            "meeting_id":  meeting_id,
            "meeting_title": "",
        },
    ]

    # Extract speaker names from transcript
    speakers = list({line["speaker"] for line in transcript}) if transcript else ["Speaker 1", "Speaker 2"]

    return decisions, action_items, speakers, ["Project Alpha", "Provider X", "Provider Y"]
