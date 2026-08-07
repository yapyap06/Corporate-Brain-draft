# Corporate Brain — Build Brief for Coding Agent

> **Read this entire file before writing any code.** This is the single source of truth for scope, structure, tech stack, and priorities. Do not add features, pages, or integrations beyond what is listed here without checking with the team first — scope creep is the #1 risk on this project.

---

## 1. What we're building (one paragraph)

Corporate Brain is a web app that turns meetings into a permanent, connected organizational memory instead of isolated transcripts. It captures a meeting (audio → transcript), extracts decisions and commitments, checks new decisions against everything the org has decided before (flagging contradictions, duplicate discussions, policy conflicts), and gives every employee a personalized dashboard of their own commitments. Everything is powered by one underlying data structure: the **Corporate Memory Graph** (Neo4j), which links People, Meetings, Decisions, Action Items, Documents, Risks, and Policies together.

**Positioning:** We are not a transcription tool (Otter/Fireflies already own that). We are an **organizational intelligence platform**. Every screen should reinforce that this app remembers *why* things were decided, not just *what* was said.

---

## 2. The 3 flagship features (build these for real — everything else is secondary)

1. **Corporate Memory Graph** — the core data layer. Every meeting, decision, person, project, document, and risk becomes a node; relationships (caused-by, related-to, contradicts, assigned-to) become edges.
2. **Decision Assistant** — during/after a meeting, surfaces relevant past decisions, and flags: policy conflicts, duplicate discussions, missing stakeholders. This is our differentiator vs. every existing meeting tool.
3. **Promise Tracker** — a personalized workspace per participant showing their commitments, deadlines, dependencies, and the meeting/decision that generated each one.

Everything else in the original slide deck (Executive Dashboard, Decision Time Machine deep-dive, Hidden Expert Finder, live Zoom/Teams bot join, web-search benchmarking, Jira/Asana sync) is **out of scope for this build**. If time allows after the above 3 are solid, add polish — not new systems.

---

## 3. Tech stack (do not substitute without asking)

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React.js + Next.js, TypeScript, Tailwind CSS | App Router, SSR where useful |
| Backend API | Python (FastAPI) | All business logic + AI orchestration lives here |
| Real-time (if needed) | Node.js | Only if we implement live meeting capture — otherwise skip |
| Speech-to-text | OpenAI Whisper | Run on uploaded audio files, not live streams, for this build |
| AI reasoning | Gemini 2.5 Flash (or Claude, whichever key is available) | Entity extraction, decision detection, contradiction reasoning |
| Knowledge graph | Neo4j | The Corporate Memory Graph — the heart of the system |
| Vector search | ChromaDB | Embeddings for semantic search / RAG in the Chat feature |
| Structured data | PostgreSQL | Users, orgs, meeting metadata, permissions |
| Auth | Google OAuth 2.0 | Simple login for hackathon — skip full RBAC unless time allows |
| Hosting | Local/dev for hackathon; GCP (Cloud Run) if deploying | Don't spend hackathon time on cloud infra until the app works locally |

**For the hackathon build:** get everything running locally first (docker-compose for Neo4j + Postgres is fine). Cloud deployment is a nice-to-have for the demo, not a requirement — a well-recorded local demo is safer than a live cloud demo that might break.

---

## 4. Input handling (important constraint)

We are **not** building live Zoom/Teams/Google Meet bot integration for this build — too fragile for a hackathon timeline. Instead:

- Users **upload an audio/video file** of a meeting (or we use 2-3 pre-recorded sample meetings for the demo).
- The pipeline runs: upload → Whisper transcription (with speaker diarization) → Gemini entity/decision extraction → write to Neo4j → available in the app.
- For the demo, prepare **two sample meetings where the second one contradicts a decision from the first** — this is the single most important test case, since it proves the Decision Assistant actually works.

---

## 5. Site structure — left side menu, 5 pages

```
┌───────────────┬─────────────────────────────────┐
│  🧠 Corporate │                                   │
│     Brain     │                                   │
│               │                                   │
│  📊 Dashboard │         (page content)            │
│  🗂 Meetings  │                                   │
│  🕸 Memory    │                                   │
│     Graph     │                                   │
│  💬 Ask Brain │                                   │
│  ⚙️ Settings  │                                   │
│               │                                   │
└───────────────┴─────────────────────────────────┘
```

Keep the side menu fixed, 5 items only, icon + label. Don't add more nav items even if a feature seems to need its own page — nest it inside one of the 5 below.

---

### Page 1 — Dashboard (`/dashboard`)
**Purpose:** This is Promise Tracker's home. What a user sees first — their own accountability view, not a company-wide view.

**Must include:**
- Greeting header: "Good morning, {name}. You have {n} outstanding commitments."
- List of the user's action items, each showing: task text, deadline, source meeting (linked), status (open/done/overdue), priority
- A small "Recent AI Flags relevant to you" widget — e.g. "Your commitment on Project Alpha may conflict with a decision from May 3rd meeting"
- Upcoming meetings (from metadata, doesn't need calendar integration — can be manually listed for demo)

**Data needed:** `GET /api/users/{id}/dashboard` → `{ action_items: [...], flags: [...], upcoming_meetings: [...] }`

---

### Page 2 — Meetings (`/meetings` and `/meetings/{id}`)
**Purpose:** List of processed meetings; detail view is where transcript + decisions + flags live.

**List view must include:**
- Table/cards: meeting title, date, participants, "# decisions extracted", "# flags raised"
- Upload button (upload audio file → triggers pipeline)

**Detail view must include:**
- Transcript panel (speaker-attributed, timestamped, scrollable)
- Decisions panel: each decision tagged **Firm Commitment / Soft Agreement / Unresolved**, with a link to jump to that point in the transcript
- AI Flags banner at top if any exist: contradiction, duplicate discussion, policy conflict, missing stakeholder — each flag should say *why* (which past decision it conflicts with, linked)
- Action items extracted from this meeting, with assignee

**Data needed:**
- `POST /api/meetings/upload` (audio file) → triggers pipeline, returns meeting_id
- `GET /api/meetings` → list
- `GET /api/meetings/{id}` → `{ transcript: [...], decisions: [...], flags: [...], action_items: [...] }`

---

### Page 3 — Memory Graph (`/graph`)
**Purpose:** The visual "wow" screen. Shows the Corporate Memory Graph as an explorable network.

**Must include:**
- Interactive graph visualization (nodes: Meeting, Decision, Person, Project; edges: relates-to, contradicts, caused-by, assigned-to)
- Click a Decision node → side panel shows the full "Decision Thread": which meetings/discussions led to it, and what (if anything) it contradicts
- A simple filter (by project or by date range) so the graph doesn't become an unreadable hairball for the demo — keep the sample dataset small and curated (10-20 nodes) so this always renders cleanly

**Data needed:** `GET /api/graph?filter=...` → nodes + edges in a format your graph library expects (e.g. react-force-graph or vis.js — pick whichever is fastest to integrate, don't build custom rendering)

**Note:** This screen only needs to look good and be clickable for the demo — it does not need to support arbitrary large-scale graphs. Prioritize visual clarity over completeness.

---

### Page 4 — Ask Brain (`/chat`)
**Purpose:** Natural-language Q&A over the Corporate Memory Graph, with citations.

**Must include:**
- Simple chat interface (input box, message history)
- Answers must cite the source meeting/decision they came from (clickable, links back to Page 2)
- Example queries to suggest to the user as placeholder/starter chips: "Why did we choose Vendor B?" / "What were the key decisions on Project Alpha?"

**Data needed:** `POST /api/chat` with `{ query: string }` → `{ answer: string, citations: [{meeting_id, decision_id, excerpt}] }`

**Implementation note:** Use ChromaDB for retrieval (semantic search over transcripts/decisions) + Gemini for answer synthesis. Keep this simple — RAG over the sample meeting dataset, not the whole internet.

---

### Page 5 — Settings (`/settings`)
**Purpose:** Minimal — mostly there to look like a real product, not a core build focus.

**Must include (keep this light):**
- User profile (name, email from Google OAuth)
- List of "connected" integrations shown as **disabled/coming soon** badges: Jira, Asana, Microsoft Teams, Zoom — do NOT build real integrations, just show the roadmap visually
- Org info (name, member list) — static/mock is fine

---

## 6. Data model sketch

### Neo4j (Corporate Memory Graph)
```
Nodes: Person, Meeting, Decision, Project, Document, ActionItem, Risk, Policy
Edges:
  (Person)-[:PARTICIPATED_IN]->(Meeting)
  (Meeting)-[:PRODUCED]->(Decision)
  (Decision)-[:RELATES_TO]->(Project)
  (Decision)-[:CONTRADICTS]->(Decision)
  (Decision)-[:BASED_ON]->(Meeting)          // for cross-meeting decision threads
  (ActionItem)-[:ASSIGNED_TO]->(Person)
  (ActionItem)-[:CREATED_IN]->(Meeting)
  (Decision)-[:VIOLATES]->(Policy)
```

### PostgreSQL (app/structured data)
```
users(id, name, email, org_id)
organizations(id, name)
meetings(id, title, date, uploaded_by, audio_url, status)
```

### Decision object shape (used across backend + frontend — lock this early, all 4 people build against it)
```json
{
  "decision_id": "d_001",
  "meeting_id": "m_001",
  "text": "Switch vendor to Provider X",
  "confidence": "soft_agreement",
  "timestamp": "00:14:32",
  "speaker": "Alice",
  "contradicts": null,
  "linked_meetings": ["m_prev_002"]
}
```

---

## 7. Build order (do not build Page 3 or 4 before Page 1/2 have real data flowing)

1. Scaffold Next.js app with the 5-page shell + side nav, all pages rendering with **mock JSON** matching the shapes above.
2. Backend: file upload → Whisper → transcript stored.
3. Backend: transcript → Gemini entity/decision extraction → written to Neo4j.
4. Wire Page 1 (Dashboard) and Page 2 (Meetings) to real API — easiest to verify end-to-end.
5. Build contradiction-detection logic (compare new decisions against existing graph) — this is the feature the whole pitch depends on, test it explicitly with the two-contradicting-meetings sample data.
6. Wire Page 3 (Graph) and Page 4 (Chat) last — they're the most visually impressive but least structurally critical; can degrade gracefully if time runs short.
7. Page 5 (Settings) — do last, keep minimal.

---

## 8. Explicit non-goals for this build

Do not implement, even if referenced in the original slide deck:
- Live meeting bot joining Zoom/Teams/Google Meet
- Real Jira/Asana/Trello sync
- Multi-tenant org management / full RBAC
- Whiteboard image OCR/diagram extraction
- Web-search benchmarking during meetings
- Executive analytics dashboard beyond what's on Page 1

If asked to add any of these, stop and confirm with the team first — they are roadmap items for the pitch, not build targets.
