# gemma-chat-vue

iOS Light Design System — Vue 3 SPA chatting with local AI (llama.cpp on Android Termux) or any OpenAI-compatible API.

**Live:** https://gemma-chat-local-agooxo-puss-agooxo-puss-projects.vercel.app

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Vue 3 SPA (Vercel)                    │
│   gemma-chat-vue                                        │
│   ┌──────────────┐    ┌──────────────────────────────┐  │
│   │  iOS Design  │    │  Hermes-Style Research      │  │
│   │  System      │    │  Pipeline                   │  │
│   │  (CSS vars)  │    │  /v1/research               │  │
│   └──────────────┘    └──────────────────────────────┘  │
└────────────┬────────────────────────────────────────────┘
             │ CORS Proxy (phone) or Direct API URL
             ▼
┌─────────────────────────────────────────────────────────┐
│  Android Termux (Sony SO-51B)                          │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │llama.cpp   │  │ CORS Proxy   │  │ DuckDuckGo    │  │
│  │gemma-2b    │  │ /v1/research │  │ HTML Search   │  │
│  │context=2048│  │ + Page Fetch │  │ + Text Extr.  │  │
│  └────────────┘  └──────────────┘  └───────────────┘  │
│  localhost:8080        :18080                          │
└────────────┬────────────────────────────────────────────┘
             │ SSH Reverse Tunnel (localhost.run / Cloudflare)
             ▼
┌─────────────────────────────────────────────────────────┐
│  Public URL (e.g. trycloudflare.com)                   │
│  HTTPS → Vue SPA → llama.cpp inference                  │
└─────────────────────────────────────────────────────────┘
```

---

## Two Connection Modes

### 1. Local Mode (default)
- Connect to your **Android phone's CORS proxy** via public tunnel URL
- Phone runs `llama.cpp` (local Gemma 2B model) + CORS proxy
- Free inference, no API costs
- Tunnel: `localhost.run` or `serveo` (SSH reverse tunnel)

### 2. Direct Mode
- Connect to **any OpenAI-compatible API endpoint**
- Built-in `/v1/research` endpoint uses DuckDuckGo HTML search + page content extraction
- No API keys required for basic use
- Set: API URL + Model name

---

## Project Structure

```
gemma-chat-web/
├── index.html              # SPA entry
├── package.json            # Vue 3 + Vite
├── vite.config.js          # Vite config (no backend proxy)
├── vercel.json             # Vercel static deployment
├── public/                 # Static assets
└── src/
    ├── main.js             # Vue app entry
    ├── App.vue             # Everything: UI + logic + styles
    └── style.css           # Global resets (minimal)
```

---

## Design System

iOS Light Design System (pure CSS, no framework):

```css
--bg: #FFFFFF
--surface: #F5F5F7
--accent: #007AFF
--text: #1D1D1F
--text2: #86868B
--border: #E5E5EA
--radius: 12px
--shadow: 0 4px 12px rgba(0,0,0,0.08)
```

**Font stack:** `-apple-system, BlinkMacSystemFont, 'SF Pro Display', system-ui, sans-serif`

---

## Hermes-Style Research Pipeline

```
User question
    │
    ▼  isSearch() triggers?
    ├─ NO  → streamChat() direct to model
    └─ YES → doResearch() pipeline:
                │
                ├─ 1. POST /v1/research
                │     └─ CORS proxy:
                │           ├─ DuckDuckGo HTML search
                │           ├─ Fetch top 3 pages (parallel)
                │           └─ Extract text via regex (no bs4)
                │
                ├─ 2. Display research block
                │     └─ Title + URL + snippet + expandable content
                │
                └─ 3. streamChat() with enriched context
                      └─ System prompt includes full page text
```

**Response flow:**
1. Show loading dots
2. Display research block (3 sources, expandable)
3. Stream model response (Markdown rendered)

---

## Backend Files (Android Termux)

These stay on the phone, not in this repo:

| File | Purpose |
|------|---------|
| `cors_proxy.py` | CORS reverse proxy + `/v1/research` pipeline |
| `watchdog_llama.sh` | Auto-restart llama.cpp if stuck/OOM |
| `patch_openai_client.py` | MiniMax streaming fix via `sys.meta_path` |
| `run_patched_gateway.sh` | Launch Hermes gateway with patched Python path |

### CORS Proxy Endpoints

```
POST /v1/chat/completions  →  proxy to llama.cpp
POST /v1/models            →  proxy to llama.cpp
POST /v1/search            →  DuckDuckGo HTML search (returns snippets)
POST /v1/research          →  Hermes pipeline: search + fetch + extract + return context
GET  /test.html            →  Browser test UI
```

---

## Deployment

### Frontend (Vercel)
```bash
npm install
npm run build
# Deploy dist/ to Vercel (REST API, no CLI needed)
```

Or push to GitHub — Vercel auto-deploys.

### Backend (Android Termux)
```bash
# Install
pip install httpx

# Run CORS proxy
python3 cors_proxy.py

# Run llama.cpp (context=2048 for research support)
llama-server -m models/gemma-2-2b-it-abliterated-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 -ngl 0 -c 2048

# Tunnel (localhost.run)
ssh -o StrictHostKeyChecking=no -R 80:localhost:18080 nokey@localhost.run
```

---

## Configuration

Settings persist in `localStorage` (key: `gc-v4`):

| Key | Default | Description |
|-----|---------|-------------|
| `connMode` | `local` | `local` or `direct` |
| `localTunnelUrl` | trycloudflare URL | Phone tunnel endpoint |
| `directApiUrl` | empty | Direct API base URL |
| `apiModel` | model filename | Model name |
| `maxTokens` | 512 | Max completion tokens |
| `systemPrompt` | Chinese helpful assistant | System prompt |

---

## Tech Stack

- **Frontend:** Vue 3 (Composition API) + Vite
- **Styling:** Pure CSS, iOS Design System, no framework
- **Icons:** Inline Lucide SVGs
- **Backend:** Python 3.13 + httpx on Android Termux
- **AI:** llama.cpp (local Gemma 2B) or any OpenAI-compatible API
- **Tunnel:** SSH reverse tunnel (localhost.run / serveo)
- **Deploy:** Vercel (static SPA)

---

## Known Constraints

- **llama.cpp context:** 2048 tokens max (hardware limited on phone)
- **Page content:** Truncated to 800 chars/page to fit context
- **Search:** DuckDuckGo HTML only (no JavaScript rendering)
- **Tunnel URL:** Changes on reconnect (no fixed domain without paid plan)
