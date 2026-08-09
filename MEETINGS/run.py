#!/usr/bin/env python3
"""
run.py — Run the MEETINGS pipeline directly from the terminal.
This calls coco2.py's logic step-by-step with visible output.

Usage:
    python MEETINGS/run.py path/to/meeting.mp4
    python MEETINGS/run.py path/to/audio.mp3
    python MEETINGS/run.py path/to/meeting.mp4 --output results/my_meeting.json
    python MEETINGS/run.py path/to/meeting.mp4 --skip-vision   (skip Gemini Vision nameplate reading)

Output: JSON file saved to MEETINGS/results/<filename>.json
"""
import os
import sys
import json
import time
import argparse
import uuid
from pathlib import Path

from typing import Dict, List, Tuple, Optional
import httpx

# Load .env before importing anything else
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

RESULTS_DIR = Path(__file__).parent / "results"
UPLOADS_DIR = Path(__file__).parent / "uploads"
RESULTS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

# ── Helpers ────────────────────────────────────────────────────────────

def banner(text):
    print(f"\n{'='*65}")
    print(f"  {text}")
    print(f"{'='*65}")

def step(n, total, text):
    print(f"\n[{n}/{total}] {text}...")

def ok(text="Done"):
    print(f"    OK  {text}")

def ts(sec):
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ── STAGE 1: Extract Audio ─────────────────────────────────────────────

def extract_audio(video_path: str, audio_path: str) -> str:
    import subprocess
    if Path(audio_path).exists():
        print(f"    Audio already exists: {audio_path}")
        return audio_path
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        "-y", audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-800:]}")
    ok(f"Saved to {audio_path}")
    return audio_path


# ── STAGE 2: Deepgram Transcription & Diarization ─────────────────────

def run_deepgram_transcription(audio_path: str):
    if not DEEPGRAM_API_KEY:
        raise ValueError("DEEPGRAM_API_KEY is not set.")
    
    print(f"    Sending audio to Deepgram: {audio_path}")
    t0 = time.time()
    
    with open(audio_path, "rb") as file:
        buffer_data = file.read()
    
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
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
        
    elapsed = time.time() - t0
    
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
            
            # Skip completely empty paragraphs
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
        words = alts.get("words", [])
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

    ok(f"{len(segments)} segments in {elapsed:.0f}s")
    return segments


# ── STAGE 5: Gemini Vision ─────────────────────────────────────────────

def extract_names_from_video(video_path: str, interval_s: int = 10):
    import cv2, base64
    from google import genai

    from google import genai
    from google.genai import types

    if not GEMINI_API_KEY:
        print("    Skipping — GEMINI_API_KEY not set")
        return {}

    client = genai.Client(api_key=GEMINI_API_KEY)
    frames_dir = Path(__file__).parent / "frames"
    frames_dir.mkdir(exist_ok=True)

    name_timestamps = {}
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    total_dur = total_frames / fps if fps > 0 else 0

    sample_s = max(interval_s, int(total_dur / 30)) if total_dur > 0 else interval_s
    interval = max(1, int(fps * sample_s))
    n = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if n % interval == 0:
                t_sec = n / fps
                path = frames_dir / f"f_{int(t_sec)}s.jpg"
                cv2.imwrite(str(path), frame)
                try:
                    img_bytes = path.read_bytes()
                    prompt = 'List all participant names visible (name tags, video tiles). Return JSON: {"names":[...]}'
                    resp = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[
                            prompt,
                            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                    time.sleep(1.0)
                    names = json.loads(resp.text).get("names", [])
                    if names:
                        name_timestamps[t_sec] = names
                        print(f"    Frame {int(t_sec)}s -> {names}")
                except Exception as e:
                    print(f"    Frame {int(t_sec)}s error: {e}")
            n += 1
        cap.release()
    finally:
        import shutil
        shutil.rmtree(str(frames_dir), ignore_errors=True)

    ok(f"Names found in {len(name_timestamps)} frames")
    return name_timestamps


# ── STAGE 6: Map speakers → real names ────────────────────────────────

def map_speakers(aligned, name_timestamps):
    speaker_map = {}
    assigned = set()

    for seg in aligned:
        spk = seg["speaker"]
        if spk in speaker_map or spk == "UNKNOWN":
            continue

        parts = seg["timestamp"].split(":")
        seg_s = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

        best, dist = None, float("inf")
        for ft, names in name_timestamps.items():
            for name in names:
                if name in assigned:
                    continue
                d = abs(ft - seg_s)
                if d < dist:
                    dist, best = d, name

        if best and dist < 30:
            speaker_map[spk] = best
            assigned.add(best)
            print(f"    {spk} -> {best}")

    ok(f"Resolved {len(speaker_map)} speaker names")
    return speaker_map


# ── STAGE 7: Gemini Analysis ───────────────────────────────────────────

_HISTORY = """
1. Meeting Date: 2026-05-03 | Decision: Freeze all new vendor onboarding until Q4.
2. Meeting Date: 2026-03-15 | Decision: Require security audits before signing tech vendor contracts.
"""

def run_gemini_analysis(transcript_text: str, detected_names: list = None):
    from google import genai

    if not GEMINI_API_KEY:
        print("    Skipping — GEMINI_API_KEY not set. Returning empty analysis.")
        return {"participants": [], "speaker_map": {}, "decisions": [], "action_items": [], "flags": []}

    client = genai.Client(api_key=GEMINI_API_KEY)
    names_str = ", ".join(detected_names) if detected_names else "None detected from video frames"

    prompt = f"""
You are the AI engine for Corporate Brain.

PART 1 — INFER & MAP SPEAKER NAMES
The transcript currently has speaker IDs like SPEAKER_01, SPEAKER_02, etc.
The following participant names were DETECTED from video nameplates/tiles by Gemini Vision:
[{names_str}]

Analyze the conversation carefully to determine each speaker's real identity.
Assign each speaker ID to one of the detected participant names above (or infer their real name if not in the list).
Do NOT output generic labels like "Unknown Speaker X". Use the actual names detected above!

PART 2 — EXTRACT INTELLIGENCE
1. decisions — each with: text, confidence (firm_commitment|soft_agreement|unresolved), timestamp, speaker
2. action_items — each with: task, assignee, deadline (or null), priority (high|medium|low)
3. flags — compare against historical decisions below and flag contradictions

Historical Decisions:
{_HISTORY}

Transcript:
{transcript_text}

Return ONLY valid JSON:
{{
  "participants": [...],
  "speaker_map": {{"SPEAKER_01": "Name"}},
  "decisions": [{{"text":"...", "confidence":"firm_commitment", "timestamp":"00:00:00", "speaker":"Name"}}],
  "action_items": [{{"task":"...", "assignee":"...", "deadline":"2026-08-20", "priority":"high"}}],
  "flags": [{{"type":"contradiction", "message":"...", "severity":"warning"}}]
}}
"""

    print("    Calling Gemini 2.5 Flash...")
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )

    raw = resp.text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:-1])

    result = json.loads(raw)
    ok(f"{len(result.get('decisions',[]))} decisions  "
       f"{len(result.get('action_items',[]))} action items  "
       f"{len(result.get('flags',[]))} flags")
    return result


# ── MAIN ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MEETINGS pipeline — direct terminal runner")
    parser.add_argument("file", help="Path to video (mp4/mkv/mov) or audio (mp3/wav/m4a)")
    parser.add_argument("--output", "-o", help="Output JSON path (default: results/<name>.json)")
    parser.add_argument("--skip-vision", action="store_true", help="Skip Gemini Vision frame analysis")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    job_id     = uuid.uuid4().hex[:10]
    stem       = file_path.stem
    audio_path = str(UPLOADS_DIR / f"{job_id}.wav")
    output_path = Path(args.output) if args.output else RESULTS_DIR / f"{stem}_{job_id}.json"

    banner(f"MEETINGS Pipeline — {file_path.name}")
    print(f"  Job ID:       {job_id}")
    print(f"  Gemini key:   {'SET' if GEMINI_API_KEY else 'NOT SET'}")
    print(f"  Deepgram API: {'SET' if DEEPGRAM_API_KEY else 'NOT SET'}")
    print(f"  Output:       {output_path}")

    total_steps = 7
    t_start = time.time()

    # ── Step 1: Extract audio ──
    is_video = file_path.suffix.lower() in {".mp4", ".mkv", ".mov", ".avi", ".webm"}
    if is_video:
        step(1, total_steps, "Extracting audio from video (ffmpeg)")
        audio_path = extract_audio(str(file_path), audio_path)
    else:
        print(f"\n[1/{total_steps}] Audio file provided — skipping extraction")
        audio_path = str(file_path)

    # ── Step 2: Transcription & Diarization ──
    step(2, total_steps, "Deepgram Transcription & Diarization")
    if not DEEPGRAM_API_KEY:
        print("    SKIPPED (no DEEPGRAM_API_KEY)")
        aligned = []
    else:
        aligned = run_deepgram_transcription(audio_path)

    # ── Step 5: Gemini Vision ──
    step(5, total_steps, "Gemini Vision — reading participant names from video frames")
    if args.skip_vision or not is_video:
        print("    SKIPPED (audio-only or --skip-vision flag)")
        name_timestamps = {}
    else:
        name_timestamps = extract_names_from_video(str(file_path))

    # ── Step 6: Map speakers ──
    step(6, total_steps, "Mapping SPEAKER_XX to real names")
    speaker_map = map_speakers(aligned, name_timestamps)

    # Apply names to aligned segments
    for seg in aligned:
        seg["speaker"] = speaker_map.get(seg["speaker"], seg["speaker"])

    transcript_text = "\n".join(
        f"[{s['timestamp']}] {s['speaker']}: {s['text']}" for s in aligned
    )

    # ── Step 7: Gemini Analysis ──
    step(7, total_steps, "Gemini 2.5 Flash — extracting decisions, action items, flags")
    all_detected_names = list(set([name for names in name_timestamps.values() for name in names]))
    analysis = run_gemini_analysis(transcript_text, all_detected_names)

    # Merge speaker maps (ignoring generic 'Unknown')
    if "speaker_map" in analysis:
        for spk, name in analysis["speaker_map"].items():
            if name and "unknown" not in name.lower():
                speaker_map[spk] = name

    # ── Build output ──
    output = {
        "job_id":       job_id,
        "filename":     file_path.name,
        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration":     f"{int((time.time()-t_start)//60)}m {int((time.time()-t_start)%60)}s",
        "participants": analysis.get("participants", list(set(speaker_map.values()))),
        "speaker_map":  speaker_map,
        "transcript":   aligned,
        "decisions":    analysis.get("decisions", []),
        "action_items": analysis.get("action_items", []),
        "flags":        analysis.get("flags", [])
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # ── Print summary ──
    banner("DONE")
    elapsed = time.time() - t_start
    print(f"  Total time:    {int(elapsed//60)}m {int(elapsed%60)}s")
    print(f"  Participants:  {output['participants']}")
    print(f"  Speaker map:   {speaker_map}")
    print(f"  Decisions:     {len(output['decisions'])}")
    print(f"  Action items:  {len(output['action_items'])}")
    print(f"  Flags:         {len(output['flags'])}")
    print(f"\n  Results saved to:\n  {output_path.resolve()}")
    print(f"\n  View in dashboard:  http://localhost:8100")
    print(f"  View raw JSON:      {output_path.resolve()}")
    print()

    # Clean up temp wav
    temp_wav = Path(UPLOADS_DIR / f"{job_id}.wav")
    if temp_wav.exists():
        temp_wav.unlink()

    return str(output_path)


if __name__ == "__main__":
    main()
