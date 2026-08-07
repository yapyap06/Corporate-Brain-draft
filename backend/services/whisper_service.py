"""
Whisper Service — converts audio files to timestamped transcripts.
Owner: Person A

Real path: calls openai-whisper locally (no API key needed).
Demo path: returns realistic mock transcript when DEMO_MODE=true or model unavailable.
"""
import os
import logging
from typing import List

logger = logging.getLogger(__name__)

# Attempt to import Whisper — it's optional (large download)
try:
    import whisper as whisper_lib
    WHISPER_AVAILABLE = True
    logger.info("Whisper library loaded successfully")
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("openai-whisper not installed. Running in demo mode.")

_model = None


def _load_model():
    """Lazy-load the Whisper model (downloads on first use)."""
    global _model
    if _model is None and WHISPER_AVAILABLE:
        model_name = os.getenv("WHISPER_MODEL", "base")
        logger.info(f"Loading Whisper model '{model_name}'...")
        _model = whisper_lib.load_model(model_name)
        logger.info("Whisper model ready.")
    return _model


async def transcribe(audio_path: str) -> List[dict]:
    """
    Transcribe an audio file.

    Returns a list of dicts:
        [{ "timestamp": "00:01:23", "speaker": "Speaker 1", "text": "..." }, ...]

    Speaker diarization: Whisper doesn't natively diarize speakers.
    For the demo we label speakers as "Speaker 1", "Speaker 2" etc.
    To get real speaker names, integrate pyannote.audio (separate step).
    """
    demo_mode = os.getenv("DEMO_MODE", "true").lower() == "true"

    if not WHISPER_AVAILABLE or demo_mode:
        logger.info("Using demo transcript (Whisper not available or DEMO_MODE=true)")
        return _demo_transcript()

    try:
        model = _load_model()
        if model is None:
            return _demo_transcript()

        logger.info(f"Transcribing: {audio_path}")
        result = model.transcribe(
            audio_path,
            task="transcribe",
            verbose=False,
            word_timestamps=True,
        )

        lines = []
        current_speaker = 1

        for segment in result.get("segments", []):
            start_sec = int(segment["start"])
            h = start_sec // 3600
            m = (start_sec % 3600) // 60
            s = start_sec % 60
            timestamp = f"{h:02d}:{m:02d}:{s:02d}"

            # Simple speaker alternation heuristic (replace with pyannote for real diarization)
            # A more sophisticated approach: detect silence gaps > 0.5s → new speaker
            if lines and (segment["start"] - _get_last_end(result, segment)) > 0.8:
                current_speaker = (current_speaker % 4) + 1

            lines.append({
                "timestamp": timestamp,
                "speaker":   f"Speaker {current_speaker}",
                "text":      segment["text"].strip(),
            })

        logger.info(f"Transcription complete: {len(lines)} segments")
        return lines if lines else _demo_transcript()

    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}")
        return _demo_transcript()


def _get_last_end(result: dict, current_segment: dict) -> float:
    """Get end time of segment before the current one."""
    for i, seg in enumerate(result.get("segments", [])):
        if seg is current_segment and i > 0:
            return result["segments"][i - 1]["end"]
    return 0.0


def _demo_transcript() -> List[dict]:
    """
    Realistic demo transcript — used when Whisper isn't available.
    Simulates a meeting about vendor selection and budget decisions.
    """
    return [
        {"timestamp": "00:00:08", "speaker": "Speaker 1",
         "text": "Good morning everyone. Let's get started — we have the vendor evaluation results to discuss and a budget decision to make today."},
        {"timestamp": "00:01:22", "speaker": "Speaker 2",
         "text": "I've completed the full technical evaluation of all three shortlisted vendors. Provider X came out significantly ahead on cost and SLA terms."},
        {"timestamp": "00:03:10", "speaker": "Speaker 1",
         "text": "What's the cost differential we're looking at over the contract period?"},
        {"timestamp": "00:03:45", "speaker": "Speaker 2",
         "text": "Provider X saves us 22% over 36 months compared to our current Provider Y contract. That's roughly $340,000 over three years."},
        {"timestamp": "00:05:20", "speaker": "Speaker 3",
         "text": "That's substantial. Are there any integration risks we should be aware of? We have the Project Alpha deadline in Q4."},
        {"timestamp": "00:06:30", "speaker": "Speaker 2",
         "text": "The migration window is 6 weeks. If we start procurement next month we can make Q4. The main precondition is a security audit — their infrastructure is solid but we need our compliance team to sign off."},
        {"timestamp": "00:08:15", "speaker": "Speaker 4",
         "text": "I should flag — did we formally lift the vendor freeze from the May all-hands? I want to make sure legal is aligned before we commit."},
        {"timestamp": "00:09:40", "speaker": "Speaker 1",
         "text": "That freeze was a guideline, not a binding policy. I'm comfortable moving forward. We'll document this decision properly so there's a clear record."},
        {"timestamp": "00:11:05", "speaker": "Speaker 1",
         "text": "Alright. Decision: we're switching to Provider X, effective Q4 2026. Tom, can you own the security audit?"},
        {"timestamp": "00:11:30", "speaker": "Speaker 2",
         "text": "Confirmed. I'll scope the audit by end of this week and target completion by August 20th."},
        {"timestamp": "00:13:45", "speaker": "Speaker 3",
         "text": "On budget — the transition costs add about 15% to Project Alpha's current allocation. I need that approved before procurement can begin."},
        {"timestamp": "00:14:55", "speaker": "Speaker 1",
         "text": "Agreed in principle. Bring the formal numbers to the finance committee Thursday but you have my backing to proceed with vendor negotiations."},
        {"timestamp": "00:17:20", "speaker": "Speaker 4",
         "text": "Should we establish a steering committee for the transition? This touches procurement, engineering, legal and finance."},
        {"timestamp": "00:18:00", "speaker": "Speaker 1",
         "text": "Good point. Let's set up a bi-weekly check-in. Diana, can you own coordinating that?"},
        {"timestamp": "00:18:35", "speaker": "Speaker 4",
         "text": "I'll set it up. First meeting next Tuesday."},
    ]
