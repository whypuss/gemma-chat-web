# gemma-chat-web

Vue 3 SPA — Chat with local Gemma GGUF model via PicoClaw gateway on Android Termux.

## Architecture

```
Browser (Vue UI)
    ↓
Vercel (frontend hosting)
    ↓
Cloudflare Tunnel (trycloudflare.com → phone)
    ↓
CORS Proxy (:18080, cors_proxy.py)
    ↓
llama.cpp server (:8080)
    ↓
Gemma 2B GGUF model (running on Sony SO-51B Android Termux)
```

**No cloud AI needed** — fully offline local inference.

## Quick Start

### 1. Setup Phone (Android Termux)

```bash
# Install dependencies
pkg update && pkg install python  git  openssh  nodejs  npm

# Clone pico
cd ~
git clone https://github.com/sipeed/picoclaw

# Install llama.cpp (Q4_K_M GGUF model)
pip install llama-cpp-python

# Download Gemma 2B IT Abliterated
# From: https://huggingface.co/bartowski/gemma-2-2b-it-abliterated-GGUF
# Put file as: ~/models/gemma-2-2b-it-abliterated-Q4_K_M.gguf

# Start llama.cpp server
python3 -m llama_cpp.server --model ~/models/gemma-2-2b-it-abliterated-Q4_K_M.gguf --host 0.0.0.0 --port 8080

# Start CORS proxy (new terminal)
python3 cors_proxy.py

# Start Cloudflare Tunnel
/data/data/com.termux/files/usr/bin/cloudflared tunnel --url http://localhost:18080
# Note the trycloudflare.com URL output
```

### 2. Upload CORS proxy

```bash
# From THIS repo - cors_proxy.py
scp cors_proxy.py u0_a409@YOUR_PHONE_IP:/data/data/com.termux/files/home/
```

### 3. Deploy Web UI

```bash
npm install
npm run build
# Deploy dist/ to Vercel / Netlify / Cloudflare Pages
```

Or use Vercel REST API (from repo root):

```bash
curl -X POST https://api.vercel.com/v13/deployments \
  -H "Authorization: Bearer YOUR_VERCEL_TOKEN" \
  -H "Content-Type: application/json" \
  -d @- << 'EOF'
{
  "name": "gemma-chat",
  "files": [{"file": "dist/index.html", "data": "..."}],
  "projectSettings": {"outputDirectory": "dist", "buildCommand": null}
}
EOF
```

### 4. Configure Settings

Open the deployed app → Settings → enter:

- **API URL**: your trycloudflare.com tunnel URL
- **Model**: `gemma-2-2b-it-abliterated-Q4_K_M.gguf`
- **Max Tokens**: 512

## Features

- 🔍 **Free web search** via DuckDuckGo HTML scraping (no API key)
- 🤖 **Local GGUF inference** — Gemma 2B on your phone
- 📱 **Mobile-first** dark theme UI
- ⚡ **Streaming responses** — tokens appear in real-time
- 🔄 **Auto-search** — detects questions and searches automatically
- 📝 **Markdown rendering** — bold, italic, code blocks
- 💬 **Chat history** — multiple conversations

## API Endpoints (via CORS proxy)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | OpenAI-compatible chat completions → llama.cpp |
| `/v1/search` | POST | Free DuckDuckGo search → `{q: "query"}` → `{results: [...]}` |

## PicoClaw Gateway

This app is designed to work WITH PicoClaw running on the same phone:

- **PicoClaw** (port 18790): Agent gateway for Telegram/Discord
- **llama.cpp** (port 8080): Local LLM inference server
- **CORS proxy** (port 18080): Bridges web UI to local servers, provides `/v1/search`

### PicoClaw Config (`~/.picoclaw/config.json`)

```json
{
  "model_list": [
    {
      "model_name": "local-gemma",
      "provider": "vllm",
      "model": "gemma-2-2b-it-abliterated-Q4_K_M.gguf",
      "api_base": "http://localhost:8080/v1",
      "enabled": true
    }
  ],
  "agents": {
    "defaults": {
      "model_name": "local-gemma"
    }
  }
}
```

## Hardware

- **Phone**: Sony SO-51B (Xperia 1 V) — Android, Termux
- **Model**: Gemma 2B IT Abliterated Q4_K_M GGUF (~1.6GB)
- **RAM**: 8GB (running Gemma + llama.cpp + proxy + tunnel)
- **Tunnel**: Cloudflare Tunnel (trycloudflare.com free tier)

## Tech Stack

- **Frontend**: Vue 3, Vite, vanilla CSS
- **Backend**: llama.cpp Python server, FastAPI-style CORS proxy
- **Hosting**: Vercel (frontend), Android Termux (inference)
- **Tunnel**: Cloudflare Tunnel (cloudflared)

## License

MIT
