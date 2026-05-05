#!/usr/bin/env python3
"""
CORS-aware reverse proxy with Hermes/Perplexity-style Harness.
No extra dependencies — uses only stdlib + httpx.

Harness Architecture:
  Research Pipeline  →  Context Engineering  →  Structured Injection  →  Stream
  (search+fetch)         (filter+rerank)         (format for Gemma)       (1024 tok)

Key numbers (configurable):
  MAX_CONTEXT_CHARS  = 12000  (~8024 tokens, gemma-2b context limit)
  MAX_CHARS_PER_PAGE = 4000  (~8024 / 3 pages * 0.6 = ~1600 tokens per page)
  OUTPUT_MAX_TOKENS  = 1024
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
import asyncio
from urllib.parse import urlparse, quote
from concurrent.futures import ThreadPoolExecutor

# ─── Config ──────────────────────────────────────────────────────────────────
PORT = 18080
BACKEND = "http://localhost:8080"
PATH_PREFIX = "/1edf5d12423b60e8"
API_KEY = "gemma-local-2025"       # Set to None to disable auth

# ─── Context / Token Budget ─────────────────────────────────────────────────
MAX_CONTEXT_CHARS  = 12000   # ~8024 tokens max for gemma-2b
MAX_CHARS_PER_PAGE = 4000    # per-page extraction budget
OUTPUT_MAX_TOKENS  = 1024    # model output cap
PARALLEL_FETCHES   = 3       # concurrent page downloads

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

_fetch_sem = threading.Semaphore(PARALLEL_FETCHES)

def _fetch_with_sem(fn, *a, **kw):
    with _fetch_sem:
        return fn(*a, **kw)

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
    if not API_KEY:
        return True
    provided = handler.headers.get("X-API-Key", "")
    if provided == API_KEY:
        return True
    handler.send_response(401)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps({"error": "Invalid or missing X-API-Key"}).encode())
    return False

# ─── Keyword Extraction ──────────────────────────────────────────────────────
def _extract_keywords(text, top_n=10):
    """Pull out significant keywords from text (no external deps)."""
    # Remove common stopwords
    stopwords = {
        "the","a","an","and","or","but","in","on","at","to","for","of","with",
        "by","from","as","is","was","are","were","be","been","being","have",
        "has","had","do","does","did","will","would","could","should","may",
        "might","must","shall","can","this","that","these","those","i","you",
        "he","she","it","we","they","what","which","who","when","where","why",
        "how","all","each","every","both","few","more","most","other","some",
        "such","no","nor","not","only","own","same","so","than","too","very",
        "just","also","now","here","there","then","once","if","because","while",
        "of","at","by","for","with","about","against","between","into","through",
        "during","before","after","above","below","up","down","out","off","over",
        "under","again","further","then","once","and","but","or","nor","so",
        "yet","both","either","neither","each","few","more","most","other","some",
        "such","no","not","only","own","same","than","too","very","s","t","d",
        "ll","re","ve","m","o","y","ain","aren","couldn","didn","doesn","hadn",
        "hasn","haven","isn","ma","mightn","mustn","needn","shan","shouldn","wasn",
        "weren","won","wouldn","佢","你","我","佢","我哋","你哋","佢哋","係","喺",
        "嚟","去","到","嚇","噉","咁","點","點解","點样","幾","幾多","幾時","邊",
        "邊個","邊度","點解","因為","所以","但係","如果","或者","不過","然後",
        "然之後","就","就係","就喺","就嚟","就噉"
    }
    # Strip tags, lowercase
    clean = re.sub(r'<[^>]+>', '', text).lower()
    # Split on non-alphanumeric
    words = re.findall(r'[a-z0-9\u4e00-\u9fff]{3,}', clean)
    freq = {}
    for w in words:
        if w not in stopwords and not w.isdigit():
            freq[w] = freq.get(w, 0) + 1
    # Return top N by frequency
    return sorted(freq, key=freq.get, reverse=True)[:top_n]

def _score_relevance(text, keywords):
    """Score how many keyword hits a text has. Higher = more relevant."""
    if not keywords or not text:
        return 0
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)

# ─── HTML → Plain text extractor ─────────────────────────────────────────────
def extract_text_from_html(html_content):
    """Strip tags, scripts, styles; return clean readable text."""
    if not html_content:
        return ""

    # Remove CDATA, SVG, comments, script/style/noscript
    html_content = re.sub(r'<!\[CDATA\[.*?\]\]>', '', html_content, flags=re.DOTALL)
    html_content = re.sub(r'<svg[^>]*>.*?</svg>', '', html_content, flags=re.DOTALL|re.IGNORECASE)
    html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL|re.IGNORECASE)
    html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL|re.IGNORECASE)
    html_content = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html_content, flags=re.DOTALL|re.IGNORECASE)
    html_content = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)

    # Replace block elements with newlines
    for tag in ['br','p','div','tr','li','h1','h2','h3','h4','h5','h6','article','section','td','th']:
        html_content = re.sub(f'<{tag}[^>]*>', '\n', html_content, flags=re.IGNORECASE)
        html_content = re.sub(f'</{tag}>', '', html_content, flags=re.IGNORECASE)

    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', '', html_content)

    # Decode HTML entities (&amp; &quot; &#39; &nbsp; etc.)
    text = html.unescape(text)

    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]*\n+', '\n', text)
    lines = [l.strip() for l in text.split('\n')]
    return '\n'.join(l for l in lines if l)

def _truncate_sentence_aware(text, max_chars):
    """Truncate text near max_chars at a sentence boundary for readability."""
    if len(text) <= max_chars:
        return text
    search_start = int(max_chars * 0.75)
    search_window = text[search_start:max_chars]
    for punct in ('。', '. ', '! ', '? ', '.\n', '!\n', '?\n', '。\n', '" ', '"\n', '" ,'):
        idx = search_window.rfind(punct)
        if idx >= 0:
            cutoff = search_start + idx + len(punct)
            return text[:cutoff].strip() + "\n\n... [內容已截斷]"
    last_space = text[:max_chars].rfind(' ')
    if last_space > max_chars * 0.6:
        return text[:last_space].strip() + "\n\n... [內容已截斷]"
    return text[:max_chars].strip() + "\n\n... [內容已截斷]"


def fetch_url_content(url):
    """Fetch URL, extract readable text. Returns (url, text, error)."""
    def _do():
        try:
            headers = _make_headers({"Referer": "https://www.google.com/"})
            with httpx.Client(timeout=12, follow_redirects=True, headers=headers) as client:
                resp = client.get(url)
                ct = resp.headers.get("content-type", "")
                if "text/html" not in ct and "application/xhtml" not in ct:
                    return (url, "", "Not HTML")
                raw = resp.text
                text = extract_text_from_html(raw)
                # Apply per-page budget
                if len(text) > MAX_CHARS_PER_PAGE:
                    text = _truncate_sentence_aware(text, MAX_CHARS_PER_PAGE)
                return (url, text, None)
        except httpx.TimeoutException:
            return (url, "", "Timeout")
        except Exception as e:
            return (url, "", str(e))

    return _fetch_with_sem(_do)

# ─── Snippet reranking within page ───────────────────────────────────────────
def _extract_top_snippets(text, keywords, max_snippets=5, snippet_len=300):
    """
    Split page into paragraphs, score by keyword relevance,
    return top N most relevant snippets.
    """
    # Split into candidate paragraphs (non-empty lines)
    paras = [p.strip() for p in text.split('\n') if p.strip() and len(p.strip()) > 40]
    if not paras:
        return [text[:snippet_len]] if text else []

    # Score each paragraph
    scored = []
    for p in paras:
        score = _score_relevance(p, keywords)
        if score > 0:
            scored.append((score, len(p), p))
        elif len(snippets := [s for s in scored if s[2] == p]) == 0:
            scored.append((0, len(p), p))

    # Sort by score desc, then length desc
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    results = []
    total = 0
    for score, length, para in scored[:max_snippets]:
        snippet = para[:snippet_len]
        if total + len(snippet) > MAX_CHARS_PER_PAGE:
            remaining = MAX_CHARS_PER_PAGE - total
            if remaining > 80:
                results.append(snippet[:remaining])
                total += remaining
            break
        results.append(snippet)
        total += len(snippet)

    return results

# ─── Structured injection formatter ───────────────────────────────────────────
def _build_harness_context(query, results, keywords):
    """
    Build a structured, dense context string optimized for Gemma 2B.
    This is the core of the Harness — turning messy web data into "pure gold".
    """
    lines = []
    lines.append(f"=== 研究查詢 ===\n{query}\n")
    lines.append(f"=== 相關關鍵詞 ===\n{', '.join(keywords)}\n")
    lines.append(f"=== 來源整合 ===\n")

    for i, item in enumerate(results, 1):
        title = item.get('title', '')[:80]
        snippet = item.get('snippet', '')[:200]
        content = item.get('content', '')
        url = item.get('url', '')
        has_relevant = item.get('has_relevant_snippets', False)

        lines.append(f"\n─── 來源 {i}: {title} ───")
        lines.append(f"URL: {url}")

        if has_relevant and content:
            # Harness: extract only the most relevant snippets per source
            relevant = _extract_top_snippets(content, keywords, max_snippets=4, snippet_len=400)
            if relevant:
                lines.append(f"【關鍵段落】(關聯度: 高)")
                for j, snip in enumerate(relevant, 1):
                    lines.append(f"  [{j}] {snip}")
            else:
                lines.append(f"【摘要】{snippet}")
        else:
            lines.append(f"【摘要】{snippet}")

    total_chars = sum(len(l) for l in lines)

    # If over budget, truncate context while preserving header + sources
    if total_chars > MAX_CONTEXT_CHARS:
        budget = MAX_CONTEXT_CHARS
        # Reserve space for header (~500 chars)
        body_budget = budget - 500
        body = "".join(lines[2:])  # skip header lines
        if len(body) > body_budget:
            body = _truncate_sentence_aware(body, body_budget)
        lines = lines[:2] + [body]

    return "".join(lines)

# ─── System Prompt for Gemma 2B ──────────────────────────────────────────────
RESEARCHER_PROMPT = """你是一個專業的研究員助手。
你將收到多個互聯網來源的整合內容（【來源】標記）。
請嚴格按照以下步驟回答：

1. 【閱讀】仔細閱讀每個來源的內容，標記關鍵事實和數據
2. 【對比】如果不同來源有矛盾，標注出來
3. 【回答】用條列式（- 或 1. 2. 3.）回答用戶問題，禁止胡說八道
4. 【引用】在回答末尾標明：資料來源：[序号]

重要原則：
- 如果某個來源沒有提及某信息，明確說「未提及」，而不是猜測
- 不要摻雜個人意見或猜測，只能基於提供的來源
- 回答簡潔有力，每點不超過兩句話
- 如果信息不足，直接說「根據現有資料無法確定」

回答："""

# ─── Research pipeline ───────────────────────────────────────────────────────
def run_research(query):
    """
    Hermes/Perplexity-style Harness pipeline:
    1. Search DuckDuckGo → get results
    2. Extract global keywords from snippets
    3. Fetch top pages in parallel, score by relevance
    4. Build structured context (Harness)
    5. Return enriched context + metadata
    """
    # Step 1: Search
    results = search_ddg_html(query)
    if not results:
        return {
            "query": query, "results": [], "context": "No search results found.",
            "source_count": 0, "keywords": [], "context_chars": 0
        }

    # Step 2: Extract keywords from all snippets (global topic fingerprint)
    all_snippets = " ".join(r.get("snippet","") for r in results[:8])
    keywords = _extract_keywords(all_snippets, top_n=12)

    # Step 3: Fetch top pages in parallel
    top3 = results[:PARALLEL_FETCHES]
    futures = []
    for r in top3:
        futures.append(executor.submit(fetch_url_content, r["url"]))

    # Step 4: Collect + score by relevance
    enriched = []
    for i, f in enumerate(futures):
        url, content, err = f.result()
        r = top3[i]
        score = 0
        if err:
            enriched.append({**r, "content": "", "error": err,
                            "has_relevant_snippets": False, "relevance_score": 0})
        else:
            score = _score_relevance(content, keywords)
            enriched.append({**r, "content": content, "error": None,
                            "has_relevant_snippets": score > 0, "relevance_score": score})

    # Sort by relevance score desc
    enriched.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    # Step 5: Build structured Harness context
    context = _build_harness_context(query, enriched, keywords)

    # Step 6: Build display results (cleaned for frontend)
    display_results = []
    for item in enriched:
        display_results.append({
            "title": item.get("title",""),
            "url": item.get("url",""),
            "snippet": item.get("snippet",""),
            "relevance": item.get("relevance_score", 0)
        })

    return {
        "query": query,
        "keywords": keywords,
        "results": display_results,
        "context": context,
        "context_chars": len(context),
        "source_count": len(enriched),
        "system_prompt": RESEARCHER_PROMPT,
    }

# ─── Build stream-able response ───────────────────────────────────────────────
def build_stream_thought(query):
    """Generate a 'thinking' preface that streams before the real answer.

    This gives the user a Perplexity-style "analyzing..." moment
    while signaling that the backend has finished computation.
    """
    thoughts = [
        f"🔍 正在分析「{query}」的搜索結果...\n\n",
        f"📊 正在比對多個來源，提取關鍵段落...\n\n",
        f"⏳ 正在整合資料，準備為你解答...\n\n",
    ]
    return random.choice(thoughts)

executor = ThreadPoolExecutor(max_workers=PARALLEL_FETCHES + 2)

# ─── DuckDuckGo HTML Search ───────────────────────────────────────────────────
def search_ddg_html(query):
    """Search DuckDuckGo HTML, return list of {title, url, snippet}."""
    try:
        headers = _make_headers()
        url = f"https://html.duckduckgo.com/html/?q={quote(query)}&kl=wt-wt"
        with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            if resp.url.path != "/html/" and "html.duckduckgo" not in resp.url.host:
                return []
            html_content = resp.text

        results = []
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

# ─── CORS Proxy HTTP Handler ─────────────────────────────────────────────────
HTML_TEST = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>gemma-2b Harness API</title>
<style>
body{font-family:monospace;max-width:700px;margin:40px auto;padding:20px;background:#1a1a2e;color:#eee}
h1{color:#e94560}input,textarea{width:100%;background:#16213e;color:#0f0;border:1px solid #333;padding:8px;font-family:monospace;box-sizing:border-box;margin:5px 0}
textarea{height:80px;resize:none}button{background:#e94560;color:white;border:none;padding:12px 24px;cursor:pointer;font-size:16px;margin:10px 5px 10px 0}
pre{background:#0d0d1a;padding:12px;border-left:4px solid #e94560;overflow-x:auto;white-space:pre-wrap;word-break:break-all;font-size:13px}
.err{color:#ff6b6b}.ok{color:#0f0}.info{color:#ffd93d}
</style></head>
<body>
<h1>gemma-2b Harness API</h1>
<p>API: <input type="text" id="api" value="https://YOUR_TUNNEL_URL/1edf5d12423b60e8"></p>
<p>Research query: <input type="text" id="q" value="比特幣現在幾錢"></p>
<p>API Key: <input type="text" id="key" value="gemma-local-2025"></p>
<button onclick="doSearch()">Search</button>
<button onclick="doResearch()">Research (Harness)</button>
<button onclick="doModels()">Models</button>
<button onclick="doChat()">Chat</button>
<div id="out"></div>
<script>
function log(m,c){var d=document.createElement('pre');d.className=c||'info';d.textContent='['+new Date().toLocaleTimeString()+'] '+m;document.getElementById('out').prepend(d)}
function hdrs(){var k=document.getElementById('key').value;return k?{'X-API-Key':k}:{};}
async function doSearch(){var api=document.getElementById('api').value;var q=document.getElementById('q').value;document.getElementById('out').innerHTML='';log('SEARCH: '+q);try{var r=await fetch(api+'/v1/search',{method:'POST',headers:{'Content-Type':'application/json',...hdrs()},body:JSON.stringify({q})});var t=await r.text();log('Status: '+r.status,r.ok?'ok':'err');log('Results: '+t.substring(0,600),'ok');}catch(e){log(e.message,'err');}}
async function doResearch(){var api=document.getElementById('api').value;var q=document.getElementById('q').value;document.getElementById('out').innerHTML='';log('RESEARCH: '+q);try{var r=await fetch(api+'/v1/research',{method:'POST',headers:{'Content-Type':'application/json',...hdrs()},body:JSON.stringify({q})});var j=await r.json();log('Status: OK | Sources: '+j.source_count+' | Keywords: '+JSON.stringify(j.keywords||[]).substring(0,200),'ok');log('Context chars: '+j.context_chars+' | Context:\n'+j.context.substring(0,800),'ok');}catch(e){log(e.message,'err');}}
async function doModels(){var api=document.getElementById('api').value;document.getElementById('out').innerHTML='';try{var r=await fetch(api+'/v1/models',{headers:hdrs()});var j=await r.json();log('OK: '+JSON.stringify(j).substring(0,400),'ok');}catch(e){log(e.message,'err');}}
async function doChat(){var api=document.getElementById('api').value;var q=document.getElementById('q').value;document.getElementById('out').innerHTML='';try{var r=await fetch(api+'/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json',...hdrs()},body:JSON.stringify({model:'gemma-2-2b-it-abliterated-Q4_K_M.gguf',messages:[{role:'system',content:'你是一個專業的研究員助手。'}, {role:'user',content:q}],max_tokens:200})});var t=await r.text();log('Status: '+r.status,r.ok?'ok':'err');try{var j=JSON.parse(t);log('Reply: '+(j.choices&&j.choices[0]&&j.choices[0].message&&j.choices[0].message.content||'none').substring(0,400),'ok');}catch(e){log('Raw: '+t.substring(0,400),'err');}}catch(e){log(e.message,'err');}}
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
        try:
            cl = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(cl).decode()) if cl > 0 else {}
            query = body.get("q", body.get("query", ""))
            if not query:
                self._json(400, {"error": "q required"})
                return
            results = search_ddg_html(query)
            self._json(200, {"query": query, "results": results, "count": len(results)})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _handle_research(self):
        """
        Hermes/Perplexity-style research endpoint.
        Runs: search → fetch → keyword extraction → rerank → structured context.
        Returns: {query, keywords, results[], context, context_chars, system_prompt}
        """
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
        skip = {"host","connection","content-length","x-api-key"}
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
                        "transfer-encoding","connection","content-encoding",
                        "access-control-allow-origin","access-control-allow-methods",
                        "access-control-allow-headers","access-control-max-age"
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
    print(f"[Harness] Proxy :{PORT} → {BACKEND}")
    print(f"[Harness] Auth: {'ON (' + API_KEY + ')' if API_KEY else 'OFF'}")
    print(f"[Harness] Context budget: {MAX_CONTEXT_CHARS} chars (~8024 tokens)")
    print(f"[Harness] Per-page: {MAX_CHARS_PER_PAGE} chars")
    print(f"[Harness] Output cap: {OUTPUT_MAX_TOKENS} tokens")
    print(f"[Harness] Parallel fetches: {PARALLEL_FETCHES}")
    print("[Harness] Endpoints:")
    print("  POST /v1/search    — DuckDuckGo HTML search")
    print("  POST /v1/research  — Harness pipeline: search + fetch + rerank + format")
    print("  POST /v1/chat/completions — llama.cpp proxy")
    server = ThreadedHTTPServer(("", PORT), CORSProxyHandler)
    server.serve_forever()
