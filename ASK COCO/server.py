"""
server.py — Standalone Ask Coco Intelligence Server (ChromaDB + Groq)
"""
import os
import json
import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI
from dotenv import load_dotenv

# Load from MEETINGS/.env
_env_path = Path(__file__).parent.parent / "MEETINGS" / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
RESULTS_DIR = Path(__file__).parent.parent / "MEETINGS" / "results"
CHROMA_DB_PATH = Path(__file__).parent / "memory"

# Initialize Groq client
if GROQ_API_KEY:
    groq_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
else:
    groq_client = None

# Initialize ChromaDB Memory
collection = None

def init_memory():
    global collection
    logger.info("🔄 Initializing ChromaDB Memory System...")
    
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    try:
        # Uses sentence-transformers (CPU-based)
        embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        collection = chroma_client.get_or_create_collection(
            name="meeting_memory",
            embedding_function=embedding_function
        )
        logger.info("✅ Embedding function loaded! ChromaDB initialized.")
    except Exception as e:
        logger.warning(f"⚠️ Failed to load embedding function: {e}. Falling back to default.")
        collection = chroma_client.get_or_create_collection(name="meeting_memory")

    # Load all meetings from MEETINGS/results
    load_all_meetings()

def load_all_meetings():
    if not RESULTS_DIR.exists():
        logger.warning(f"Results dir {RESULTS_DIR} does not exist.")
        return

    global collection
    
    # Get existing source IDs from ChromaDB to avoid duplicates
    existing_sources = set()
    if collection.count() > 0:
        results = collection.get(include=["metadatas"])
        if results and results["metadatas"]:
            for meta in results["metadatas"]:
                if meta and "source" in meta:
                    existing_sources.add(meta["source"])

    logger.info("Syncing new meeting data into ChromaDB...")
    total_added = 0

    for p in RESULTS_DIR.glob("*.json"):
        if p.name.endswith(".status.json"):
            continue
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            job_id = data.get("job_id", p.stem)
            filename = data.get("filename", "Unknown Meeting")
            
            if filename in existing_sources:
                continue # Already loaded

            
            transcript_raw = data.get("transcript", [])
            snippets = []
            
            for item in transcript_raw:
                timestamp = item.get("timestamp", "00:00:00")
                speaker = item.get("speaker", "Unknown")
                text = item.get("text", "")
                full_line = f"[{timestamp}] {speaker}: {text}"
                snippets.append({
                    "timestamp": timestamp,
                    "speaker": speaker,
                    "text": text,
                    "full_line": full_line
                })

            if snippets:
                ids = []
                documents = []
                metadatas = []
                for idx, snippet in enumerate(snippets):
                    ids.append(f"{job_id}_transcript_{idx:04d}")
                    documents.append(snippet["full_line"])
                    metadatas.append({
                        "timestamp": snippet["timestamp"],
                        "speaker": snippet["speaker"],
                        "source": filename,
                        "full_text": snippet["text"]
                    })
                
                collection.add(ids=ids, documents=documents, metadatas=metadatas)
                total_added += len(ids)

            # Store Decisions and Action items
            decisions = data.get("decisions", [])
            action_items = data.get("action_items", [])
            if decisions or action_items:
                summary_lines = [f"📋 SUMMARY FOR: {filename}"]
                if decisions:
                    summary_lines.append("\n📝 Decisions:")
                    for i, d in enumerate(decisions, 1):
                        summary_lines.append(f"   {i}. {d.get('text', '')}")
                if action_items:
                    summary_lines.append("\n✅ Action Items:")
                    for i, a in enumerate(action_items, 1):
                        summary_lines.append(f"   {i}. {a.get('task', '')} (Assignee: {a.get('assignee', 'Unassigned')})")
                
                summary_text = "\n".join(summary_lines)
                collection.add(
                    ids=[f"{job_id}_summary"],
                    documents=[summary_text],
                    metadatas=[{
                        "timestamp": "00:00:00",
                        "speaker": "System",
                        "source": filename,
                        "full_text": summary_text
                    }]
                )
                total_added += 1

        except Exception as e:
            logger.warning(f"Error loading {p}: {e}")

    logger.info(f"✅ Finished loading. {total_added} total snippets stored.")

# --- HELPERS ---
MEETING_KEYWORDS = [
    'meeting', 'discuss', 'agenda', 'decision', 'action item', 'task',
    'summarize', 'summary', 'explain', 'tell', 'project', 'audit',
    'what', 'who', 'why', 'when', 'how', 'which'
]

def is_meeting_related(question: str) -> bool:
    question_lower = question.lower().strip()
    for kw in MEETING_KEYWORDS:
        if kw in question_lower:
            return True
    return len(question_lower) > 5

# --- FASTAPI APP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    init_memory()
    yield

from fastapi.responses import FileResponse

app = FastAPI(title="Ask Coco Engine", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def serve_index():
    index_path = Path(__file__).parent / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"detail": "index.html not found"}


class ChatRequest(BaseModel):
    query: str

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Empty query")
    
    if not is_meeting_related(req.query):
        return {
            "answer": "🤷 I'm Coco, your meeting intelligence assistant. I can only answer questions about your meetings. Please ask me about decisions, speakers, or summaries!",
            "citations": []
        }

    if not groq_client:
        return {
            "answer": "❌ GROQ_API_KEY is missing. Please add GROQ_API_KEY to your MEETINGS/.env file and restart the server.",
            "citations": []
        }
        
    try:
        # Semantic search
        results = collection.query(
            query_texts=[req.query],
            n_results=5
        )
        
        context_lines = []
        citations = []
        
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                timestamp = metadata.get('timestamp', 'Unknown')
                speaker = metadata.get('speaker', 'Unknown')
                source = metadata.get('source', 'Meeting')
                context_lines.append(f"[{source} @ {timestamp}] {speaker}: {doc}")
                citations.append({
                    "filename": source,
                    "timestamp": timestamp,
                    "speaker": speaker,
                    "excerpt": metadata.get("full_text", doc)
                })
                
        if not context_lines:
            return {
                "answer": "🤷 I couldn't find any relevant information about that in your meeting records.",
                "citations": []
            }
            
        context = "\n".join(context_lines)
        
        prompt = f"""
You are Coco, the AI assistant for Corporate Brain. You answer questions based ONLY on the meeting transcripts provided below.

**Context (from processed meetings):**
{context}

**Question:** {req.query}

**Instructions:**
1. Answer the question clearly and accurately using ONLY the context above.
2. If the context doesn't contain the answer, politely say you don't know based on the current meeting records, and you MUST prefix your response with exactly "NO_INFO: ".
3. Keep your answer professional but friendly.
"""
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800
        )
        
        answer = response.choices[0].message.content
        
        if answer.startswith("NO_INFO:"):
            answer = answer.replace("NO_INFO:", "", 1).strip()
            citations = []
            
        return {
            "answer": answer,
            "citations": citations
        }
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
