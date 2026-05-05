#!/usr/bin/env python3
"""
CORS-aware reverse proxy with Hermes-style research pipeline.
Search → Fetch pages → Extract content → Return enriched context.
No extra dependencies — uses only stdlib + httpx (already installed).

Security: Supports optional X-API-Key header validation.
"""
import http.server
import urllib.request
import urllib.error
import json
import sys
import socketserver
import re
import html
import random
import threading
from urllib.parse import urlparse, quote
from concurrent.futures import ThreadPoolExecutor

# ─── Config ──────────────────────────────────────────────────────────────────
PORT = 18080
BACKEND = "http://localhost:8080"
PATH_PREFIX = "/1edf5d12423b60e8"
MAX_WORKERS = 4
MAX_PARALLEL_FETCHES = 3
FETCH_TIMEOUT = 12
MAX_CHARS_PER_PAGE = 600   # ~150 tokens per page, 3 pages = ~450 tokens
API_KEY = "gemma-local-2025"  # Set to None to disable auth

# ─── User-Agent Pool ─────────────────────────────────────────────────────────
_UA_POOL = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]

def _ua():
    return random.choice(_UA_POOL)

# ─── Semaphore for concurrency control ───────────────────────────────────────
_fetch_semaphore = threading.Semaphore(MAX_PARALLEL_FETCHES)

def _fetch_with_semaphore(fn, *args, **kwargs):
    with _fetch_semaphore:
        return fn(*args, **kwargs)

# ─── HTTP Client (shared session per thread) ─────────────────────────────────
import httpx

def _make_headers(extra=None):
    h = {
        "User-Agent": _ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    }
    if extra:
        h.update(extra)
    return h

# ─── API Key Auth ─────────────────────────────────────────────────────────────
def _check_auth(handler):
    """Return True if request is authorized. Checks X-API-Key header."""
    if not API_KEY:
        return True
    provided = handler.headers.get("X-API-Key", "")
    if provided == API_KEY:
        return True
    handler.send_response(401)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("X-API-Key", "Required")
    handler.end_headers()
    handler.wfile.write(json.dumps({"error": "Invalid or missing X-API-Key"}).encode())
    return False

# ─── HTML → Plain text extractor ─────────────────────────────────────────────
def extract_text_from_html(html_content):
    """Strip tags, scripts, styles; return clean readable text.

    Improved robustness:
    - Removes CDATA, SVG, inline SVGs
    - Handles HTML entities properly (html.unescape handles &amp; &quot; etc.)
    - Sentence-aware truncation (cut at sentence boundary, not mid-word)
    """
    if not html_content:
        return ""

    # Remove CDATA sections
    html_content = re.sub(r'<!\[CDATA\[.*?\]\]>', '', html_content, flags=re.DOTALL)

    # Remove SVG graphics (often contain non-content noise)
    html_content = re.sub(r'<svg[^>]*>.*?</svg>', '', html_content, flags=re.DOTALL|re.IGNORECASE)

    # Remove script/style/noscript sections
    html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL|re.IGNORECASE)
    html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL|re.IGNORECASE)
    html_content = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html_content, flags=re.DOTALL|re.IGNORECASE)
    html_content = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)  # HTML comments

    # Replace block elements with newlines (preserves structure)
    for tag in ['br', 'p', 'div', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'article', 'section']:
        html_content = re.sub(f'<{tag}[^>]*>', '\n', html_content, flags=re.IGNORECASE)
        html_content = re.sub(f'</{tag}>', '', html_content, flags=re.IGNORECASE)

    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', '', html_content)

    # Decode HTML entities (&amp; &quot; &#39; &nbsp; etc.)
    text = html.unescape(text)

    # Clean whitespace: collapse spaces/tabs, remove blank lines
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]*\n+', '\n', text)  # collapse multiple blank lines
    lines = [l.strip() for l in text.split('\n')]
    text = '\n'.join(l for l in lines if l)

    # Sentence-aware truncation — cut at sentence boundary near MAX_CHARS_PER_PAGE
    if len(text) > MAX_CHARS_PER_PAGE:
        text = _truncate_sentence_aware(text, MAX_CHARS_PER_PAGE)

    return text


def _truncate_sentence_aware(text, max_chars):
    """Truncate text near max_chars at a sentence boundary for readability."""
    if len(text) <= max_chars:
        return text

    # Look for sentence-ending punctuation within last 15% of the allowed space
    search_start = int(max_chars * 0.75)
    search_window = text[search_start:max_chars]

    # Find last sentence-ending punctuation
    for punct in ('。', '. ', '! ', '? ', '.\n', '!\n', '?\n', '。\n'):
        idx = search_window.rfind(punct)
        if idx >= 0:
            cutoff = search_start + idx + len(punct)
            return text[:cutoff].strip() + "\n\n... [內容已截斷]"

    # Fallback: cut at last complete word
    last_space = text[:max_chars].rfind(' ')
    if last_space > max_chars * 0.6:
        return text[:last_space].strip() + "\n\n... [內容已截斷]"

    return text[:max_chars].strip() + "\n\n... [內容已截斷]"


def fetch_url_content(url):
    """Fetch a URL and extract readable text. Returns (url, text, error)."""
    def _do_fetch():
        try:
            headers = _make_headers({
                "Referer": "https://www.google.com/",
            })
            with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True, headers=headers) as client:
                resp = client.get(url)
                # Reject non-HTML responses
                ct = resp.headers.get("content-type", "")
                if "text/html" not in ct and "application/xhtml" not in ct:
                    return (url, "", "Not HTML content")
                content = resp.text
                text = extract_text_from_html(content)
                return (url, text, None)
        except httpx.TimeoutException:
            return (url, "", "Timeout")
        except Exception as e:
            return (url, "", str(e))

    return _fetch_with_semaphore(_do_fetch)


def search_ddg_html(query):
    """Search DuckDuckGo HTML, return list of {title, url, snippet}."""
    try:
        headers = _make_headers()
        url = f"https://html.duckduckgo.com/html/?q={quote(query)}&kl=wt-wt"
        with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            # Detect CAPTCHA or JS redirect
            if resp.url.path != "/html/" and "html.duckduckgo" not in resp.url.host:
                return []
            html_content = resp.text

        results = []
        # Pattern: <a class="result__a" ... href="URL">Title</a>
        # The \s before href= handles cases where rel="nofollow" precedes href
        for a_match in re.finditer(
            r'<a[^>]*class="result__a"[^>]*\shref="([^"]+)"[^>]*>([^<]+)</a>',
            html_content
        ):
            result_url = a_match.group(1)
            raw_title = a_match.group(2)
            title = html.unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()

            # Find snippet after this result
            snippet = ""
            pos = a_match.end()
            snippet_match = re.search(
                r'<p class="result__snippet"[^>]*>(.*?)</p>',
                html_content[pos:pos+500], re.DOTALL
            )
            if snippet_match:
                snippet = html.unescape(re.sub(r'<[^>]+>', '', snippet_match.group(1))).strip()

            if result_url and title:
                results.append({
                    "title": title,
                    "url": result_url,
                    "snippet": snippet[:300] if snippet else ""
                })
            if len(results) >= 8:
                break

        return results
    except Exception:
        return []


# ─── Research pipeline ───────────────────────────────────────────────────────
def run_research(query):
    """
    Hermes-style research pipeline:
    1. Search DuckDuckGo
    2. Fetch top pages in parallel (semaphore-limited)
    3. Extract readable content
    4. Return enriched context string
    """
    # Step 1: Search
    results = search_ddg_html(query)
    if not results:
        return {"query": query, "results": [], "context": "No search results found.", "source_count": 0}

    # Step 2: Fetch top pages in parallel (MAX_PARALLEL_FETCHES at a time)
    top3 = results[:MAX_PARALLEL_FETCHES]
    futures = []
    for r in top3:
        futures.append(executor.submit(fetch_url_content, r["url"]))

    # Step 3: Collect and enrich
    enriched = []
    for i, f in enumerate(futures):
        url, content, err = f.result()
        r = top3[i]
        if err:
            enriched.append({
                "title": r["title"],
                "url": r["url"],
                "snippet": r["snippet"],
                "content": f"[Failed: {err}]"
            })
        elif content.strip():
            enriched.append({
                "title": r["title"],
                "url": r["url"],
                "snippet": r["snippet"],
                "content": content
            })
        else:
            enriched.append({
                "title": r["title"],
                "url": r["url"],
                "snippet": r["snippet"],
                "content": "[Page content unavailable]"
            })

    # Step 4: Build context string for LLM
    ctx_parts = [f"Research query: {query}\n"]
    for item in enriched:
        ctx_parts.append(f"\n--- Source: {item['title']} ---")
        ctx_parts.append(f"URL: {item['url']}")
        if item['content'] and not item['content'].startswith('[Failed'):
            ctx_parts.append(f"\n{item['content']}")
        else:
            ctx_parts.append(f"\n{item['snippet']}")

    context = "\n".join(ctx_parts)
    return {
        "query": query,
        "results": enriched,
        "context": context,
        "source_count": len(enriched)
    }


executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


# ─── CORS Proxy HTTP Handler ─────────────────────────────────────────────────
HTML_TEST = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>gemma-2b API + Research</title>
<style>
body{font-family:monospace;max-width:700px;margin:40px auto;padding:20px;background:#1a1a2e;color:#eee}
h1{color:#e94560}input,textarea{width:100%;background:#16213e;color:#0f0;border:1px solid #333;padding:8px;font-family:monospace;box-sizing:border-box;margin:5px 0}
textarea{height:80px;resize:none}button{background:#e94560;color:white;border:none;padding:12px 24px;cursor:pointer;font-size:16px;margin:10px 5px 10px 0}
pre{background:#0d0d1a;padding:12px;border-left:4px solid #e94560;overflow-x:auto;white-space:pre-wrap;word-break:break-all;font-size:13px}
.err{color:#ff6b6b}.ok{color:#0f0}.info{color:#ffd93d}
</style></head>
<body>
<h1>gemma-2b + Research API</h1>
<p>API: <input type="text" id="api" value="https://YOUR_TUNNEL_URL/1edf5d12423b60e8"></p>
<p>Research query: <input type="text" id="q" value="澳門天氣"></p>
<p>API Key (optional): <input type="text" id="key" value="gemma-local-2025" placeholder="X-API-Key header"></p>
<button onclick="doSearch()">Search</button>
<button onclick="doResearch()">Research (Hermes)</button>
<button onclick="doModels()">Models</button>
<button onclick="doChat()">Chat</button>
<div id="out"></div>
<script>
function log(m,c){var d=document.createElement('pre');d.className=c||'info';d.textContent='['+new Date().toLocaleTimeString()+'] '+m;document.getElementById('out').prepend(d)}
function hdrs(){return document.getElementById('key').value ? {'X-API-Key': document.getElementById('key').value} : {}}
async function doSearch(){var api=document.getElementById('api').value;var q=document.getElementById('q').value;document.getElementById('out').innerHTML='';log('SEARCH: '+q);try{var r=await fetch(api+'/v1/search',{method:'POST',headers:{'Content-Type':'application/json',...hdrs()},body:JSON.stringify({q})});var t=await r.text();log('Status: '+r.status,r.ok?'ok':'err');log('Results: '+t.substring(0,600),'ok');}catch(e){log(e.message,'err');}}
async function doResearch(){var api=document.getElementById('api').value;var q=document.getElementById('q').value;document.getElementById('out').innerHTML='';log('RESEARCH: '+q);try{var r=await fetch(api+'/v1/research',{method:'POST',headers:{'Content-Type':'application/json',...hdrs()},body:JSON.stringify({q})});var t=await r.text();var j=JSON.parse(t);log('Status: '+r.status,r.ok?'ok':'err');log('Sources: '+j.source_count+' | Context: '+j.context.length+' chars','ok');log(j.context.substring(0,400),'ok');}catch(e){log(e.message,'err');}}
async function doModels(){var api=document.getElementById('api').value;document.getElementById('out').innerHTML='';try{var r=await fetch(api+'/v1/models',{headers:hdrs()});var j=await r.json();log('OK: '+JSON.stringify(j).substring(0,400),'ok');}catch(e){log(e.message,'err');}}
async function doChat(){var api=document.getElementById('api').value;var q=document.getElementById('q').value;document.getElementById('out').innerHTML='';try{var r=await fetch(api+'/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json',...hdrs()},body:JSON.stringify({model:'gemma-2-2b-it-abliterated-Q4_K_M.gguf',messages:[{role:'user',content:q}],max_tokens:50})});var t=await r.text();log('Status: '+r.status,r.ok?'ok':'err');try{var j=JSON.parse(t);log('Reply: '+(j.choices&&j.choices[0]&&j.choices[0].message&&j.choices[0].message.content||'none').substring(0,300),'ok');}catch(e){log('Raw: '+t.substring(0,300),'err');}}catch(e){log(e.message,'err');}}
</script></body></html>"""


class CORSProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[CORS] {fmt % args}\n")

    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With, X-API-Key")

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors()
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/test", "/test.html"):
            body = HTML_TEST.encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._set_cors()
            self.end_headers()
            self.wfile.write(body)
            return
        self._proxy("GET")

    def do_POST(self):
        if not _check_auth(self):
            return
        parsed = urlparse(self.path)
        if parsed.path == "/v1/search":
            self._handle_search()
        elif parsed.path == "/v1/research":
            self._handle_research()
        else:
            self._proxy("POST")

    def _handle_search(self):
        """DDG HTML search — returns results[]."""
        try:
            cl = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(cl).decode()) if cl > 0 else {}
            query = body.get("q", body.get("query", ""))
            if not query:
                self._json(400, {"error": "q required"})
                return
            results = search_ddg_html(query)
            self._json(200, {"query": query, "results": results, "count": len(results)})
        except json.JSONDecodeError:
            self._json(400, {"error": "Invalid JSON"})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _handle_research(self):
        """Hermes-style pipeline: search → fetch → extract → return context."""
        try:
            cl = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(cl).decode()) if cl > 0 else {}
            query = body.get("q", body.get("query", ""))
            if not query:
                self._json(400, {"error": "q required"})
                return
            self.log_message("Research: %s", query)
            result = run_research(query)
            self._json(200, result)
        except json.JSONDecodeError:
            self._json(400, {"error": "Invalid JSON"})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._set_cors()
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self, method):
        parsed = urlparse(self.path)

        # Strip PATH_PREFIX if present
        path = parsed.path
        if path.startswith(PATH_PREFIX):
            path = path[len(PATH_PREFIX):]
        if not path:
            path = "/"

        backend_url = BACKEND + path
        if parsed.query:
            backend_url += "?" + parsed.query

        cl = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(cl) if cl > 0 else None

        headers = {}
        skip = {"host", "connection", "content-length", "x-api-key"}
        for k, v in self.headers.items():
            if k.lower() not in skip:
                headers[k] = v

        try:
            req = urllib.request.Request(backend_url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=90) as resp:
                content = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in (
                        "transfer-encoding", "connection", "content-encoding",
                        "access-control-allow-origin", "access-control-allow-methods",
                        "access-control-allow-headers", "access-control-max-age"
                    ):
                        continue
                    self.send_header(k, v)
                self._set_cors()
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                if content:
                    self.wfile.write(content)
        except urllib.error.HTTPError as e:
            content = e.read()
            self.send_response(e.code)
            self._set_cors()
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if content:
                self.wfile.write(content)
        except Exception as e:
            sys.stderr.write(f"[CORS] Error: {e}\n")
            self.send_response(502)
            self._set_cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    print(f"[CORS+Research] Proxy :{PORT} → {BACKEND}")
    print(f"[CORS+Research] Auth: {'ON (X-API-Key: ' + API_KEY + ')' if API_KEY else 'OFF (no auth)'}")
    print("[CORS+Research] Endpoints:")
    print("  POST /v1/search     — DuckDuckGo HTML search")
    print("  POST /v1/research  — Hermes: search + fetch + extract")
    print("  POST /v1/chat/completions — llama.cpp proxy")
    print(f"[CORS+Research] Per-page limit: {MAX_CHARS_PER_PAGE} chars")
    server = ThreadedHTTPServer(("", PORT), CORSProxyHandler)
    server.serve_forever()
