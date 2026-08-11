"""
pipeline.py — Reorganized coco2.py logic.
All processing functions from coco2.py are here, cleaned up and made
safe for async FastAPI background task execution.

Stages:
  1. extract_audio       — ffmpeg: video → 16kHz mono WAV
  2. run_diarization     — PyAnnote 3.1: speaker timeline
  3. transcribe_audio    — Whisper: timestamped segments
  4. align_speakers      — map segments → SPEAKER_XX
  5. extract_names       — Gemini Vision: read nameplates from video frames
  6. map_speakers        — SPEAKER_XX → real name
  7. run_gemini_analysis — Gemini 2.5 Flash: decisions, action items, flags
  8. build_result        — assemble MeetingResult

Each stage updates the job status so the frontend can poll progress.
"""
import os
import json
import base64
import shutil
import logging
import subprocess
import tempfile
import asyncio
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import httpx

from MEETINGS.config  import settings
from MEETINGS.schemas import (
    MeetingResult, TranscriptLine, Decision, ActionItem,
    Flag, PipelineStep, DecisionConfidence, FlagType
)
from MEETINGS.storage import set_step, set_error, save_result, now_iso

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# STAGE 1 — Audio Extraction
# ─────────────────────────────────────────────────────────────────────

def extract_audio(video_path: str, audio_path: str) -> str:
    """
    Extract audio from video using ffmpeg.
    Output: 16kHz mono WAV (required by both Whisper and PyAnnote).
    """
    if Path(audio_path).exists():
        logger.info(f"Audio already exists: {audio_path}")
        return audio_path

    logger.info(f"Extracting audio from: {video_path}")
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn",                    # no video
        "-acodec", "pcm_s16le",   # 16-bit PCM WAV
        "-ar", "16000",           # 16kHz sample rate (PyAnnote requirement)
        "-ac", "1",               # mono
        "-y",                     # overwrite
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")

    logger.info(f"Audio extracted: {audio_path}")
    return audio_path


# ─────────────────────────────────────────────────────────────────────
# STAGE 2 — Deepgram Transcription & Diarization
# ─────────────────────────────────────────────────────────────────────

def run_deepgram_transcription(audio_path: str) -> List[dict]:
    """
    Send audio to Deepgram API for transcription and diarization.
    Returns: List of aligned segment dictionaries.
    """
    if not settings.DEEPGRAM_API_KEY:
        raise ValueError("DEEPGRAM_API_KEY is not set.")
    
    logger.info(f"Sending audio to Deepgram: {audio_path}")
    
    with open(audio_path, "rb") as file:
        buffer_data = file.read()
    
    headers = {
        "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
        "Content-Type": "audio/wav"
    }
    params = {
        "model": "nova-2",
        "smart_format": "true",
        "diarize": "true",
        "paragraphs": "true",
        "language": "en"
    }
    
    # Use httpx with no timeout for large files
    with httpx.Client(timeout=300.0) as client:
        response = client.post(
            "https://api.deepgram.com/v1/listen",
            headers=headers,
            params=params,
            content=buffer_data
        )
        response.raise_for_status()
        data = response.json()
    
    alts = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0]
    paragraphs = alts.get("paragraphs", {}).get("paragraphs", [])
    
    segments = []
    
    if paragraphs:
        for p in paragraphs:
            start = p.get("start", 0)
            h = int(start // 3600)
            m = int((start % 3600) // 60)
            s = int(start % 60)
            
            # Deepgram stores text in 'sentences' array inside each paragraph
            sentences = p.get("sentences", [])
            text = " ".join(s.get("text", "") for s in sentences).strip()
            
            # Skip completely empty paragraphs (often noise)
            if not text:
                continue
            
            segments.append({
                "timestamp": f"{h:02d}:{m:02d}:{s:02d}",
                "start": start,
                "speaker": f"SPEAKER_{p.get('speaker', 0) + 1:02d}",
                "speaker_raw": str(p.get("speaker", 0)),
                "text": text
            })
    else:
        # Fallback if paragraphs aren't available
        words = alts.get("words", [])
        # Very crude fallback just in case
        for i in range(0, len(words), 10):
            chunk = words[i:i+10]
            start = chunk[0].get("start", 0)
            h = int(start // 3600)
            m = int((start % 3600) // 60)
            s = int(start % 60)
            text = " ".join([w.get("punctuated_word", w.get("word", "")) for w in chunk])
            speaker = chunk[0].get("speaker", 0)
            
            segments.append({
                "timestamp": f"{h:02d}:{m:02d}:{s:02d}",
                "start": start,
                "speaker": f"SPEAKER_{speaker + 1:02d}",
                "speaker_raw": str(speaker),
                "text": text.strip()
            })

    logger.info(f"Deepgram transcription complete — {len(segments)} segments")
    return segments


def _call_agnes_api(messages: list, model: str = "agnes-2.0-flash") -> str:
    """Helper to call Agnes AI OpenAI-compatible chat completion endpoint with 429 retry backoff."""
    import urllib.request
    import time

    url = f"{settings.AGNES_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages
    }
    data_bytes = json.dumps(payload).encode("utf-8")

    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data_bytes, headers=headers)
            with urllib.request.urlopen(req, timeout=35) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res["choices"][0]["message"]["content"]
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "rate" in err_str.lower()) and attempt < 3:
                logger.warning(f"Agnes AI rate limited (429). Retrying in 2.5s (attempt {attempt+1}/4)...")
                time.sleep(2.5)
                continue
            raise


# ─────────────────────────────────────────────────────────────────────
# STAGE 5 — Vision: Extract Names from Video Frames
# ─────────────────────────────────────────────────────────────────────

def extract_names_from_video(video_path: str) -> Dict[float, List[str]]:
    """
    Extract frames from video and send to Vision API (Agnes AI or Gemini) to identify participant names.
    Samples 4 key frames with gentle pacing to respect API rate limits.
    """
    if not settings.AGNES_API_KEY and not settings.GEMINI_API_KEY:
        return {}

    import cv2
    import time
    import base64
    import re

    name_timestamps: Dict[float, List[str]] = {}
    frames_dir = settings.FRAMES_DIR
    frames_dir.mkdir(parents=True, exist_ok=True)

    gemini_client = None
    if settings.GEMINI_API_KEY:
        from google import genai
        gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)

    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
        duration_s = total_frames / fps

        # Sample 4 key frames across the video to prevent rate limits
        if duration_s > 0:
            sample_timestamps = [
                duration_s * 0.15,
                duration_s * 0.40,
                duration_s * 0.65,
                duration_s * 0.85,
            ]
        else:
            sample_timestamps = [0.0]

        logger.info("Sampling 4 key video frames for Gemini Vision...")

        for ts in sample_timestamps:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps))
            ret, frame = cap.read()
            if not ret:
                continue

            frame_path = frames_dir / f"frame_{int(ts)}s.jpg"
            cv2.imwrite(str(frame_path), frame)

            try:
                time.sleep(1.0)
                image_bytes = frame_path.read_bytes()
                resp_text = ""

                if settings.GEMINI_API_KEY:
                    try:
                        from google.genai import types
                        prompt = (
                            "Look at this video meeting screenshot. "
                            "List all visible participant names (from name tags, banners, or video tiles). "
                            'Return ONLY JSON: {"names": ["Name1", "Name2"]}. '
                            'If no names visible: {"names": []}.'
                        )
                        resp = gemini_client.models.generate_content(
                            model="gemini-2.0-flash",
                            contents=[
                                prompt,
                                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                            ],
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json"
                            ),
                        )
                        resp_text = resp.text
                    except Exception as gemini_err:
                        logger.warning(f"Gemini Vision notice: {gemini_err}. Falling back to Agnes AI Vision...")
                        resp_text = ""

                if not resp_text and settings.AGNES_API_KEY:
                    b64_str = base64.b64encode(image_bytes).decode('utf-8')
                    data_uri = f"data:image/jpeg;base64,{b64_str}"
                    messages = [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": 'Look at this video meeting screenshot. List all visible participant names (from name tags, video tiles, or banners). Return ONLY JSON: {"names": ["Name1", "Name2"]}. If none: {"names": []}.'},
                                {"type": "image_url", "image_url": {"url": data_uri}}
                            ]
                        }
                    ]
                    resp_text = _call_agnes_api(messages, model="agnes-2.0-flash")

                raw_json = resp_text.strip()
                match = re.search(r'\{.*\}', raw_json, re.DOTALL)
                if match:
                    raw_json = match.group(0)
                data = json.loads(raw_json)
                names = data.get("names", []) or data.get("participants", [])
                if names:
                    name_timestamps[ts] = names
            except Exception as e:
                logger.warning(f"  Frame {int(ts)}s Vision notice: {e}")

        cap.release()
        logger.info(f"Vision complete — names found in {len(name_timestamps)} frames")

    except Exception as e:
        logger.warning(f"Vision extraction notice: {e}")
    finally:
        for p in frames_dir.glob("frame_*.jpg"):
            try:
                p.unlink()
            except Exception:
                pass

    return name_timestamps


# ─────────────────────────────────────────────────────────────────────
# STAGE 6 — Map SPEAKER_XX → Real Names (Enforce Unique 1-to-1 Mapping)
# ─────────────────────────────────────────────────────────────────────

def map_speakers_to_names(
    segments: List[dict],
    name_timestamps: Dict[float, List[str]],
    gemini_map: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Map SPEAKER_01, SPEAKER_02 to real names.
    Combines AI Analysis speaker_map and Vision timestamps while enforcing 1-to-1 UNIQUE assignment.
    """
    speaker_map: Dict[str, str] = dict(gemini_map or {})
    assigned_names: set = set(name for name in speaker_map.values() if name and "speaker" not in name.lower())
    all_names = list(set([n for names in name_timestamps.values() for n in names]))

    if not name_timestamps or not all_names:
        return speaker_map

    speaker_frames: Dict[str, List[float]] = {}
    for seg in segments:
        spk = seg["speaker"]
        t_str = seg["timestamp"]
        try:
            parts = t_str.split(":")
            if len(parts) == 2:
                seg_sec = int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                seg_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            else:
                seg_sec = 0
        except Exception:
            seg_sec = 0

        speaker_frames.setdefault(spk, []).append(seg_sec)

    for spk, times in speaker_frames.items():
        if spk in speaker_map and speaker_map[spk] and "speaker" not in speaker_map[spk].lower():
            continue

        matched_names: List[str] = []
        for seg_t in times:
            for frame_t, names in name_timestamps.items():
                if abs(frame_t - seg_t) < 60:
                    matched_names.extend(names)

        if matched_names:
            most_common = max(set(matched_names), key=matched_names.count)
            speaker_map[spk] = most_common
            logger.info(f"Mapped {spk} -> {most_common} (from Vision timestamps)")

    return speaker_map


# ─────────────────────────────────────────────────────────────────────
# STAGE 7 — Gemini Analysis
# ─────────────────────────────────────────────────────────────────────

_HISTORICAL_CONTEXT = """
1. Meeting Date: 2026-05-03 | Decision: Freeze all new vendor onboarding until Q4.
2. Meeting Date: 2026-03-15 | Decision: Require security audits before signing tech vendor contracts.
"""

def run_gemini_analysis(transcript_text: str, detected_names: List[str] = None) -> dict:
    """
    Send transcript to Agnes AI or Gemini 2.0 Flash for:
    - Mapping speaker IDs to real names
    - Extracting decisions (with confidence levels)
    - Extracting action items (with assignee + deadline)
    - Flagging contradictions against historical decisions
    """
    names_str = ", ".join(detected_names) if detected_names else "None detected from video frames"

    prompt = f"""
You are the AI engine for 'Corporate Brain', an organizational intelligence platform.

**PART 1 — INFER & MAP SPEAKER NAMES**
The transcript currently has speaker IDs like SPEAKER_01, SPEAKER_02, etc.
The following participant names were DETECTED from video nameplates/tiles by Vision AI:
[{names_str}]

Analyze the conversation carefully to determine each speaker's real identity.
Assign each speaker ID to one of the detected participant names above (or infer their real name if not in the list).
Do NOT output generic labels like "Unknown Speaker X". Use the actual names detected above!

**PART 2 — EXTRACT INTELLIGENCE**
From the transcript, extract:
1. Decisions — with confidence: "firm_commitment" | "soft_agreement" | "unresolved"
2. Action Items — with assignee (real name) and deadline (ISO date or description)
3. AI Flags — compare decisions against Historical Decisions below and flag contradictions

Historical Decisions for comparison:
{_HISTORICAL_CONTEXT}

**Meeting Transcript:**
{transcript_text}

**Return ONLY valid JSON** with this exact structure:
{{
  "participants": ["Real Name 1", "Real Name 2"],
  "speaker_map": {{"SPEAKER_01": "Real Name 1", "SPEAKER_02": "Real Name 2"}},
  "decisions": [
    {{
      "text": "Decision text here",
      "confidence": "firm_commitment",
      "timestamp": "00:00:14",
      "speaker": "Real Name 1"
    }}
  ],
  "action_items": [
    {{
      "task": "Task description",
      "assignee": "Real Name 2",
      "deadline": "2026-08-20",
      "priority": "high"
    }}
  ],
  "flags": [
    {{
      "type": "contradiction",
      "message": "Why this is flagged",
      "severity": "warning"
    }}
  ]
}}
"""

    try:
        raw = ""
        if settings.GEMINI_API_KEY:
            logger.info("Running Gemini 2.0 Flash analysis...")
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                raw = response.text
            except Exception as gemini_ex:
                logger.warning(f"Gemini analysis notice: {gemini_ex}. Falling back to Agnes AI...")
                raw = ""

        if not raw and settings.AGNES_API_KEY:
            logger.info("Running Agnes AI Flash analysis...")
            messages = [{"role": "user", "content": prompt}]
            raw = _call_agnes_api(messages, model="agnes-2.0-flash")

        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        return json.loads(raw)
    except Exception as e:
        logger.warning(f"AI analysis failed: {e}. Using fallback extraction.")
        return _fallback_analysis(transcript_text, detected_names)


def _fallback_analysis(transcript_text: str, detected_names: Optional[List[str]] = None) -> dict:
    """Fallback intelligence extraction when Gemini API rate limits/quotas are reached."""
    participants = list(set(detected_names)) if detected_names else ["Speaker"]
    decisions = []
    action_items = []
    
    # Extract lines mentioning key decision/action words
    for line in transcript_text.split("\n"):
        if not line.strip():
            continue
        ts = "00:00:00"
        spk = "Speaker"
        txt = line
        if line.startswith("[") and "]" in line:
            parts = line.split("]", 1)
            ts = parts[0].replace("[", "").strip()
            rest = parts[1].strip()
            if ":" in rest:
                spk_parts = rest.split(":", 1)
                spk = spk_parts[0].strip()
                txt = spk_parts[1].strip()

        l_lower = txt.lower()
        if any(w in l_lower for w in ["decide", "agree", "confirm", "approve", "settle", "must", "wise", "compulsory"]):
            decisions.append({
                "text": txt,
                "confidence": "firm_commitment",
                "timestamp": ts,
                "speaker": spk
            })
        elif any(w in l_lower for w in ["action", "task", "todo", "post", "send", "submit", "check", "need to"]):
            action_items.append({
                "task": txt,
                "assignee": spk,
                "deadline": "End of week",
                "priority": "high"
            })

    return {
        "participants": participants,
        "speaker_map": {},
        "decisions": decisions[:5],
        "action_items": action_items[:5],
        "flags": []
    }


# ─────────────────────────────────────────────────────────────────────
# DEMO MODE — Realistic mock pipeline (no API keys needed)
# ─────────────────────────────────────────────────────────────────────

def _demo_pipeline(job_id: str, filename: str) -> MeetingResult:
    """Return realistic demo data when DEMO_MODE=true."""
    return MeetingResult(
        job_id       = job_id,
        filename     = filename,
        processed_at = now_iso(),
        duration     = "1h 22m",
        participants = ["Sarah Park", "Tom Wright", "Alex Chen", "Diana Ross"],
        speaker_map  = {
            "SPEAKER_01": "Sarah Park",
            "SPEAKER_02": "Tom Wright",
            "SPEAKER_03": "Alex Chen",
            "SPEAKER_04": "Diana Ross",
        },
        transcript   = [
            TranscriptLine(timestamp="00:00:08", speaker="Sarah Park",  speaker_raw="SPEAKER_01", text="Good morning everyone. Let's start with the vendor evaluation."),
            TranscriptLine(timestamp="00:01:22", speaker="Tom Wright",  speaker_raw="SPEAKER_02", text="I've reviewed all three providers. Provider X leads on cost and SLA."),
            TranscriptLine(timestamp="00:03:10", speaker="Alex Chen",   speaker_raw="SPEAKER_03", text="What's the cost saving over the full contract period?"),
            TranscriptLine(timestamp="00:03:45", speaker="Tom Wright",  speaker_raw="SPEAKER_02", text="22% over 36 months — roughly $340,000 total savings."),
            TranscriptLine(timestamp="00:05:20", speaker="Diana Ross",  speaker_raw="SPEAKER_04", text="Are there integration risks for Project Alpha's Q4 deadline?"),
            TranscriptLine(timestamp="00:06:30", speaker="Tom Wright",  speaker_raw="SPEAKER_02", text="6-week migration window. A security audit is the main precondition."),
            TranscriptLine(timestamp="00:08:15", speaker="Diana Ross",  speaker_raw="SPEAKER_04", text="Did we formally lift the vendor freeze from the May all-hands?"),
            TranscriptLine(timestamp="00:09:40", speaker="Sarah Park",  speaker_raw="SPEAKER_01", text="That freeze was a guideline. I'm comfortable proceeding. Decision made."),
            TranscriptLine(timestamp="00:11:05", speaker="Sarah Park",  speaker_raw="SPEAKER_01", text="Official decision: switch to Provider X, effective Q4 2026. Tom, own the audit."),
            TranscriptLine(timestamp="00:11:30", speaker="Tom Wright",  speaker_raw="SPEAKER_02", text="Confirmed. I'll target audit completion by August 20th."),
            TranscriptLine(timestamp="00:13:45", speaker="Alex Chen",   speaker_raw="SPEAKER_03", text="The transition adds ~15% to Project Alpha's budget. I need that approved."),
            TranscriptLine(timestamp="00:14:55", speaker="Sarah Park",  speaker_raw="SPEAKER_01", text="Approved in principle. Bring formal numbers to finance Thursday."),
        ],
        decisions    = [
            Decision(text="Switch primary vendor to Provider X, effective Q4 2026", confidence=DecisionConfidence.firm_commitment, timestamp="00:11:05", speaker="Sarah Park"),
            Decision(text="Increase Project Alpha budget by 15% for vendor transition", confidence=DecisionConfidence.soft_agreement,  timestamp="00:13:45", speaker="Alex Chen"),
            Decision(text="Security audit of Provider X is mandatory before contract signing", confidence=DecisionConfidence.firm_commitment, timestamp="00:06:30", speaker="Tom Wright"),
        ],
        action_items = [
            ActionItem(task="Complete security audit of Provider X", assignee="Tom Wright", deadline="2026-08-20", priority="high"),
            ActionItem(task="Submit 15% budget increase to finance committee", assignee="Alex Chen", deadline="2026-08-15", priority="high"),
            ActionItem(task="Begin vendor procurement negotiations with Provider X", assignee="Sarah Park", deadline="2026-09-01", priority="high"),
            ActionItem(task="Set up bi-weekly transition steering committee", assignee="Diana Ross", deadline=None, priority="medium"),
        ],
        flags        = [
            Flag(type=FlagType.contradiction, message="Provider X decision may conflict with the vendor freeze agreed at the May 3rd All-Hands meeting.", severity="warning"),
        ],
    )


# ─────────────────────────────────────────────────────────────────────
# MASTER PIPELINE — called by FastAPI background task
# ─────────────────────────────────────────────────────────────────────

async def run_full_pipeline(job_id: str, file_path: str, filename: str) -> None:
    """
    Full processing pipeline. Runs asynchronously in the background.
    Updates status at every stage so the frontend can poll /api/status/{job_id}.
    """
    audio_path = str(settings.UPLOAD_DIR / f"{job_id}.wav")

    try:
        # ── Demo mode ──
        if settings.DEMO_MODE:
            logger.info(f"[{job_id}] DEMO_MODE=true — running simulated pipeline")
            steps = [
                (PipelineStep.extracting_audio, 10, "Extracting audio track from video..."),
                (PipelineStep.diarizing,        25, "PyAnnote detecting speakers..."),
                (PipelineStep.transcribing,     45, "Whisper transcribing audio..."),
                (PipelineStep.aligning,         60, "Aligning speakers with transcript..."),
                (PipelineStep.vision,           72, "Gemini Vision reading participant names..."),
                (PipelineStep.analysing,        85, "Gemini extracting decisions and action items..."),
                (PipelineStep.saving,           95, "Saving meeting intelligence..."),
            ]
            for step, progress, message in steps:
                set_step(job_id, step, progress, message)
                await asyncio.sleep(1.0)   # Simulate processing time

            result = _demo_pipeline(job_id, filename)
            save_result(result)
            set_step(job_id, PipelineStep.done, 100, "Meeting fully processed")
            return

        # ── Stage 1: Extract audio ──
        set_step(job_id, PipelineStep.extracting_audio, 5, "Extracting audio from video...")
        audio_path = await asyncio.get_event_loop().run_in_executor(
            None, extract_audio, file_path, audio_path
        )
        set_step(job_id, PipelineStep.extracting_audio, 12, "Audio extracted")

        # ── Stage 2: Deepgram Transcription & Diarization ──
        set_step(job_id, PipelineStep.transcribing, 15, "Deepgram transcribing and separating speakers...")
        aligned = await asyncio.get_event_loop().run_in_executor(
            None, run_deepgram_transcription, audio_path
        )
        set_step(job_id, PipelineStep.transcribing, 55, "Deepgram transcription complete")
        set_step(job_id, PipelineStep.aligning, 62, "Speaker alignment complete")

        # ── Build initial transcript text ──
        transcript_text = "\n".join(
            f"[{s['timestamp']}] {s['speaker']}: {s['text']}" for s in aligned
        )

        # ── Stage 5: Vision AI (only for video files) ──
        name_timestamps: Dict = {}
        ai_provider = "Gemini" if settings.GEMINI_API_KEY else "Agnes AI"
        if file_path.lower().endswith((".mp4", ".mkv", ".mov", ".avi", ".webm")):
            set_step(job_id, PipelineStep.vision, 64, f"{ai_provider} Vision reading participant names from video...")
            if settings.AGNES_API_KEY or settings.GEMINI_API_KEY:
                name_timestamps = await asyncio.get_event_loop().run_in_executor(
                    None, extract_names_from_video, file_path
                )
            set_step(job_id, PipelineStep.vision, 72, f"Names found in {len(name_timestamps)} frames")

        # Collect all unique names detected from Vision AI
        all_detected_names = list(set([name for names in name_timestamps.values() for name in names]))

        # ── Stage 6: AI Analysis & Speaker Mapping ──
        set_step(job_id, PipelineStep.analysing, 75, f"{ai_provider} extracting decisions, action items, and flags...")

        analysis: dict = {}
        ai_speaker_map: dict = {}
        if settings.AGNES_API_KEY or settings.GEMINI_API_KEY:
            analysis = await asyncio.get_event_loop().run_in_executor(
                None, run_gemini_analysis, transcript_text, all_detected_names
            )
            if "speaker_map" in analysis and isinstance(analysis["speaker_map"], dict):
                for spk, name in analysis["speaker_map"].items():
                    if name and "unknown" not in name.lower() and "speaker" not in name.lower():
                        ai_speaker_map[spk] = name

        # Map speakers combining AI Analysis + Vision timestamps with 1-to-1 unique assignment
        speaker_map = map_speakers_to_names(aligned, name_timestamps, ai_speaker_map)

        # Update transcript text with final unique names
        for seg in aligned:
            seg["speaker"] = speaker_map.get(seg["speaker"], seg["speaker"])
        transcript_text = "\n".join(
            f"[{s['timestamp']}] {s['speaker']}: {s['text']}" for s in aligned
        )

        set_step(job_id, PipelineStep.analysing, 90,
                 f"{len(analysis.get('decisions', []))} decisions · "
                 f"{len(analysis.get('action_items', []))} action items · "
                 f"{len(analysis.get('flags', []))} flags")

        # ── Stage 8: Assemble result ──
        set_step(job_id, PipelineStep.saving, 92, "Saving results...")

        # Build final transcript with resolved names
        final_transcript = [
            TranscriptLine(
                timestamp   = s["timestamp"],
                speaker     = speaker_map.get(s["speaker"], s["speaker"]),
                speaker_raw = s.get("speaker_raw", ""),
                text        = s["text"],
            )
            for s in aligned
        ]

        # Parse Gemini output
        decisions    = [Decision(**d)    for d in analysis.get("decisions",    [])]
        action_items = [ActionItem(**a)  for a in analysis.get("action_items", [])]
        flags        = [Flag(**f)        for f in analysis.get("flags",        [])]
        participants = analysis.get("participants", list(set(speaker_map.values())))

        # Calculate total duration (hh:mm:ss) from last segment
        last_sec = max([s.get("start", 0) for s in aligned], default=0)
        h = int(last_sec // 3600)
        m = int((last_sec % 3600) // 60)
        s = int(last_sec % 60)
        duration_str = f"{h:02d}:{m:02d}:{s:02d}"

        result = MeetingResult(
            job_id       = job_id,
            filename     = filename,
            processed_at = now_iso(),
            duration     = duration_str,
            participants = participants,
            speaker_map  = speaker_map,
            transcript   = final_transcript,
            decisions    = decisions,
            action_items = action_items,
            flags        = flags,
        )

        save_result(result)
        set_step(job_id, PipelineStep.done, 100, "Meeting fully processed")
        logger.info(f"[{job_id}] Pipeline complete — {len(decisions)} decisions, {len(action_items)} actions, {len(flags)} flags")

    except Exception as e:
        logger.exception(f"[{job_id}] Pipeline failed: {e}")
        set_error(job_id, str(e))

    finally:
        # Clean up temporary WAV if it was extracted from video
        if audio_path and os.path.exists(audio_path) and audio_path.endswith(".wav"):
            try:
                os.remove(audio_path)
            except Exception:
                pass
