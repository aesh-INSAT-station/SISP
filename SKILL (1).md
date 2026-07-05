---
name: lumio-dev
description: Development assistant for the Lumio/Unblur AI-powered ADHD learning platform. Use this skill whenever working on any part of the Lumio codebase — backend (FastAPI, XGBoost, FAISS, LangChain, n8n), frontend (React + TypeScript, MediaPipe, Recharts), database schemas, deployment, or any feature implementation. Triggers on any mention of Lumio, Unblur, focus tracker, CV module, distraction classifier, RAG engine, teacher dashboard, parent interface, student session, eye tracking overlay, or any component described in this skill.
---

# Lumio Development Skill

Lumio is an AI-powered ADHD early detection and learning support platform built for the IEEE CODE2CURE SIGHT Day Congress 4.0 challenge. It connects students, teachers, and parents in a single real-time ecosystem.

## Read first
Before writing any code, check `context/LUMIO_PROJECT_CONTEXT.md` for full architecture, schemas, and design decisions. Do not contradict decisions documented there.

---

## Stack at a glance

| Layer | Technology |
|---|---|
| **Backend** | FastAPI (Python), PostgreSQL (Supabase), Redis (Upstash), XGBoost, scikit-learn, FAISS, LangChain |
| **Automation** | n8n |
| **Frontend** | React + TypeScript + Tailwind CSS (web only — no React Native, no Expo) |
| **Design tokens** | Custom CSS variables (see Design System below) layered on top of Tailwind |
| **CV** | MediaPipe FaceMesh via CDN (browser-only — no video ever transmitted) |
| **LLM** | **Llama** (via Ollama locally or a hosted Llama API endpoint) — NOT Anthropic/Claude |
| **Deploy** | Railway (backend + n8n), Vercel (frontend) |

> ⚠️ **Platform is React web only.** There is no mobile app. Never generate React Native, Expo, or `StyleSheet` code.

---

## Design System — apply to every UI component

All frontend code must use these tokens and follow this visual language. They come from the Lumio homepage and must be consistent across **all** screens.

### CSS Variables (define in `:root` or a global `tokens.css`)
```css
:root {
  --bg:      #f5f4f0;   /* Warm off-white — universal background */
  --ink:     #1a1a1a;   /* Near-black — all text, borders, icons */
  --accent:  #ff5c00;   /* Burnt orange — CTAs, highlights, hover sparks */
  --muted:   #999999;   /* Cool grey — labels, captions, secondary text */
  --surface: #eeecea;   /* Cards, inputs, elevated panels */
  --border:  rgba(26,26,26,0.10);
}
```

### Typography
```
Display / Headings : font-family: 'Syne', sans-serif; font-weight: 800;
Body / Labels / Code: font-family: 'Syne Mono', monospace; font-weight: 400;

Google Fonts CDN:
  https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Syne+Mono&display=swap

Scale:
  --text-xs   : 11px / letter-spacing 0.2em / uppercase  → nav labels, micro-copy
  --text-sm   : 13px / letter-spacing 0.15em / uppercase  → tags, badges
  --text-base : 15px / line-height 1.9                    → body paragraphs
  --text-md   : clamp(22px, 3vw, 28px)                    → sub-headings, card titles
  --text-lg   : clamp(42px, 7vw, 96px) / letter-spacing -0.03em  → section headings
  --text-xl   : clamp(56px, 10vw, 140px) / letter-spacing -0.04em → hero/CTA
```

### Components — exact specs

**Buttons (pill shape only)**
```css
.btn {
  border-radius: 100px;
  padding: 17px 40px;
  border: 1.5px solid var(--border);
  background: transparent;
  color: var(--ink);
  font: 700 15px 'Syne', sans-serif;
  letter-spacing: 0.04em;
  transition: background 0.25s, color 0.25s, border-color 0.25s, transform 0.2s;
  cursor: pointer;
}
.btn:hover {
  background: var(--ink);
  color: var(--bg);
  border-color: var(--ink);
  transform: translateY(-3px);
}
.btn--accent:hover { background: var(--accent); border-color: var(--accent); }
```

**Inputs / Text Fields**
```css
.input {
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: 12px;
  padding: 14px 20px;
  font: 400 14px 'Syne Mono', monospace;
  color: var(--ink);
  outline: none;
}
.input:focus { border-color: var(--ink); }
.input::placeholder { color: var(--muted); }
```

**Cards / Panels**
```
background: var(--surface)
border: 1px solid var(--border)
border-radius: 0px  ← NO rounded corners on panels
padding: 40px 48px
NO box-shadow — depth from borders only
```

**Section Labels**
```
font: 'Syne Mono', 11px, uppercase, letter-spacing 0.2em
color: var(--accent)
always prefix with  "— "
```

**Accent glyph:** `✦` used as decorative bullet before button labels

### Motion rules
```
Reveal easing:    cubic-bezier(0.25, 0.46, 0.45, 0.94)
Reveal duration:  0.7s–0.9s
Hover duration:   0.2s–0.3s
Scroll reveal:    IntersectionObserver threshold 0.15
                  initial: opacity 0 + translateY(24px) → visible: opacity 1 + none
Stagger:          0.1s delay per sibling
No loading spinners — use opacity pulse or blur-to-focus transition instead
```

### Global noise texture overlay (apply once in App.tsx or index.css)
```css
body::before {
  content: '';
  position: fixed;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.035'/%3E%3C/svg%3E");
  background-size: 200px 200px;
  pointer-events: none;
  z-index: 1000;
  opacity: 0.4;
}
```

### What to NEVER do in the UI
```
✗ No purple, blue, or gradient color schemes
✗ No rounded corners on panels (buttons only)
✗ No drop shadows — borders only for depth
✗ No Inter, Roboto, or system fonts
✗ No role-selection question on the login page (role comes from URL param)
✗ No loading spinners
✗ No emoji in UI text (only ✦ glyph allowed)
✗ No React Native / Expo / StyleSheet code anywhere
```

---

## Role System & Auth

Three user roles: **Student · Teacher · Parent**
- Role passed via URL param: `?role=student | ?role=teacher | ?role=parent`
- Login interface NEVER asks role again — it is already known from the param
- Post-login routing:
  - `student` → `/student/session`
  - `teacher` → `/teacher/dashboard`
  - `parent`  → `/parent/overview`

---

## Student Session Interface — CV overlay

The student session page (`src/pages/student/SessionPage.tsx`) shows the student their **own webcam feed with a live computer-vision overlay** — giving a focus-tracking, sci-fi feel while keeping the Lumio design language.

### Visual layout
```
┌─────────────────────────────────────────────────────┐
│  nav: LUMIO²  —  [session label]            Unblur  │
├──────────────────────┬──────────────────────────────┤
│                      │                              │
│   WEBCAM FEED        │   LESSON / RAG CONTENT       │
│   + CV OVERLAY       │   (text, quiz, AI tutor)     │
│   (left ~40%)        │   (right ~60%)               │
│                      │                              │
├──────────────────────┴──────────────────────────────┤
│  FocusBar  ████████░░░░░░░  focus 74%   ✦ on track  │
└─────────────────────────────────────────────────────┘
```

### CVOverlay component (`src/components/CVOverlay.tsx`)

Renders on top of the `<video>` element using a `<canvas>` overlay. **No video data ever leaves the browser.**

```typescript
// Visual layers to draw on canvas (in order):
// 1. Scan-line grid — faint ink lines, 0.04 opacity, 32px spacing
// 2. FaceMesh landmarks — dot mesh in var(--accent) at 0.5 opacity
// 3. Gaze vector — line from pupil center toward estimated gaze point, accent colour
// 4. Head-pose axes — 3 colour-coded axis arrows (X/Y/Z) from nose tip
// 5. HUD bracket corners — 4 corner brackets around the face bounding box,
//    drawn in var(--ink), 2px stroke, 20px arm length
// 6. Data readout — top-left of video, Syne Mono 11px, var(--ink) on
//    semi-transparent var(--bg) pill:
//      GAZE  0.87
//      BLINK 14/min
//      POSE  +3° / -1°
//      FOCUS 0.74
// 7. Focus pulse ring — circle around face bbox; opacity pulses 0.2→0.6 when
//    focus_score < 0.45 (attention alert, no text shown to student)
```

**Styling rules for the video panel:**
```css
.session-cv-panel {
  position: relative;
  background: var(--ink);          /* dark surround so video pops */
  border: 1px solid var(--border);
  border-radius: 0;                /* consistent with design system */
  overflow: hidden;
}
.session-cv-panel video {
  width: 100%;
  display: block;
  opacity: 0.92;
  filter: contrast(1.05) saturate(0.9);  /* slight desaturate → matches b&w feel */
}
.session-cv-panel canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
/* Scan-line aesthetic overlay */
.session-cv-panel::after {
  content: '';
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    to bottom,
    transparent 0px,
    transparent 3px,
    rgba(26,26,26,0.025) 3px,
    rgba(26,26,26,0.025) 4px
  );
  pointer-events: none;
}
```

### Focus score compositing (unchanged formula)
```typescript
const computeFocusScore = (landmarks: FaceLandmarks): number => {
  const gazeScore  = computeGazeScore(landmarks);      // 0–1
  const blinkNorm  = normalizeBlink(blinkRate);         // 0–1
  const poseNorm   = normalizeHeadPose(headPoseDeg);   // 0–1
  return 0.4 * gazeScore + 0.3 * (1 - blinkNorm) + 0.3 * (1 - poseNorm);
};
```

### FocusBar (`src/components/FocusBar.tsx`)
```typescript
// Thin bar, full width, below both panels
// Fill: var(--accent) when focus < 0.45, var(--ink) otherwise
// Label: "focus {Math.round(score * 100)}%" in Syne Mono 11px
// Right badge: "✦ on track" or "✦ refocus" depending on score threshold
// Animate fill with CSS transition: width 0.6s cubic-bezier(0.25,0.46,0.45,0.94)
```

---

## LLM Integration — Llama (not Anthropic)

The project uses **Llama** as the LLM. Use the OpenAI-compatible chat endpoint that most Llama hosts expose (Ollama, Together AI, Groq, etc.).

### Backend LLM call pattern
```python
import httpx

LLAMA_BASE_URL = settings.LLAMA_BASE_URL       # e.g. http://localhost:11434/v1
LLAMA_MODEL    = settings.LLAMA_MODEL          # e.g. "llama3.1:8b" or "meta-llama/Llama-3-8b"
LLAMA_API_KEY  = settings.LLAMA_API_KEY        # "ollama" for local, real key for hosted

async def call_llama(system: str, user: str, max_tokens: int = 1000) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{LLAMA_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLAMA_API_KEY}"},
            json={
                "model": LLAMA_MODEL,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user}
                ]
            }
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
```

### LangChain wrapper (for RAG service)
```python
from langchain_community.llms import Ollama
from langchain_openai import ChatOpenAI   # works with any OpenAI-compat endpoint

llm = ChatOpenAI(
    base_url=settings.LLAMA_BASE_URL,
    api_key=settings.LLAMA_API_KEY,
    model=settings.LLAMA_MODEL,
    temperature=0.3,
    max_tokens=1000,
)
```

### Prompt structure (same schema, different provider)
```python
SYSTEM_TEACHER = """You are a pedagogical assistant for children with learning difficulties.
Archetype: {archetype}
Rules:
- Generate suggestions ONLY from provided context chunks
- NEVER use: ADHD, disorder, diagnosis, condition, autism
- Output valid JSON only matching the schema below. Nothing else.
Schema: {{"summary": str, "for_teacher": [str], "for_student": [str],
          "for_parent": [str], "sources": [str], "urgency": "low"|"medium"|"high",
          "professional_referral": bool}}"""
```

---

## File structure convention

```
backend/
  app/
    main.py
    config.py            # pydantic settings — includes LLAMA_BASE_URL, LLAMA_MODEL, LLAMA_API_KEY
    database.py          # async SQLAlchemy
    routers/
      auth.py
      sessions.py
      analytics.py
      rag.py
      homework.py
    services/
      rule_engine.py     # deterministic — no ML
      recommender.py     # rule → FAISS → Llama → DB
      rag_service.py     # FAISS + LangChain + Llama
      llm_service.py     # call_llama() helper
    models/
      distraction_clf.joblib
      risk_profiler.joblib
    faiss_index/
  scripts/
    generate_training_data.py
    train_classifier.py
    train_profiler.py
    ingest_kb.py
    seed_demo.py
  tests/
    test_auth.py
    test_analytics.py
    test_rag.py
    test_rule_engine.py

frontend/
  src/
    styles/
      tokens.css         # all CSS variables — imported once in index.tsx
    pages/
      student/
        SessionPage.tsx  # webcam + CV overlay + lesson content
        HomeworkPage.tsx
        ProgressPage.tsx
      teacher/
        DashboardPage.tsx
        ChatbotPage.tsx
        HomeworkPage.tsx
      parent/
        OverviewPage.tsx
        SessionHistoryPage.tsx
      LoginPage.tsx      # reads ?role= from URL, never shows role selector
    components/
      CVOverlay.tsx      # MediaPipe wrapper + canvas drawing
      FocusBar.tsx       # real-time focus bar
      ChatInterface.tsx
      FocusTrendChart.tsx
    hooks/
      useAuth.ts
      useFocusStream.ts
    i18n/
      ar.json
      fr.json
      en.json
```

---

## Core rules — never violate these

1. **No video on server** — MediaPipe discards every frame locally. Only `focus_score` JSON is transmitted.
2. **No diagnosis language** — All LLM output must pass regex filter: `ADHD|disorder|diagnosis|condition|autism` → regenerate if matched.
3. **Risk score gated** — Parent API endpoints NEVER return `risk_score` or `risk_tier`. Return `for_parent` suggestions only.
4. **Rule engine overrides LLM** — `professional_referral` is set by `rule_engine.py` ONLY. LLM value is always discarded.
5. **Backend frozen after Day 10** — No new endpoints after the backend freeze tag. UI uses what exists.
6. **Synthetic data for training** — XGBoost and RF/MLP train on synthetic data. Interface unchanged when real data arrives.
7. **React web only** — No React Native, no Expo, no `StyleSheet`. All UI is web (`tsx` + CSS tokens).
8. **LLM is Llama** — Never import `langchain_anthropic`, `anthropic`, or reference Claude in code. Use `llm_service.py`.

---

## Key implementation patterns

### WebSocket focus stream (backend)
```python
@router.websocket("/ws/focus/{student_id}")
async def focus_stream(websocket: WebSocket, student_id: str):
    await websocket.accept()
    async for data in websocket.iter_json():
        await redis.set(f"session:live:{student_id}", json.dumps(data), ex=7200)
        await redis.publish(f"pubsub:class:{data['class_id']}", json.dumps(data))
```

### XGBoost classifier endpoint
```python
@router.post("/analytics/classify")
async def classify_distraction(events: List[FocusEvent]):
    features = extract_features(events)
    cause_id = model.predict([features])[0]
    confidence = model.predict_proba([features])[0].max()
    return {"cause": CAUSE_LABELS[cause_id], "confidence": float(confidence)}
```

### Rule engine (deterministic — no ML)
```python
def classify_archetype(cause, risk_score, session_dur, hw_grade, streak_days):
    if risk_score > 0.75 and streak_days > 7:
        return "PERSISTENT_ADHD_RISK", True
    if cause == "fatigue" and risk_score > 0.5 and session_dur > 5400:
        return "SUSTAINED_FATIGUE_HIGH_RISK", False
    if cause == "difficulty" and hw_grade < 8:
        return "SUBJECT_DIFFICULTY_STRUGGLE", False
    if cause == "fatigue" and risk_score < 0.5:
        return "SIMPLE_FATIGUE", False
    if cause == "environment":
        return "ENVIRONMENTAL_DISTRACTION", False
    if cause == "difficulty":
        return "CONTENT_DIFFICULTY", False
    return "GENERAL_DISTRACTION", False
```

### n8n trigger pattern
```python
async def trigger_n8n(workflow: str, payload: dict):
    async with httpx.AsyncClient() as client:
        await client.post(f"{N8N_BASE_URL}/webhook/{workflow}", json=payload, timeout=5.0)
```

### Diagnosis language filter
```python
import re
BLACKLIST = re.compile(r"\b(ADHD|disorder|diagnosis|condition|autism)\b", re.IGNORECASE)

def filter_diagnosis_language(text: str) -> bool:
    return bool(BLACKLIST.search(text))  # True = needs regeneration
```

---

## Validation pipeline (4 safeguards)
1. **Schema** — Pydantic validation → retry once → static fallback
2. **Grounding** — keyword overlap each suggestion vs retrieved chunks (Jaccard threshold)
3. **Diagnosis filter** — regex blacklist → regenerate → 2 strikes → static fallback
4. **Referral override** — `rule_engine.professional_referral` always overwrites LLM field

---

## Environment variables
```
# LLM (Llama)
LLAMA_BASE_URL=http://localhost:11434/v1    # or hosted endpoint
LLAMA_MODEL=llama3.1:8b
LLAMA_API_KEY=ollama                        # "ollama" for local; real key for hosted

# Database
DATABASE_URL=postgresql://...              # Supabase connection string
REDIS_URL=redis://...                      # Upstash Redis URL

# Services
N8N_BASE_URL=http://n8n:5678
SENDGRID_API_KEY=
JWT_SECRET_KEY=                            # 32+ char random string
SUPABASE_URL=
SUPABASE_ANON_KEY=
```

---

## Demo seed data
Run `scripts/seed_demo.py` to create:
- 1 teacher: `teacher@demo.com` / `password`
- Student 1 "Yassine": 7 days focus_events, risk_tier=needs_attention, full suggested_actions
- Student 2: risk_tier=moderate
- Student 3: risk_tier=low
- 2 homework assignments, 1 submission with struggle_flag=True

---

## Common tasks reference

**Add a new API endpoint:**
1. Add route to appropriate router in `app/routers/`
2. Add Pydantic schema if needed
3. Write pytest integration test in `tests/`

**Retrain XGBoost classifier:**
1. Run `scripts/generate_training_data.py`
2. Run `scripts/train_classifier.py`
3. New `distraction_clf.joblib` auto-loaded on FastAPI restart

**Add to RAG knowledge base:**
1. Add PDFs to `rag-sources/` Supabase bucket
2. Run `scripts/ingest_kb.py`
3. New `faiss_index/` auto-loaded on RAG service restart

**Add new n8n workflow:**
1. Build workflow in n8n UI
2. Add trigger in `app/services/n8n_service.py`
3. Call `trigger_n8n("workflow_name", payload)` from the service layer

**Style a new component:**
1. Import `tokens.css` (already global — no import needed per component)
2. Use `var(--bg)`, `var(--ink)`, `var(--accent)`, `var(--surface)`, `var(--border)` only
3. Use `font-family: 'Syne', sans-serif` for headings, `'Syne Mono', monospace` for labels/code
4. All buttons must be pill-shaped (`border-radius: 100px`)
5. No shadows — borders only
