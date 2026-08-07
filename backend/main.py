"""
Corporate Brain — FastAPI Application Entry Point
Run with: uvicorn backend.main:app --reload --port 8000
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Startup / Shutdown ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("  Corporate Brain API starting up")
    logger.info(f"  DEMO_MODE    = {os.getenv('DEMO_MODE', 'true')}")
    logger.info(f"  GEMINI_KEY   = {'SET' if os.getenv('GEMINI_API_KEY') else 'NOT SET (using demo)'}")
    logger.info(f"  NEO4J_URI    = {os.getenv('NEO4J_URI', 'not configured')}")
    logger.info(f"  WHISPER_MODEL= {os.getenv('WHISPER_MODEL', 'base')}")
    logger.info("=" * 60)

    # Seed demo data on startup
    from backend.database import seed_demo_data
    seed_demo_data()
    logger.info("Demo data seeded — 3 sample meetings loaded")

    yield  # App is running

    logger.info("Corporate Brain API shutting down")


# ── App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "Corporate Brain API",
    description = "Organizational intelligence platform powered by Coco, Neo4j, Whisper, and Gemini",
    version     = "1.0.0",
    lifespan    = lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────
# Allow requests from the frontend (served on port 8765)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8765",
        "http://127.0.0.1:8765",
        os.getenv("FRONTEND_URL", "http://localhost:8765"),
        "*",  # Allow all for local dev — restrict in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────
from backend.routers import rooms, meetings

app.include_router(rooms.router)
app.include_router(meetings.router)

# ── Health check ──────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service":   "Corporate Brain API",
        "version":   "1.0.0",
        "status":    "running",
        "demo_mode": os.getenv("DEMO_MODE", "true") == "true",
        "docs":      "/docs",
    }

@app.get("/health")
async def health():
    from backend.database import meetings_db, rooms_db
    return {
        "status":         "ok",
        "meetings_count": len(meetings_db),
        "rooms_count":    len(rooms_db),
    }
