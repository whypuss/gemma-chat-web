# gemma-chat-vue

iOS Light Design System — Vue 3 SPA chatting with local AI (llama.cpp on Android Termux) or any OpenAI-compatible API.

**Live:** https://gemma-chat-n9bpwb3nb-agooxo-puss-projects.vercel.app

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Vue 3 SPA (Vercel)                       │
│   ┌────────────────┐    ┌────────────────────────────────┐ │
│   │  iOS Design    │    │  Hermes-Style Research        │ │
│   │  System        │    │  Pipeline                    │ │
│   │  (CSS vars)    │    │  /v1/research               │ │
│   └────────────────┘    └────────────────────────────────┘ │
└────────────────────┬─────────────────────────────────────────┘
                     │ CORS Proxy (phone) or Direct API URL
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  Android Termux (Sony SO-51B)                              │
│  ┌────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │llama.cpp   │  │ CORS Proxy     │  │ DuckDuckGo     │  │
│  │gemma-2b    │  │ /v1/research   │  │ HTML Search    │  │
│  │context=2048│  │ + Page Fetch   │  │ + Regex Extr.  │  │
│  └────────────┘  └────────────────┘  └────────────────┘  │
│  localhost:8080              :18080                        │
└────────────────────┬─────────────────────────────────────────┘
                     │ SSH Reverse Tunnel (serveo / Cloudflare)
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  Public URL (e.g. serveo.net or trycloudflare.com)         │
│  HTTPS → Vue SPA → llama.cpp inference + search             │
└──────────────────────────────────────────────────────────────┘
```

---

## Two Connection Modes

### 1. Local Mode (default)
- Connect to your **Android phone's CORS proxy** via public tunnel URL
- Phone runs `llama.cpp` (local Gemma 2B model) + CORS proxy
- Free inference, no API costs
- Tunnel: `serveo.net` or `localhost.run` (SSH reverse tunnel)

### 2. Direct Mode
- Connect to **any OpenAI-compatible API endpoint**
- Built-in `/v1/research` endpoint uses DuckDuckGo HTML search + page content extraction
- No API keys required for basic use
- Set: API URL + Model name

---

## Project Structure

```
gemma-chat-web/
├── README.md               # This file
├── index.html              # SPA entry
├── package.json            # Vue 3 + Vite
├── vite.config.js          # Vite config (no backend proxy)
├── vercel.json             # Vercel static deployment
├── public/                 # Static assets
└── src/
    ├── main.js             # Vue app entry
    ├── App.vue             # Everything: UI + logic + styles
    └── style.css           # Global resets (minimal)

phone/                      # Android Termux deployment files
├── cors_proxy.py          # CORS proxy + Hermes /v1/research pipeline
├── watchdog.sh            # Auto-restart: llama.cpp, CORS proxy, serveo tunnel
├── start_all.sh           # Launch all services
├── start_cf_tunnel.sh     # Cloudflare tunnel launcher
└── start_cf_v2.sh         # Cloudflare tunnel v2
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
                │     └─ CORS proxy (phone :18080):
                │           ├─ DuckDuckGo HTML search
                │           │     └─ User-Agent rotation (5 browser profiles)
                │           ├─ Fetch top 3 pages (parallel, semaphore-limited)
                │           │     └─ Regex text extraction (no bs4)
                │           └─ Sentence-aware truncation (600 chars/page)
                │
                ├─ 2. Display research block
                │     └─ Title + URL + snippet + expandable content
                │
                └─ 3. streamChat() with enriched context
                      └─ System prompt includes full page text
```

**Key technical choices:**
- **No bs4:** Pure regex extraction handles 95% of pages well, no C-extension dependency risk
- **User-Agent pool:** 5 rotating profiles to reduce DDG CAPTCHA risk
- **Semaphore concurrency:** Max 3 parallel page fetches to avoid IP blocking
- **Sentence-aware truncation:** Cuts at sentence boundaries, not mid-word
- **HTML entities:** Properly decoded via `html.unescape()` (handles `&amp;`, `&quot;`, `&#39;`, `&nbsp;` etc.)

**Response flow:**
1. Show loading dots
2. Display research block (3 sources, expandable)
3. Stream model response (Markdown rendered)

---

## Security

### API Key Protection (Optional)

`cors_proxy.py` supports optional `X-API-Key` header authentication:

```python
API_KEY = "gemma-local-2025"  # Change this! Set to None to disable
```

Clients must send `X-API-Key: gemma-local-2025` on every request. Without it, the proxy returns HTTP 401.

### Public Tunnel Warning

`serveo.net` / `localhost.run` expose your phone's CORS proxy to the public internet. Without API key protection, anyone who guesses your tunnel URL can use your llama.cpp inference.

**Always enable API key authentication** if your tunnel URL is discoverable.

---

## Backend Files (Android Termux)

| File | Purpose |
|------|---------|
| `cors_proxy.py` | CORS reverse proxy + `/v1/research` pipeline |
| `watchdog.sh` | Auto-restart: llama.cpp (context=2048), CORS proxy, serveo tunnel |
| `start_all.sh` | Launch all services |
| `start_cf_tunnel.sh` | Cloudflare tunnel launcher |

### CORS Proxy Endpoints

```
POST /v1/chat/completions  →  proxy to llama.cpp
POST /v1/models            →  proxy to llama.cpp
POST /v1/search             →  DuckDuckGo HTML search (returns snippets)
POST /v1/research           →  Hermes pipeline: search + fetch + extract + return context
GET  /test.html             →  Browser test UI (includes API key input)
```

### Required Headers

```
X-API-Key: gemma-local-2025   # Only if API_KEY is set in cors_proxy.py
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
# Install httpx (only dependency)
pip install httpx

# Run CORS proxy (port 18080)
python3 cors_proxy.py

# Run llama.cpp (context=2048)
# If your phone has 12GB+ RAM, add --flash-attn for better long-text performance
llama-server \
  -m /data/data/com.termux/files/home/models/gemma-2-2b-it-abliterated-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 -ngl 0 -c 2048

# Tunnel (serveo — fixed subdomain)
ssh -i ~/.ssh/id_ed25519 \
  -o StrictHostKeyChecking=no \
  -R moggy:80:localhost:18080 \
  serveo.net
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
- **Backend:** Python 3 (Termux default) + httpx on Android Termux
- **AI:** llama.cpp (local Gemma 2B) or any OpenAI-compatible API
- **Tunnel:** SSH reverse tunnel (serveo.net / localhost.run / Cloudflare)
- **Deploy:** Vercel (static SPA) or Cloudflare Pages

---

## Known Constraints

- **llama.cpp context:** 2048 tokens max (hardware limited on phone)
- **Page content:** Truncated to ~600 chars/page (sentence-aware cut, ~150 tokens × 3 pages)
- **Search:** DuckDuckGo HTML only (no JavaScript rendering) — if blocked, consider adding a proxy
- **Tunnel URL:** Changes on reconnect (serveo free plan = no fixed subdomain without paid account)
- **API key in URL:** The tunnel subdomain (e.g. `moggy.serveo.net`) should be kept private
