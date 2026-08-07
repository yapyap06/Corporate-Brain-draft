// mock-data.js — All mock data matching real API shapes
// Used across all pages during Phase 1 (UI shell)

const mockData = {

  // Current logged-in user
  currentUser: {
    id: "u_001",
    name: "Alex Chen",
    email: "alex.chen@acmecorp.com",
    role: "Product Manager",
    org: "Acme Corp"
  },

  // Dashboard endpoint: GET /api/users/{id}/dashboard
  dashboard: {
    action_items: [
      { id: "ai_001", task: "Finalise Q3 budget proposal and share with finance team", deadline: "2026-08-10", meeting_id: "m_001", meeting_title: "Q2 Review", status: "overdue", priority: "high" },
      { id: "ai_002", task: "Evaluate three shortlisted vendors and submit comparison report", deadline: "2026-08-15", meeting_id: "m_001", meeting_title: "Q2 Review", status: "open", priority: "high" },
      { id: "ai_003", task: "Schedule follow-up with Product team on roadmap alignment", deadline: "2026-08-18", meeting_id: "m_002", meeting_title: "Vendor Selection", status: "open", priority: "medium" },
      { id: "ai_004", task: "Update Project Alpha risk register with new dependencies", deadline: "2026-08-20", meeting_id: "m_002", meeting_title: "Vendor Selection", status: "open", priority: "medium" },
      { id: "ai_005", task: "Draft communications plan for the Provider X transition", deadline: "2026-08-25", meeting_id: "m_003", meeting_title: "All-Hands May", status: "open", priority: "low" },
      { id: "ai_006", task: "Confirm legal sign-off on new SLA terms with Provider X", deadline: "2026-09-01", meeting_id: "m_003", meeting_title: "All-Hands May", status: "open", priority: "high" },
      { id: "ai_007", task: "Archive legacy vendor contracts and notify procurement", deadline: "2026-09-05", meeting_id: "m_001", meeting_title: "Q2 Review", status: "done", priority: "low" },
    ],
    flags: [
      { id: "f_001", severity: "warning", message: "Commitment conflict detected", detail: "Your commitment to evaluate Provider X (Q2 Review) may conflict with the May 3rd decision to freeze new vendor onboarding until Q4.", meeting_ref: "m_003", meeting_title: "All-Hands May" },
      { id: "f_002", severity: "info", message: "Duplicate discussion flagged", detail: "The budget approval topic was discussed in both Q2 Review and Vendor Selection — consider consolidating the decisions.", meeting_ref: "m_002", meeting_title: "Vendor Selection" },
    ],
    upcoming_meetings: [
      { id: "m_004", title: "Q3 Planning Kickoff", date: "2026-08-10", time: "10:00 AM", participants: 8, location: "Conference Room A" },
      { id: "m_005", title: "Engineering Sprint Review", date: "2026-08-12", time: "2:00 PM", participants: 5, location: "Virtual" },
      { id: "m_006", title: "Board Strategy Session", date: "2026-08-15", time: "9:00 AM", participants: 12, location: "Executive Floor" },
    ]
  },

  // Meetings list: GET /api/meetings
  meetings: [
    {
      id: "m_001",
      title: "Q2 Business Review",
      date: "2026-07-28",
      duration: "1h 22m",
      participants: ["Alex Chen", "Sarah Park", "Tom Wright", "Diana Ross"],
      status: "processed",
      decisions_count: 5,
      flags_count: 2,
      action_items_count: 7
    },
    {
      id: "m_002",
      title: "Vendor Selection — Project Alpha",
      date: "2026-07-15",
      duration: "48m",
      participants: ["Alex Chen", "Tom Wright", "James Liu"],
      status: "processed",
      decisions_count: 3,
      flags_count: 1,
      action_items_count: 4
    },
    {
      id: "m_003",
      title: "All-Hands — May Strategy Update",
      date: "2026-05-03",
      duration: "2h 05m",
      participants: ["Sarah Park", "Diana Ross", "James Liu", "Mike O'Brien", "Priya Mehta"],
      status: "processed",
      decisions_count: 8,
      flags_count: 0,
      action_items_count: 12
    },
    {
      id: "m_processing",
      title: "Engineering Architecture Review",
      date: "2026-08-06",
      duration: "—",
      participants: ["Tom Wright", "James Liu"],
      status: "processing",
      decisions_count: 0,
      flags_count: 0,
      action_items_count: 0
    }
  ],

  // Meeting detail: GET /api/meetings/{id}
  meetingDetail: {
    m_001: {
      id: "m_001",
      title: "Q2 Business Review",
      date: "2026-07-28",
      duration: "1h 22m",
      participants: ["Alex Chen", "Sarah Park", "Tom Wright", "Diana Ross"],
      flags: [
        { id: "f_d_001", type: "contradiction", severity: "warning", message: "Decision contradicts prior policy", detail: "Decision to switch to Provider X contradicts the May 3rd freeze on new vendor onboarding until Q4.", contradicts_meeting: "m_003", contradicts_decision: "d_m003_001" },
        { id: "f_d_002", type: "duplicate", severity: "info", message: "Duplicate discussion", detail: "Budget approval was discussed again without referencing the prior Q1 decision (Vendor Selection meeting).", contradicts_meeting: "m_002", contradicts_decision: "d_m002_001" },
      ],
      decisions: [
        { decision_id: "d_001", text: "Switch primary logistics vendor from Provider Y to Provider X effective Q4 2026", confidence: "firm_commitment", timestamp: "00:14:32", speaker: "Sarah Park", contradicts: "d_m003_001" },
        { decision_id: "d_002", text: "Increase Project Alpha budget by 15% to accommodate new vendor transition costs", confidence: "soft_agreement", timestamp: "00:31:15", speaker: "Alex Chen", contradicts: null },
        { decision_id: "d_003", text: "Conduct a full security audit of Provider X's infrastructure before contract signing", confidence: "firm_commitment", timestamp: "00:45:08", speaker: "Tom Wright", contradicts: null },
        { decision_id: "d_004", text: "Target completion of vendor transition by end of Q4 2026", confidence: "soft_agreement", timestamp: "01:02:44", speaker: "Sarah Park", contradicts: null },
        { decision_id: "d_005", text: "Establish monthly steering committee for Project Alpha oversight", confidence: "unresolved", timestamp: "01:18:20", speaker: "Diana Ross", contradicts: null },
      ],
      action_items: [
        { id: "ai_001", task: "Finalise Q3 budget proposal and share with finance team", assignee: "Alex Chen", deadline: "2026-08-10", status: "overdue" },
        { id: "ai_002", task: "Evaluate three shortlisted vendors and submit comparison report", assignee: "Alex Chen", deadline: "2026-08-15", status: "open" },
        { id: "ai_008", task: "Run security audit on Provider X", assignee: "Tom Wright", deadline: "2026-08-20", status: "open" },
        { id: "ai_009", task: "Draft vendor transition roadmap", assignee: "Sarah Park", deadline: "2026-08-25", status: "open" },
      ],
      transcript: [
        { timestamp: "00:00:12", speaker: "Sarah Park", text: "Alright, let's get started. We have a lot to cover today — the Q2 numbers, the vendor situation for Project Alpha, and budget sign-off before the board meeting next week." },
        { timestamp: "00:02:45", speaker: "Tom Wright", text: "I've reviewed both Provider X and Provider Y proposals in detail. The short version is Provider X gives us 22% cost savings over 36 months, and their SLA terms are considerably better." },
        { timestamp: "00:05:30", speaker: "Alex Chen", text: "That's a significant saving. What are the transition risks? We have a Q4 hard deadline on Project Alpha." },
        { timestamp: "00:07:15", speaker: "Tom Wright", text: "The main risk is the 6-week migration window. If we start now, we can hit Q4. But we'd need to do a full security audit first — their infrastructure is solid but our compliance team hasn't signed off." },
        { timestamp: "00:10:02", speaker: "Diana Ross", text: "I want to flag that we discussed a vendor freeze back in May. Did we formally lift that? I don't want us to get halfway through and have legal block us." },
        { timestamp: "00:12:40", speaker: "Sarah Park", text: "That freeze was a soft guideline, not a binding policy. I'm comfortable proceeding. We'll document this decision properly." },
        { timestamp: "00:14:32", speaker: "Sarah Park", text: "Let's make it official — we're switching to Provider X, effective Q4 2026. Tom, can you own the security audit?" },
        { timestamp: "00:14:55", speaker: "Tom Wright", text: "Confirmed. I'll scope the audit and have initial findings by August 20th." },
        { timestamp: "00:31:15", speaker: "Alex Chen", text: "On budget — the Provider X transition is going to require about a 15% uplift on Project Alpha. I'll need that approved before I can move forward with procurement." },
        { timestamp: "00:33:45", speaker: "Sarah Park", text: "Agreed in principle. Bring the formal numbers to the finance committee but you have my backing." },
        { timestamp: "00:45:08", speaker: "Tom Wright", text: "For the record — we should put the security audit as a firm precondition to signing any contract with Provider X. That's non-negotiable from a compliance standpoint." },
      ]
    }
  },

  // Graph data: GET /api/graph
  graph: {
    nodes: [
      { id: "m_001", type: "meeting", label: "Q2 Review", date: "Jul 28" },
      { id: "m_002", type: "meeting", label: "Vendor Selection", date: "Jul 15" },
      { id: "m_003", type: "meeting", label: "All-Hands May", date: "May 3" },
      { id: "d_001", type: "decision", label: "Switch to Provider X", confidence: "firm" },
      { id: "d_002", type: "decision", label: "Increase Alpha Budget", confidence: "soft" },
      { id: "d_003", type: "decision", label: "Security Audit Required", confidence: "firm" },
      { id: "d_m003_001", type: "decision", label: "Vendor Freeze Until Q4", confidence: "firm" },
      { id: "d_m002_001", type: "decision", label: "Evaluate 3 Vendors", confidence: "firm" },
      { id: "p_alpha", type: "project", label: "Project Alpha" },
      { id: "person_alex", type: "person", label: "Alex Chen" },
      { id: "person_sarah", type: "person", label: "Sarah Park" },
      { id: "person_tom", type: "person", label: "Tom Wright" },
      { id: "person_diana", type: "person", label: "Diana Ross" },
    ],
    edges: [
      { source: "m_001", target: "d_001", label: "produced" },
      { source: "m_001", target: "d_002", label: "produced" },
      { source: "m_001", target: "d_003", label: "produced" },
      { source: "m_002", target: "d_m002_001", label: "produced" },
      { source: "m_003", target: "d_m003_001", label: "produced" },
      { source: "d_001", target: "d_m003_001", label: "contradicts", isContradiction: true },
      { source: "d_001", target: "p_alpha", label: "relates-to" },
      { source: "d_002", target: "p_alpha", label: "relates-to" },
      { source: "person_alex",  target: "m_001", label: "participated-in" },
      { source: "person_sarah", target: "m_001", label: "participated-in" },
      { source: "person_tom",   target: "m_001", label: "participated-in" },
      { source: "person_diana", target: "m_001", label: "participated-in" },
      { source: "person_alex",  target: "m_002", label: "participated-in" },
      { source: "person_tom",   target: "m_002", label: "participated-in" },
    ]
  },

  // Chat: POST /api/chat (sample answers)
  chatSamples: [
    {
      query: "Why did we choose Provider X as our logistics vendor?",
      answer: "Based on the Q2 Business Review (July 28, 2026), the decision to switch to Provider X was driven by three key factors:\n\n1. **Cost savings** — Provider X offers a 22% reduction in costs over 36 months compared to Provider Y.\n2. **Better SLA terms** — Provider X's service level agreement was rated considerably stronger.\n3. **Project Alpha timeline** — The 6-week migration window aligns with the Q4 2026 hard deadline.\n\nThe decision was formally made by Sarah Park and is classified as a firm commitment, with a mandatory security audit as a precondition to signing.",
      citations: [
        { meeting_id: "m_001", meeting_title: "Q2 Business Review", decision_id: "d_001", excerpt: "Switch primary logistics vendor from Provider Y to Provider X effective Q4 2026" },
        { meeting_id: "m_001", meeting_title: "Q2 Business Review", decision_id: "d_003", excerpt: "Conduct a full security audit of Provider X's infrastructure before contract signing" },
      ]
    },
    {
      query: "What were the key decisions on Project Alpha?",
      answer: "Project Alpha has three active decisions across two meetings:\n\n1. **Switch to Provider X** (Q2 Review, Jul 28) — Firm commitment to change logistics vendor, effective Q4 2026.\n2. **15% budget increase** (Q2 Review, Jul 28) — Soft agreement to increase Project Alpha budget, pending finance committee sign-off.\n3. **Security audit required** (Q2 Review, Jul 28) — Firm commitment that a security audit is a precondition to any contract.\n\nNote: There is an active AI flag — Decision 1 may contradict the vendor freeze decision from the May 3rd All-Hands meeting.",
      citations: [
        { meeting_id: "m_001", meeting_title: "Q2 Business Review", decision_id: "d_001", excerpt: "Switch primary logistics vendor from Provider Y to Provider X" },
        { meeting_id: "m_001", meeting_title: "Q2 Business Review", decision_id: "d_002", excerpt: "Increase Project Alpha budget by 15%" },
        { meeting_id: "m_003", meeting_title: "All-Hands May", decision_id: "d_m003_001", excerpt: "Vendor freeze until Q4 — contradicts Provider X decision" },
      ]
    }
  ]
};
