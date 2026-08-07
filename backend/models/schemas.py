"""
Corporate Brain — All Pydantic schemas (shared data contracts)
All 4 team members import from this file — do NOT change field names without telling everyone.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ── Enums ──────────────────────────────────────────────────────────────

class MeetingStatus(str, Enum):
    pending      = "pending"
    recording    = "recording"
    transcribing = "transcribing"
    extracting   = "extracting"
    contradiction= "contradiction"
    graph        = "graph"
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

class FlagSeverity(str, Enum):
    critical = "critical"
    warning  = "warning"
    info     = "info"

class NodeType(str, Enum):
    meeting    = "meeting"
    decision   = "decision"
    person     = "person"
    project    = "project"
    action_item= "action_item"


# ── Transcript ─────────────────────────────────────────────────────────

class TranscriptLine(BaseModel):
    timestamp: str               # "00:01:23"
    speaker:   str               # "Alex Chen" or "Speaker 1"
    text:      str


# ── Decision ───────────────────────────────────────────────────────────

class Decision(BaseModel):
    decision_id:     str
    meeting_id:      str
    text:            str
    confidence:      DecisionConfidence
    timestamp:       str
    speaker:         str
    contradicts:     Optional[str] = None   # decision_id it contradicts
    linked_meetings: List[str]    = Field(default_factory=list)


# ── Action Item ────────────────────────────────────────────────────────

class ActionItem(BaseModel):
    id:         str
    task:       str
    assignee:   str
    deadline:   Optional[str] = None   # ISO date string
    status:     str = "open"           # open | done | overdue
    priority:   str = "medium"         # high | medium | low
    meeting_id: str
    meeting_title: str = ""


# ── Flag ───────────────────────────────────────────────────────────────

class Flag(BaseModel):
    id:                str
    meeting_id:        str
    type:              FlagType
    severity:          FlagSeverity
    message:           str
    detail:            str
    contradicts_meeting:  Optional[str] = None
    contradicts_decision: Optional[str] = None


# ── Participant ────────────────────────────────────────────────────────

class Participant(BaseModel):
    name:      str
    role:      str = "participant"    # participant | organizer | bot
    email:     Optional[str] = None
    joinedAt:  Optional[str] = None
    leftAt:    Optional[str] = None


# ── Meeting ────────────────────────────────────────────────────────────

class Meeting(BaseModel):
    id:                str
    title:             str
    date:              str
    duration:          str = "—"
    participants:      List[str]    = Field(default_factory=list)
    status:            MeetingStatus = MeetingStatus.pending
    decisions_count:   int = 0
    flags_count:       int = 0
    action_items_count:int = 0

class MeetingDetail(BaseModel):
    id:           str
    title:        str
    date:         str
    duration:     str
    participants: List[str]
    transcript:   List[TranscriptLine]
    decisions:    List[Decision]
    action_items: List[ActionItem]
    flags:        List[Flag]

class MeetingStatus_Response(BaseModel):
    meeting_id: str
    step:       str
    progress:   int          # 0-100
    message:    str
    flags:      List[Flag]  = Field(default_factory=list)


# ── Room ───────────────────────────────────────────────────────────────

class Room(BaseModel):
    id:           str
    meeting_id:   str
    title:        str
    date:         str
    join_url:     str
    participants: List[Participant] = Field(default_factory=list)
    status:       str = "active"     # active | ended

class CreateRoomRequest(BaseModel):
    title:       str
    date:        Optional[str] = None
    organizer:   Optional[str] = "Alex Chen"

class CocoSubmitResponse(BaseModel):
    meeting_id:  str
    status:      str
    message:     str


# ── Graph ──────────────────────────────────────────────────────────────

class GraphNode(BaseModel):
    id:         str
    type:       NodeType
    label:      str
    date:       Optional[str] = None
    confidence: Optional[str] = None

class GraphEdge(BaseModel):
    source:          str
    target:          str
    label:           str
    isContradiction: bool = False

class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


# ── Dashboard ──────────────────────────────────────────────────────────

class UpcomingMeeting(BaseModel):
    id:           str
    title:        str
    date:         str
    time:         str
    participants: int
    location:     str = "Virtual"

class DashboardResponse(BaseModel):
    action_items:       List[ActionItem]
    flags:              List[Flag]
    upcoming_meetings:  List[UpcomingMeeting]


# ── User ───────────────────────────────────────────────────────────────

class User(BaseModel):
    id:    str
    name:  str
    email: str
    role:  str = "member"
    org:   str = "Acme Corp"


# ── Chat ───────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query:      str
    user_id:    Optional[str] = None

class ChatCitation(BaseModel):
    meeting_id:    str
    meeting_title: str
    decision_id:   Optional[str] = None
    excerpt:       str

class ChatResponse(BaseModel):
    answer:    str
    citations: List[ChatCitation]
