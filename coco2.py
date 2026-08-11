#!/usr/bin/env python3
"""
Corporate Brain: PyAnnote + Gemini Speaker Detection
Run this in Antigravity with a clean Conda environment.
"""

import os
import json
import time
import subprocess
import base64
from typing import Dict, List, Tuple

# --- CONFIGURATION ---
AUDIO_FILE = "extracted_audio.wav"  # Make sure this exists
VIDEO_FILE = "meeting.mp4"          # Your uploaded video
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# --- STEP 1: Install Dependencies (Run once) ---
def install_dependencies():
    """Install all required packages in a clean environment."""
    print("📦 Installing dependencies...")
    
    # Uninstall conflicting packages
    os.system("pip uninstall -y numpy pandas scipy")
    
    # Install compatible versions
    os.system("pip install numpy==1.26.4 pandas==2.2.2 scipy==1.13.1")
    
    # Install PyTorch with CUDA
    os.system("pip install torch==2.3.0 torchaudio==2.3.0 --index-url https://download.pytorch.org/whl/cu118")
    
    # Install PyAnnote and related packages
    os.system("pip install pyannote.audio==3.1.1 huggingface_hub")
    
    # Install Whisper and Gemini
    os.system("pip install openai-whisper google-genai opencv-python-headless")
    
    # Install ffmpeg (if not already installed)
    os.system("apt-get install -y ffmpeg -qq")
    
    print("✅ All dependencies installed!")

# --- STEP 2: Extract Audio from Video ---
def extract_audio(video_path: str, audio_path: str = "extracted_audio.wav"):
    """Extract audio from video using ffmpeg."""
    if os.path.exists(audio_path):
        print(f"⚡ Audio file already exists: {audio_path}")
        return audio_path
    
    print(f"🎬 Extracting audio from {video_path}...")
    cmd = [
        'ffmpeg', '-i', video_path,
        '-vn', '-acodec', 'pcm_s16le',
        '-ar', '16000', '-ac', '1',
        '-y', audio_path
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    print(f"✅ Audio extracted: {audio_path}")
    return audio_path

# --- STEP 3: PyAnnote Diarization ---
def run_diarization(audio_path: str, hf_token: str) -> Dict:
    """Run PyAnnote speaker diarization."""
    from pyannote.audio import Pipeline
    import torch
    
    print("🔄 Loading PyAnnote diarization model...")
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token
    )
    
    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))
        print("✅ PyAnnote running on GPU")
    
    print(f"🎤 Running diarization on {audio_path}...")
    diarization_result = pipeline(audio_path)
    
    # Build speaker timeline
    speaker_timeline = {}
    for turn, _, speaker in diarization_result.itertracks(yield_label=True):
        speaker_timeline[(turn.start, turn.end)] = speaker
    
    unique_speakers = list(set(speaker_timeline.values()))
    print(f"✅ Diarization complete! Detected {len(unique_speakers)} unique speakers.")
    
    return speaker_timeline

# --- STEP 4: Whisper Transcription ---
def transcribe_audio(audio_path: str) -> List[Dict]:
    """Transcribe audio using Whisper."""
    import whisper
    
    print("🚀 Loading Whisper model...")
    model = whisper.load_model("small")
    
    print(f"🎙️ Transcribing {audio_path}...")
    result = model.transcribe(
        audio_path,
        fp16=True,
        language="en"
    )
    
    segments = []
    for seg in result["segments"]:
        hours = int(seg['start'] // 3600)
        minutes = int((seg['start'] % 3600) // 60)
        seconds = int(seg['start'] % 60)
        start_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        segments.append({
            "start": seg['start'],
            "end": seg['end'],
            "timestamp": start_time,
            "text": seg['text'].strip()
        })
    
    print(f"✅ Transcription complete! {len(segments)} segments.")
    return segments

# --- STEP 5: Align Whisper Segments with PyAnnote Speakers ---
def align_speakers(segments: List[Dict], speaker_timeline: Dict) -> List[Dict]:
    """Assign speaker IDs to each Whisper segment based on PyAnnote diarization."""
    aligned = []
    
    # Create a speaker map for consistent labeling
    unique_speakers = list(set(speaker_timeline.values()))
    speaker_label_map = {orig: f"SPEAKER_{i+1:02d}" for i, orig in enumerate(unique_speakers)}
    
    for seg in segments:
        seg_start = seg['start']
        assigned_speaker = "UNKNOWN"
        
        # Find which speaker is active during this segment
        for (s_start, s_end), speaker_id in speaker_timeline.items():
            if s_start <= seg_start <= s_end:
                assigned_speaker = speaker_id
                break
        
        if assigned_speaker in speaker_label_map:
            speaker_label = speaker_label_map[assigned_speaker]
        else:
            speaker_label = "UNKNOWN"
        
        aligned.append({
            "timestamp": seg['timestamp'],
            "speaker": speaker_label,
            "speaker_raw": assigned_speaker,
            "text": seg['text']
        })
    
    print(f"✅ Aligned {len(aligned)} segments with speakers.")
    return aligned

# --- STEP 6: Build Transcript ---
def build_transcript(aligned_segments: List[Dict]) -> str:
    """Build the final transcript text with speaker labels."""
    transcript = ""
    for seg in aligned_segments:
        line = f"[{seg['timestamp']}] {seg['speaker']}: {seg['text']}"
        transcript += line + "\n"
    return transcript

# --- STEP 7: Extract Names from Video (Gemini Vision) ---
def extract_names_from_video(video_path: str, api_key: str) -> Dict:
    """Use Gemini Vision to read names from video frames."""
    import cv2
    from google import genai
    
    client = genai.Client(api_key=api_key)
    name_timestamps = {}
    
    print("📸 Extracting frames from video for name detection...")
    
    # Create frames directory
    os.makedirs("frames", exist_ok=True)
    
    # Extract frames using OpenCV
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(fps * 10)  # One frame every 10 seconds
    
    frame_count = 0
    saved_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % frame_interval == 0:
            timestamp = frame_count / fps
            frame_filename = f"frames/frame_{int(timestamp)}s.jpg"
            cv2.imwrite(frame_filename, frame)
            
            # Send to Gemini
            with open(frame_filename, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            
            prompt = """
            Look at this screenshot from a video meeting.
            Identify all participants' names visible on the screen (name tags, profile pictures).
            Return ONLY a JSON: {"names": ["Name1", "Name2", ...]}.
            If no names visible, return {"names": []}.
            """
            
            try:
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=[prompt, {"mime_type": "image/jpeg", "data": image_data}],
                    config={'response_mime_type': 'application/json'}
                )
                result = json.loads(response.text)
                names = result.get("names", [])
                if names:
                    name_timestamps[timestamp] = names
                    print(f"   ✅ Frame at {int(timestamp)}s → names: {names}")
                saved_count += 1
            except Exception as e:
                print(f"   ⚠️ Frame at {int(timestamp)}s error: {e}")
        
        frame_count += 1
    
    cap.release()
    
    # Clean up
    import shutil
    shutil.rmtree("frames", ignore_errors=True)
    
    print(f"✅ Extracted names from {len(name_timestamps)} frames.")
    return name_timestamps

# --- STEP 8: Map PyAnnote Speakers to Real Names ---
def map_speakers_to_names(
    aligned_segments: List[Dict],
    name_timestamps: Dict,
    speaker_map: Dict
) -> Dict:
    """Map SPEAKER_XX to real names based on Gemini Vision and context."""
    # First, use Vision detection
    for seg in aligned_segments:
        if seg['speaker'] == "UNKNOWN":
            continue
        # Get the raw speaker ID from PyAnnote
        raw_speaker = seg['speaker_raw']
        
        # Find the closest frame timestamp
        seg_start = seg['timestamp']
        # Parse timestamp to seconds
        h, m, s = map(int, seg_start.split(':'))
        seg_seconds = h * 3600 + m * 60 + s
        
        best_name = None
        best_dist = float('inf')
        for frame_time, names in name_timestamps.items():
            if names:
                dist = abs(frame_time - seg_seconds)
                if dist < best_dist:
                    best_dist = dist
                    best_name = names[0]
        
        if best_name and best_dist < 30:
            speaker_map[seg['speaker']] = best_name
    
    return speaker_map

# --- STEP 9: Gemini Analysis (Extracts Decisions, Action Items) ---
def run_gemini_analysis(transcript: str, api_key: str) -> Dict:
    """Run Gemini analysis on the transcript."""
    from google import genai
    
    client = genai.Client(api_key=api_key)
    
    historical_context = """
    1. Meeting Date: 2026-05-03 | Decision: Freeze all new vendor onboarding until Q4.
    2. Meeting Date: 2026-03-15 | Decision: Require security audits before signing tech vendor contracts.
    """
    
    prompt = f"""
    You are the AI engine for 'Corporate Brain'.
    
    **PART 1: INFER SPEAKER NAMES**
    The transcript uses placeholders (SPEAKER_01, SPEAKER_02).
    Analyze the conversation to figure out the REAL NAMES of each speaker.
    Look for introductions, direct address, and context.

    **PART 2: EXTRACT INTELLIGENCE**
    - Extract all decisions with confidence level (firm_commitment, soft_agreement, unresolved).
    - Extract all action items with assignee and deadline.
    - Compare decisions against Historical Decisions and flag contradictions.

    Historical Decisions:
    {historical_context}

    Meeting Transcript:
    {transcript}

    Return ONLY valid JSON with this structure:
    {{
      "participants": ["Real Name 1", "Real Name 2"],
      "speaker_map": {{"SPEAKER_01": "Real Name 1"}},
      "decisions": [
        {{"text": "...", "confidence": "firm_commitment", "timestamp": "00:00:14", "speaker": "Real Name 1"}}
      ],
      "action_items": [
        {{"task": "...", "assignee": "Real Name 2", "deadline": "..."}}
      ],
      "flags": [
        {{"type": "contradiction", "message": "..."}}
      ]
    }}
    """
    
    print("🧠 Running Gemini 2.0 Flash analysis...")
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt,
        config={'response_mime_type': 'application/json'}
    )
    
    return json.loads(response.text)

# --- MAIN PIPELINE ---
def main():
    # Configuration
    HF_TOKEN = os.getenv("HF_TOKEN", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    
    # Step 1: Install dependencies (uncomment if needed)
    # install_dependencies()
    
    # Step 2: Extract audio from video
    audio_file = extract_audio(VIDEO_FILE)
    
    # Step 3: Run PyAnnote diarization
    speaker_timeline = run_diarization(audio_file, HF_TOKEN)
    
    # Step 4: Run Whisper transcription
    segments = transcribe_audio(audio_file)
    
    # Step 5: Align speakers
    aligned = align_speakers(segments, speaker_timeline)
    
    # Step 6: Build transcript
    transcript = build_transcript(aligned)
    print("\n" + "="*70)
    print("📝 TRANSCRIPT (PyAnnote Speaker Labels)")
    print("="*70)
    print(transcript)
    print("="*70)
    
    # Step 7: Extract names from video (Gemini Vision)
    name_timestamps = extract_names_from_video(VIDEO_FILE, GEMINI_API_KEY)
    
    # Step 8: Map speakers to real names
    speaker_map = {}
    speaker_map = map_speakers_to_names(aligned, name_timestamps, speaker_map)
    print(f"\n🗺️ Speaker Map: {speaker_map}")
    
    # Step 9: Run Gemini analysis
    analysis = run_gemini_analysis(transcript, GEMINI_API_KEY)
    
    # Update analysis with speaker map
    if "speaker_map" in analysis:
        analysis["speaker_map"].update(speaker_map)
    
    # Step 10: Save results
    output = {
        "transcript": transcript,
        "analysis": analysis
    }
    
    with open("corporate_brain_output.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print("\n✅ Results saved to 'corporate_brain_output.json'")
    print(f"📊 Participants: {analysis.get('participants', [])}")
    print(f"📊 Speaker Map: {analysis.get('speaker_map', {})}")
    print(f"📊 Decisions: {len(analysis.get('decisions', []))}")
    print(f"📊 Action Items: {len(analysis.get('action_items', []))}")
    print(f"📊 Flags: {len(analysis.get('flags', []))}")

if __name__ == "__main__":
    main()