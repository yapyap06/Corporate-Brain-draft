"""
schemas.py — All Pydantic data models for the MEETINGS API.
These define the shape of every request and response — the contract for index.html.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class PipelineStep(str, Enum):
    queued       = "queued"
    extracting_audio  = "extracting_audio"
    diarizing    = "diarizing"
    transcribing = "transcribing"
    aligning     = "aligning"
    vision       = "vision"
    analysing    = "analysing"
    saving       = "saving"
    done         = "done"
    error        = "error"


class DecisionConfidence(str, Enum):
    firm_commitment = "firm_commitment"
    soft_agreement  = "soft_agreement"
    unresolved      = "unresolved"


class FlagType(str, Enum):
    contradiction        = "contradiction"
    duplicate_discussion = "duplicate_discussion"
    policy_conflict      = "policy_conflict"
    missing_stakeholder  = "missing_stakeholder"


# ── Pipeline progress (polled by frontend) ────────────────────────────

class JobStatus(BaseModel):
    job_id:    str
    step:      PipelineStep
    progress:  int = Field(ge=0, le=100, description="0–100 percent complete")
    message:   str = ""
    error:     Optional[str] = None


# ── Core meeting data ─────────────────────────────────────────────────

class TranscriptLine(BaseModel):
    timestamp:    str           # HH:MM:SS
    speaker:      str           # Real name (or SPEAKER_XX if unresolved)
    speaker_raw:  str = ""      # Original PyAnnote label (SPEAKER_00 etc.)
    text:         str


class Decision(BaseModel):
    text:         str
    confidence:   DecisionConfidence
    timestamp:    str
    speaker:      str


class ActionItem(BaseModel):
    task:         str
    assignee:     str
    deadline:     Optional[str] = None    # ISO date or human-readable string
    priority:     str = "medium"


class Flag(BaseModel):
    type:         FlagType
    message:      str
    severity:     str = "warning"         # warning | info | critical


class SpeakerMapEntry(BaseModel):
    speaker_id:   str   # SPEAKER_01
    real_name:    str   # Alex Chen


# ── Full meeting result ───────────────────────────────────────────────

class MeetingResult(BaseModel):
    job_id:       str
    filename:     str
    processed_at: str
    duration:     str = "—"

    # Participants (real names resolved by Gemini + Vision)
    participants: List[str]               = Field(default_factory=list)
    speaker_map:  dict                    = Field(default_factory=dict)

    # Transcript
    transcript:   List[TranscriptLine]    = Field(default_factory=list)

    # AI extracted intelligence
    decisions:    List[Decision]          = Field(default_factory=list)
    action_items: List[ActionItem]        = Field(default_factory=list)
    flags:        List[Flag]              = Field(default_factory=list)


# ── Meeting list (index page) ─────────────────────────────────────────

class MeetingListItem(BaseModel):
    job_id:           str
    filename:         str
    processed_at:     str
    status:           PipelineStep
    participants:     List[str]  = Field(default_factory=list)
    decisions_count:  int = 0
    action_items_count: int = 0
    flags_count:      int = 0


# ── Upload response ───────────────────────────────────────────────────

class UploadResponse(BaseModel):
    job_id:   str
    filename: str
    message:  str
    status:   PipelineStep = PipelineStep.queued
