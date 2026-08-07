"""
Contradiction Service — compares new decisions against organizational memory
to detect contradictions, duplicates, and missing stakeholders.
Owner: Person C

Real path: ChromaDB semantic search + Gemini reasoning.
Demo path: simple keyword matching + demo flags.
"""
import os
import logging
import uuid
from typing import List, Tuple

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("chromadb not installed. Using keyword-based contradiction detection.")

_chroma_client = None
_collection    = None


def _init_chroma():
    global _chroma_client, _collection
    if _chroma_client is None and CHROMA_AVAILABLE:
        _chroma_client = chromadb.Client()
        _collection = _chroma_client.get_or_create_collection(
            name="decisions",
            embedding_function=embedding_functions.DefaultEmbeddingFunction()
        )
    return _collection


async def index_decisions(decisions: List[dict], meeting_id: str):
    """Add new decisions to the ChromaDB index so future meetings can find contradictions."""
    collection = _init_chroma()
    if collection is None:
        return  # Demo mode — skip indexing

    for d in decisions:
        try:
            collection.add(
                ids=[d["decision_id"]],
                documents=[d["text"]],
                metadatas=[{"meeting_id": meeting_id, "confidence": d["confidence"]}]
            )
        except Exception as e:
            logger.warning(f"Failed to index decision {d['decision_id']}: {e}")


async def check_contradictions(
    new_decisions: List[dict],
    meeting_id: str,
    all_meetings: dict,
) -> List[dict]:
    """
    For each new decision:
    1. Search ChromaDB for semantically similar past decisions
    2. Ask Gemini if they contradict (demo: keyword matching)
    3. Return list of Flag dicts
    """
    flags = []
    collection = _init_chroma()

    for decision in new_decisions:
        # ── Real path: semantic search ──
        if collection is not None:
            try:
                results = collection.query(
                    query_texts=[decision["text"]],
                    n_results=3,
                    where={"meeting_id": {"$ne": meeting_id}}  # Exclude current meeting
                )

                for i, (doc, meta) in enumerate(
                    zip(results["documents"][0], results["metadatas"][0])
                ):
                    distance = results["distances"][0][i]
                    # Low distance = high similarity (potential contradiction)
                    if distance < 0.4:
                        flag = _build_contradiction_flag(
                            decision, doc, meta["meeting_id"], meeting_id
                        )
                        if flag:
                            flags.append(flag)
            except Exception as e:
                logger.warning(f"ChromaDB query failed: {e}")
                flags.extend(_demo_contradiction_check(new_decisions, meeting_id, all_meetings))
                break

        else:
            # ── Demo path: keyword matching ──
            flags.extend(_demo_contradiction_check(new_decisions, meeting_id, all_meetings))
            break  # Only run once in demo mode

    # Deduplicate flags by ID
    seen = set()
    unique_flags = []
    for f in flags:
        if f["id"] not in seen:
            seen.add(f["id"])
            unique_flags.append(f)

    return unique_flags


def _build_contradiction_flag(
    new_decision: dict,
    similar_text: str,
    past_meeting_id: str,
    current_meeting_id: str,
) -> dict | None:
    """
    Use Gemini to determine if two decisions actually contradict.
    Falls back to returning a flag if API unavailable.
    """
    # TODO (Person C): Call Gemini here for deep reasoning
    # prompt = f"""
    # Decision A (from new meeting): {new_decision['text']}
    # Decision B (from past meeting {past_meeting_id}): {similar_text}
    # Do these two decisions contradict each other?
    # Answer JSON: {{"contradicts": true/false, "reason": "..."}}
    # """
    return {
        "id":                  f"f_{uuid.uuid4().hex[:8]}",
        "meeting_id":          current_meeting_id,
        "type":                "contradiction",
        "severity":            "warning",
        "message":             "Potential contradiction with a previous decision",
        "detail":              f'New decision "{new_decision["text"][:80]}..." may conflict with a past decision in meeting {past_meeting_id}.',
        "contradicts_meeting": past_meeting_id,
        "contradicts_decision": None,
    }


def _demo_contradiction_check(
    new_decisions: List[dict],
    meeting_id: str,
    all_meetings: dict,
) -> List[dict]:
    """
    Simple keyword-based contradiction detection for demo mode.
    Looks for decisions about vendors/budget that conflict with known past decisions.
    """
    flags = []

    # Known contradiction: anything about "vendor" and "Provider X" vs. freeze
    contradiction_keywords = {
        "vendor": ["freeze", "halt", "pause", "stop", "delay"],
        "provider x": ["freeze", "halt", "not approved"],
        "budget increase": ["freeze", "hold", "rejected"],
    }

    # Find past decisions across all processed meetings (excluding current)
    past_decisions = []
    for mid, meeting in all_meetings.items():
        if mid == meeting_id:
            continue
        if meeting.get("status") == "done":
            past_decisions.extend(meeting.get("decisions", []))

    for decision in new_decisions:
        text_lower = decision["text"].lower()

        # Check for vendor-related contradictions
        if any(kw in text_lower for kw in ["vendor", "provider x", "provider y", "switch"]):
            for past in past_decisions:
                past_lower = past["text"].lower()
                if any(kw in past_lower for kw in ["freeze", "halt", "pause", "moratorium"]):
                    flags.append({
                        "id":                  f"f_{uuid.uuid4().hex[:8]}",
                        "meeting_id":          meeting_id,
                        "type":                "contradiction",
                        "severity":            "warning",
                        "message":             "New vendor decision conflicts with prior freeze",
                        "detail":              f'Decision "{decision["text"][:100]}" may conflict with: "{past["text"][:100]}"',
                        "contradicts_meeting": past["meeting_id"],
                        "contradicts_decision": past["decision_id"],
                    })

        # Check for duplicate discussion
        for past in past_decisions:
            past_lower = past["text"].lower()
            words_new  = set(text_lower.split())
            words_old  = set(past_lower.split())
            overlap    = words_new & words_old - {"the", "a", "an", "to", "of", "and", "is", "in"}
            if len(overlap) > 8 and past["meeting_id"] != meeting_id:
                flags.append({
                    "id":                  f"f_{uuid.uuid4().hex[:8]}",
                    "meeting_id":          meeting_id,
                    "type":                "duplicate_discussion",
                    "severity":            "info",
                    "message":             "This topic was previously discussed",
                    "detail":              f'Similar decision found in meeting {past["meeting_id"]}: "{past["text"][:100]}"',
                    "contradicts_meeting": past["meeting_id"],
                    "contradicts_decision": past["decision_id"],
                })

    return flags
