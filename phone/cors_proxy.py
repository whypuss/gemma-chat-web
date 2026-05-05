#!/usr/bin/env python3
"""
CORS-aware reverse proxy with Hermes-style research pipeline.
Search → Fetch pages → Extract content → Return enriched context.
No extra dependencies — uses only stdlib + httpx (already installed).
"""
import http.server
import urllib.request
import urllib.error
import json
import sys
import socketserver
import re
import html
import asyncio
import threading
from urllib.parse import urlparse, quote
from concurrent.futures import ThreadPoolExecutor

PORT = 18080
BACKEND = "http://localhost:8080"
PATH_PREFIX = "/1edf5d12423b60e8"
MAX_WORKERS = 4
FETCH_TIMEOUT = 12  # seconds per page fetch

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# ─── HTML → Plain text extractor (no bs4 needed) ────────────────────────────
def extract_text_from_html(html_content, url=""):
    """Strip tags, scripts, styles; return clean readable text."""
    if not html_content:
        return ""

    # Remove script/style sections
    html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL|re.IGNORECASE)
    html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL|re.IGNORECASE)
    html_content = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html_content, flags=re.DOTALL|re.IGNORECASE)

    # Replace block elements with newlines
    for tag in ['br', 'p', 'div', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
        html_content = re.sub(f'<{tag}[^>]*>', '\n', html_content, flags=re.IGNORECASE)
        html_content = re.sub(f'</{tag}>', '', html_content, flags=re.IGNORECASE)

    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', '', html_content)

    # Decode HTML entities
    text = html.unescape(text)

    # Clean whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    lines = [l.strip() for l in text.split('\n')]
    text = '\n'.join(l for l in lines if l)

    # Truncate to avoid huge context (keep first 800 chars per page, ~200 tokens)
    if len(text) > 800:
        text = text[:800] + "\n... [content truncated]"
    return text


def fetch_url_content(url, timeout=FETCH_TIMEOUT):
    """Fetch a URL and extract readable text. Returns (url, text, error)."""
    try:
        import httpx
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
        }
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            content = resp.text
            text = extract_text_from_html(content, url)
            return (url, text, None)
    except Exception as e:
        return (url, "", str(e))


def search_ddg_html(query):
    """Search DuckDuckGo HTML, return list of {title, url, snippet}."""
    try:
        import httpx
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
            'Accept': 'text/html',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        url = f"https://html.duckduckgo.com/html/?q={quote(query)}&kl=wt-wt"
        with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            html_content = resp.text

        results = []
        # Parse result items: <a class="result__a" href="URL">Title</a>
        # and <p class="result__snippet">Snippet</p>
        for a_match in re.finditer(r'<a[^>]*class="result__a"[^>]*\shref="([^"]+)"[^>]*>([^<]+)</a>', html_content):
            result_url = a_match.group(1)
            title = html.unescape(re.sub(r'<[^>]+>', '', a_match.group(2))).strip()

            # Find the snippet after this result
            snippet = ""
            pos = a_match.end()
            snippet_match = re.search(r'<p class="result__snippet"[^>]*>(.*?)</p>', html_content[pos:pos+500], re.DOTALL)
            if snippet_match:
                snippet = html.unescape(re.sub(r'<[^>]+>', '', snippet_match.group(1))).strip()

            if result_url and title:
                results.append({"title": title, "url": result_url, "snippet": snippet[:300]})
            if len(results) >= 8:
                break

        return results
    except Exception as e:
        return []


# ─── Research pipeline ─────────────────────────────────────────────────────
def run_research(query):
    """
    Hermes-style research pipeline:
    1. Search DuckDuckGo
    2. Fetch top pages in parallel
    3. Extract readable content
    4. Return enriched context
    """
    # Step 1: Search
    results = search_ddg_html(query)
    if not results:
        return {"query": query, "results": [], "context": "No search results found."}

    # Step 2: Fetch top pages in parallel
    top3 = results[:3]
    futures = []
    for r in top3:
        futures.append(executor.submit(fetch_url_content, r["url"]))

    # Collect results
    enriched = []
    for i, f in enumerate(futures):
        url, content, err = f.result()
        r = top3[i]
        if err:
            enriched.append({
                "title": r["title"],
                "url": r["url"],
                "snippet": r["snippet"],
                "content": f"[Failed to fetch: {err}]"
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

    # Step 3: Build context string for LLM
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


# ─── CORS Proxy ──────────────────────────────────────────────────────────────
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
<p>API: <input type="text" id="api" value="https://22fa1367b38265.lhr.life/1edf5d12423b60e8"></p>
<p>Research query: <input type="text" id="q" value="澳門天氣"></p>
<button onclick="doSearch()">Search</button>
<button onclick="doResearch()">Research (Hermes)</button>
<button onclick="doModels()">Models</button>
<button onclick="doChat()">Chat</button>
<div id="out"></div>
<script>
function log(m,c){var d=document.createElement('pre');d.className=c||'info';d.textContent='['+new Date().toLocaleTimeString()+'] '+m;document.getElementById('out').prepend(d)}
async function doSearch(){var api=document.getElementById('api').value;var q=document.getElementById('q').value;document.getElementById('out').innerHTML='';log('SEARCH: '+q);try{var r=await fetch(api+'/v1/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q})});var t=await r.text();log('Status: '+r.status,r.ok?'ok':'err');log('Results: '+t.substring(0,600),'ok');}catch(e){log(e.message,'err');}}
async function doResearch(){var api=document.getElementById('api').value;var q=document.getElementById('q').value;document.getElementById('out').innerHTML='';log('RESEARCH: '+q);try{var r=await fetch(api+'/v1/research',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q})});var t=await r.text();var j=JSON.parse(t);log('Status: '+r.status,r.ok?'ok':'err');log('Sources: '+j.source_count+' | Context chars: '+j.context.length,'ok');log('First 400 chars of context:','info');log(j.context.substring(0,400),'ok');}catch(e){log(e.message,'err');}}
async function doModels(){var api=document.getElementById('api').value;document.getElementById('out').innerHTML='';try{var r=await fetch(api+'/v1/models');var j=await r.json();log('OK: '+JSON.stringify(j).substring(0,400),'ok');}catch(e){log(e.message,'err');}}
async function doChat(){var api=document.getElementById('api').value;var q=document.getElementById('q').value;document.getElementById('out').innerHTML='';try{var r=await fetch(api+'/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:'gemma-2-2b-it-abliterated-Q4_K_M.gguf',messages:[{role:'user',content:q}],max_tokens:50})});var t=await r.text();log('Status: '+r.status,r.ok?'ok':'err');try{var j=JSON.parse(t);log('Reply: '+(j.choices&&j.choices[0]&&j.choices[0].message&&j.choices[0].message.content||'none').substring(0,300),'ok');}catch(e){log('Raw: '+t.substring(0,300),'err');}}catch(e){log(e.message,'err');}}
</script></body></html>"""


class CORSProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        sys.stderr.write("[CORS] " + (fmt % args) + "\n")

    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

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
        parsed = urlparse(self.path)
        # ── /v1/search ──────────────────────────────────────────
        if parsed.path == "/v1/search":
            self._handle_search()
            return
        # ── /v1/research ────────────────────────────────────────
        if parsed.path == "/v1/research":
            self._handle_research()
            return
        # ── Proxy everything else to llama.cpp ──────────────────
        self._proxy("POST")

    def _handle_search(self):
        """Enhanced search: DDG HTML → return results with context."""
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
        """
        Hermes-style research pipeline.
        POST {q: "query"} → returns {query, results[], context, source_count}
        """
        try:
            cl = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(cl).decode()) if cl > 0 else {}
            query = body.get("q", body.get("query", ""))
            if not query:
                self._json(400, {"error": "q required"})
                return

            self.log_message("Research: %s", query)

            # Run research in thread pool (may take 10-30s)
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

        if parsed.path.startswith(PATH_PREFIX):
            new_path = parsed.path[len(PATH_PREFIX):]
        else:
            new_path = parsed.path
        if not new_path:
            new_path = "/"

        backend_url = BACKEND + new_path
        if parsed.query:
            backend_url += "?" + parsed.query

        cl = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(cl) if cl > 0 else None

        headers = {}
        skip = {"host", "connection", "content-length"}
        for k, v in self.headers.items():
            if k.lower() not in skip:
                headers[k] = v

        try:
            req = urllib.request.Request(backend_url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=90) as resp:
                content = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in ("transfer-encoding", "connection", "content-encoding",
                                      "access-control-allow-origin", "access-control-allow-methods",
                                      "access-control-allow-headers", "access-control-max-age"):
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
            sys.stderr.write("[CORS] Error: " + str(e) + "\n")
            self.send_response(502)
            self._set_cors()
            self.end_headers()
            err = json.dumps({"error": str(e)}).encode()
            self.wfile.write(err)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    print("[CORS+Research] Proxy: " + str(PORT) + " -> " + BACKEND)
    print("[CORS+Research] Endpoints:")
    print("  POST /v1/search    — DuckDuckGo search (enhanced)")
    print("  POST /v1/research — Hermes-style: search + fetch + extract")
    print("  POST /v1/chat/completions — llama.cpp proxy")
    server = ThreadedHTTPServer(("", PORT), CORSProxyHandler)
    server.serve_forever()
