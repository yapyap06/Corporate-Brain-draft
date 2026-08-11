"""
config.py — All settings loaded from environment variables.
Never hardcode API keys. Copy .env.example → .env and fill in your values.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Locate .env file relative to this file
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path)


class Settings:
    # ── AI Keys ──────────────────────────────────────────────────────────
    GEMINI_API_KEY: str  = os.getenv("GEMINI_API_KEY", "").strip().lstrip("-")
    AGNES_API_KEY:  str  = os.getenv("AGNES_API_KEY", "")
    AGNES_BASE_URL: str  = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
    HF_TOKEN:       str  = os.getenv("HF_TOKEN", "")         # HuggingFace for PyAnnote
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")

    # ── Model choices ────────────────────────────────────────────────────
    WHISPER_MODEL:  str  = os.getenv("WHISPER_MODEL", "small")    # tiny/base/small/medium
    DIARIZATION_MODEL: str = "pyannote/speaker-diarization-3.1"

    # ── Storage ──────────────────────────────────────────────────────────
    UPLOAD_DIR:   Path = Path(os.getenv("UPLOAD_DIR",   "./uploads"))
    RESULTS_DIR:  Path = Path(os.getenv("RESULTS_DIR",  "./results"))
    FRAMES_DIR:   Path = Path(os.getenv("FRAMES_DIR",   "./frames"))

    # ── Processing ───────────────────────────────────────────────────────
    MAX_FILE_SIZE_MB:  int  = int(os.getenv("MAX_FILE_SIZE_MB", "2000"))
    FRAME_INTERVAL_S:  int  = int(os.getenv("FRAME_INTERVAL_S", "15"))  # Gemini Vision: every N seconds
    USE_GPU:           bool = os.getenv("USE_GPU", "true").lower() == "true"

    # ── Demo mode (no real API keys needed) ──────────────────────────────
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() == "true"
    
    # ── Fast mode ────────────────────────────────────────────────────────
    SKIP_DIARIZATION: bool = os.getenv("SKIP_DIARIZATION", "false").lower() == "true"

    # ── CORS ─────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: list = [
        "http://localhost:8765",
        "http://127.0.0.1:8765",
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", "http://localhost:8765"),
    ]

    def validate(self) -> list[str]:
        """Return list of missing required config items."""
        errors = []
        if not self.GEMINI_API_KEY and not self.DEMO_MODE:
            errors.append("GEMINI_API_KEY is required (or set DEMO_MODE=true)")
        if not self.DEEPGRAM_API_KEY and not self.DEMO_MODE:
            errors.append("DEEPGRAM_API_KEY is required for transcription (or set DEMO_MODE=true)")
        return errors


settings = Settings()

# Ensure storage directories exist
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
