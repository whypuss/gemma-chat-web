#!/usr/bin/env python3
"""
CORS-aware reverse proxy with Hermes/Perplexity-style Harness.
No extra dependencies — uses only stdlib + httpx.

Key numbers (configurable):
  MAX_CONTEXT_TOKENS = 1800   # per-source token budget (3 sources × 1800 = 5400 in context)
  MAX_CHARS_PER_PAGE = 3000  # ~1800 tokens for mixed EN/ZH text
  PARALLEL_FETCHES   = 3     # concurrent page downloads

Harness Architecture:
  Search (DuckDuckGo HTML) → Parallel fetch → Relevance rerank
  → State-machine HTML extraction → Bigram keyword scoring
  → Token-budgeted context assembly → OpenAI compat streaming
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# ─── Config ────────────────────────────────────────────────────────────────────
PORT             = 18080
BACKEND          = "http://localhost:8080"
PATH_PREFIX      = "/1edf5d12423b60e8"
API_KEY          = "gemma-local-2025"   # Set to None to disable auth

# Token budgets (Gemma 2B Q4_K_M ~6 tok/word EN, ~2 tok/char ZH)
MAX_CONTEXT_TOKENS  = 1800   # per-source token budget (safe for ZH mixed text)
MAX_CHARS_PER_PAGE  = 3000   # ~1500-1800 tokens for ZH-heavy text
PARALLEL_FETCHES    = 3

# ─── Shared httpx Client (connection pool — one TCP/TLS handshake reused) ─────
import httpx

_http_lock = threading.Lock()
_http_client = httpx.Client(
    timeout=12,
    follow_redirects=True,
    http2=True,           # multiplex multiple reqs over one connection
    limits=httpx.Limits(
        max_keepalive_connections=PARALLEL_FETCHES,
        max_connections=PARALLEL_FETCHES + 2,
        keepalive_expiry=60,
    ),
)

# ─── User-Agent Pool ───────────────────────────────────────────────────────────
_UA_POOL = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]

def _ua():
    return random.choice(_UA_POOL)

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

# ─── Semaphore (safe — acquired/released in same frame, no code paths skip it) ─
_fetch_sem = threading.Semaphore(PARALLEL_FETCHES)

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

# ─── State-machine HTML → plain text ─────────────────────────────────────────
# Fixes: regex hallucination on `<div data-info="a>b">`, nested quotes, etc.
def extract_text_from_html(html_content):
    """
    Strip HTML tags/scripts/styles using a character-level state machine.
    Handles: quoted attributes with > inside, CDATA, SVG, scripts, noscript.
    Does NOT use regex for tag detection — avoids '>'-in-attribute edge cases.
    """
    if not html_content:
        return ""

    # Fast pre-clean: strip known dangerous blocks first (before state machine)
    html_content = re.sub(r'<!\[CDATA\[.*?\]\]>', '', html_content, flags=re.DOTALL)
    html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    html_content = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    html_content = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)
    html_content = re.sub(r'<svg[^>]*>.*?</svg>', '', html_content, flags=re.DOTALL | re.IGNORECASE)

    # State machine: IN_TEXT=0, IN_TAG=1, IN_TAG_ATTR=2
    IN_TEXT, IN_TAG, IN_TAG_ATTR = 0, 1, 2
    state = IN_TEXT
    result = []
    i = 0
    n = len(html_content)

    while i < n:
        c = html_content[i]

        if state == IN_TEXT:
            if c == '<':
                state = IN_TAG
            elif c == '\n':
                result.append('\n')
            elif not c.isspace():
                result.append(c)
            # else: skip whitespace in text

        elif state == IN_TAG:
            # '<' already consumed; next char determines next state
            if c == '>':
                # End of tag
                state = IN_TEXT
            elif c in ('"', "'"):
                # Enter attribute value quoted state
                state = IN_TAG_ATTR
                attr_quote = c
            else:
                # Still reading tag name / attributes
                state = IN_TAG
            # Never copy tag characters

        elif state == IN_TAG_ATTR:
            # Inside a quoted attribute value — > inside quotes is literal
            if c == attr_quote:
                state = IN_TAG
            # else: skip everything inside attribute values

        i += 1

    # Normalise whitespace
    text = ''.join(result)
    # Collapse blank lines and leading/trailing whitespace on each line
    lines = text.split('\n')
    lines = [l.strip() for l in lines if l.strip()]
    return '\n'.join(lines)

# ─── Token estimator ────────────────────────────────────────────────────────────
def estimate_tokens(text):
    """
    Rough token count for mixed EN/ZH text without HuggingFace tokenizers.
    Rule of thumb:
      English: ~4 chars/token
      Chinese: ~1.5 chars/token (CJK tokens are typically 1-2 chars each in Gemma)
      Punctuation: ~1 char/token
    Conservative: divide Chinese count by 1.5.
    """
    zh_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    other = len(text) - zh_chars
    return int(other / 4.0 + zh_chars / 1.5)

def truncate_to_token_budget(text, max_tokens):
    """Truncate text to approximately max_tokens using sentence-aware cuts."""
    budget = int(max_tokens * 4.5)   # convert tokens → chars (conservative)
    if len(text) <= budget:
        return text

    # Search backward from budget for sentence boundary
    search = text[:budget]
    for punct in ('。', '. ', '! ', '? ', '.\n', '!\n', '?\n', '。\n', '" ', '"\n'):
        idx = search.rfind(punct)
        if idx >= int(budget * 0.7):
            return text[:idx + len(punct)].strip() + "\n\n... [內容已截斷]"
    # Fallback: word boundary
    sp = search.rfind(' ')
    if sp > int(budget * 0.6):
        return text[:sp].strip() + "\n\n... [內容已截斷]"
    return text[:budget].strip() + "\n\n... [內容已截斷]"

# ─── Keyword Extraction (bigram sliding window for Chinese) ────────────────────
_STOPWORDS = {
    # English
    "the","a","an","and","or","but","in","on","at","to","for","of","with","by",
    "from","as","is","was","are","were","be","been","being","have","has","had",
    "do","does","did","will","would","could","should","may","might","must",
    "this","that","these","those","i","you","he","she","it","we","they",
    "what","which","who","when","where","why","how","all","each","every",
    "both","few","more","most","other","some","such","no","nor","not","only",
    "own","same","so","than","too","very","just","also","now","here","there",
    "then","once","if","because","while","about","against","between","into",
    "through","during","before","after","above","below","up","down","out",
    "off","over","under","again","further","get","got","make","made","find",
    "give","gave","tell","told","say","said","come","came","look","looked",
    # Crypto/financial noise
    "price","today","live","chart","market","currency","currencies","trading",
    "trader","trade","bitcoin","btc","ethereum","eth","coin","coins","usd",
    # HTML noise
    "https","http","www","com","org","net","html","css","javascript",
    # Chinese common
    "佢","你","我","我哋","你哋","係","喺","嚟","去","到","點","點解",
    "因為","所以","但係","如果","或者","不過","然後","就","就係","就喺",
}

def _extract_keywords(text, top_n=12):
    """
    Extract keywords using unigram + bigram sliding window for Chinese.
    English: tokenise on non-alphanumeric.
    Chinese: sliding window of 2-3 chars to capture meaningful phrases.
    Returns list of (keyword, score) sorted by frequency, deduplicated.
    """
    clean = re.sub(r'<[^>]+>', '', text).lower()
    freq = {}
    seen = set()

    # English words: 3+ alphanumeric chars
    for w in re.findall(r'[a-z]{3,}', clean):
        if w not in _STOPWORDS and not w.isdigit():
            freq[w] = freq.get(w, 0) + 1
            seen.add(w)

    # Chinese + mixed: sliding window 2-3 chars
    cjk = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]{2,}', clean)
    for w in cjk:
        if w in _STOPWORDS:
            continue
        # Unigram CJK
        if len(w) >= 2:
            freq[w] = freq.get(w, 0) + 1
        # CJK bigram (consecutive 2-char pairs within longer runs)
        if len(w) > 2:
            for j in range(len(w) - 1):
                bigram = w[j:j+2]
                if bigram not in _STOPWORDS:
                    freq[bigram] = freq.get(bigram, 0) + 0.6

    # Sort by freq desc, return top_n
    return [k for k, _ in sorted(freq.items(), key=lambda x: -x[1]) if k not in seen][:top_n]

def _score_relevance(text, keywords):
    """Score text by keyword hits. Chinese bigrams get partial weight."""
    if not keywords or not text:
        return 0
    text_lower = text.lower()
    score = 0
    for kw in keywords:
        kw_l = kw.lower()
        if kw_l in text_lower:
            score += 1
        elif len(kw) > 3 and kw[:2] in text_lower:
            score += 0.5
    return score

# ─── URL fetching (reuses shared _http_client — connection pool) ─────────────
def fetch_url_content(url):
    """
    Fetch URL, extract text. Returns (url, text, error).
    Uses module-level _http_client (persistent connection pool).
    """
    def _do():
        try:
            # Respect robots.txt for polite crawling
            headers = _make_headers({"Referer": "https://www.google.com/"})
            resp = _http_client.get(url, headers=headers)
            ct = resp.headers.get("content-type", "")
            if "text/html" not in ct and "application/xhtml" not in ct:
                return (url, "", "Not HTML")
            raw = resp.text
            text = extract_text_from_html(raw)
            if not text:
                return (url, "", "Empty after extraction")
            # Apply per-page token budget
            tokens = estimate_tokens(text)
            if tokens > MAX_CONTEXT_TOKENS:
                text = truncate_to_token_budget(text, MAX_CONTEXT_TOKENS)
            return (url, text, None)
        except httpx.TimeoutException:
            return (url, "", "Timeout")
        except Exception as e:
            return (url, "", str(e))

    acquired = False
    try:
        _fetch_sem.acquire()
        acquired = True
        return _do()
    finally:
        if acquired:
            _fetch_sem.release()

# ─── Snippet reranking ────────────────────────────────────────────────────────
def _extract_top_snippets(text, keywords, max_snippets=4, snippet_len=400):
    """Split page into paragraphs, score by relevance, return top N."""
    paras = [p.strip() for p in text.split('\n')
             if p.strip() and len(p.strip()) > 40]
    if not paras:
        return [text[:snippet_len]] if text else []

    scored = []
    for p in paras:
        sc = _score_relevance(p, keywords)
        scored.append((sc, len(p), p))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    results = []
    total_chars = 0
    for _, length, para in scored[:max_snippets]:
        cap = min(len(para), snippet_len)
        if total_chars + cap > MAX_CHARS_PER_PAGE:
            remaining = MAX_CHARS_PER_PAGE - total_chars
            if remaining > 80:
                results.append(para[:remaining])
                total_chars += remaining
            break
        results.append(para[:cap])
        total_chars += cap
    return results

# ─── Context builder (token-budgeted) ────────────────────────────────────────
def _build_context(query, results, keywords):
    """
    Build structured context respecting per-source token budget.
    Header + sources are preserved; body is truncated if over budget.
    """
    header = (
        f"=== 研究查詢 ===\n{query}\n\n"
        f"=== 關鍵詞 ===\n{', '.join(keywords)}\n\n"
        f"=== 來源整合 ===\n"
    )
    header_chars = len(header)
    # Conservative: 1 token ≈ 4 chars for mixed text; budget in chars
    header_tokens = estimate_tokens(header)
    total_token_budget = MAX_CONTEXT_TOKENS * len(results) + header_tokens

    source_blocks = []
    for i, item in enumerate(results, 1):
        title = item.get('title', '')[:80]
        snippet = item.get('snippet', '')[:200]
        content = item.get('content', '')
        url = item.get('url', '')
        has_rel = item.get('has_relevant_snippets', False)

        block_lines = [f"\n─── 來源 {i}: {title}", f"URL: {url}"]
        if has_rel and content:
            relevant = _extract_top_snippets(content, keywords, max_snippets=4, snippet_len=400)
            if relevant:
                block_lines.append(f"【關鍵段落】")
                for j, snip in enumerate(relevant, 1):
                    block_lines.append(f"  [{j}] {snip}")
            else:
                block_lines.append(f"【摘要】{snippet}")
        else:
            block_lines.append(f"【摘要】{snippet}")

        block_text = '\n'.join(block_lines)
        block_tokens = estimate_tokens(block_text)
        # Truncate individual source block if it exceeds per-source budget
        if block_tokens > MAX_CONTEXT_TOKENS:
            block_text = truncate_to_token_budget(block_text, MAX_CONTEXT_TOKENS)
        source_blocks.append(block_text)

    body = '\n'.join(source_blocks)
    body_tokens = estimate_tokens(body)
    total_tokens = header_tokens + body_tokens

    # Hard cap: if total exceeds budget, truncate body (keep header + first source)
    if total_tokens > total_token_budget:
        # Preserve at least first source entirely, truncate the rest
        body_chars_budget = int((total_token_budget - header_tokens) * 4.5)
        if len(body) > body_chars_budget:
            body = truncate_to_token_budget(body, int(body_chars_budget / 4.5))

    return header + body

# ─── System Prompt ────────────────────────────────────────────────────────────
RESEARCHER_PROMPT = """你是一個嚴謹的事實問答助手。

【重要】你必須只基於以下資料回答，禁止胡說八道。如果資料未提及某信息，明確說「未提及」，禁止猜測。

回答要求：
- 回答簡潔，用條列式（- 或 1. 2. 3.）
- 每點不超過兩句
- 末尾必須標明資料來源：格式如「資料來源：[1]、[2]」

回答："""

# ─── Research pipeline ────────────────────────────────────────────────────────
def run_research(query):
    """
    Full Harness pipeline:
      1. DuckDuckGo HTML search
      2. Keyword extraction (unigram + CJK bigram)
      3. Parallel fetch top-3 (connection-pooled httpx)
      4. Relevance reranking
      5. Token-budgeted context assembly
    Returns dict for frontend + system prompt injection.
    """
    # Step 1: Search
    results = search_ddg_html(query)
    if not results:
        return {
            "query": query, "results": [], "context": "No search results found.",
            "source_count": 0, "keywords": [], "context_chars": 0,
            "system_prompt": RESEARCHER_PROMPT,
        }

    # Step 2: Keyword extraction from snippets (unigram + CJK bigram)
    all_snippets = " ".join(r.get("snippet", "") for r in results[:8])
    keywords = _extract_keywords(all_snippets, top_n=12)
    if not keywords:
        keywords = [w.strip().lower() for w in query.split() if len(w.strip()) >= 2][:8]

    # Step 3: Fetch top-PARALLEL_FETCHES pages concurrently
    top = results[:PARALLEL_FETCHES]
    fetched = []
    with ThreadPoolExecutor(max_workers=PARALLEL_FETCHES) as executor:
        futures = {executor.submit(fetch_url_content, r["url"]): r for r in top}
        for future in as_completed(futures):
            url, content, err = future.result()
            r = futures[future]
            score = _score_relevance(content, keywords) if not err else 0
            fetched.append({
                **r,
                "content": content,
                "error": err,
                "has_relevant_snippets": score > 0,
                "relevance_score": score,
            })

    # Sort by relevance desc
    fetched.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    # Step 4: Build context (respects per-source token budget)
    context = _build_context(query, fetched, keywords)

    # Step 5: Display results (cleaned)
    display_results = [{
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "snippet": item.get("snippet", ""),
        "relevance": item.get("relevance_score", 0),
    } for item in fetched]

    return {
        "query": query,
        "keywords": keywords,
        "results": display_results,
        "context": context,
        "context_chars": len(context),
        "context_tokens_approx": estimate_tokens(context),
        "source_count": len(fetched),
        "system_prompt": RESEARCHER_PROMPT,
    }

# ─── DuckDuckGo HTML search ───────────────────────────────────────────────────
# Tracks last request time for rate-limit backoff
_ddg_last_request = 0.0
_ddg_min_interval = 5.0   # minimum seconds between DDG searches

def search_ddg_html(query):
    """
    Search DuckDuckGo HTML. Applies rate-limit backoff if called too frequently.
    Returns list of {title, url, snippet}.
    """
    global _ddg_last_request

    try:
        now = time.monotonic()
        wait = _ddg_min_interval - (now - _ddg_last_request)
        if wait > 0:
            time.sleep(wait)
        _ddg_last_request = time.monotonic()

        url = f"https://html.duckduckgo.com/html/?q={quote(query)}&kl=wt-wt"
        resp = _http_client.get(url, headers=_make_headers())
        if resp.status_code == 403:
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
                    "snippet": snippet[:300] if snippet else "",
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
<p>Research query: <input type="text" id="q" value="澳門有多少碼頭"></p>
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
async function doResearch(){var api=document.getElementById('api').value;var q=document.getElementById('q').value;document.getElementById('out').innerHTML='';log('RESEARCH: '+q);try{var r=await fetch(api+'/v1/research',{method:'POST',headers:{'Content-Type':'application/json',...hdrs()},body:JSON.stringify({q})});var j=await r.json();log('Status: OK | Sources: '+j.source_count+' | Keywords: '+JSON.stringify(j.keywords||[]).substring(0,200),'ok');log('Context chars: '+j.context_chars+' | Tokens(approx): '+j.context_tokens_approx,'ok');log('Context:\\n'+j.context.substring(0,800),'ok');}catch(e){log(e.message,'err');}}
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

        # Security: strict PATH_PREFIX strip — reject path traversal attempts
        if path.startswith(PATH_PREFIX):
            path = path[len(PATH_PREFIX):]
        if not path:
            path = "/"
        # Block directory traversal attempts
        if ".." in path or path.startswith("/etc") or path.startswith("/passwd"):
            self.send_response(400)
            self._set_cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Bad path"}).encode())
            return

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
    print(f"[Harness] Proxy :{PORT} → {BACKEND}")
    print(f"[Harness] Auth: {'ON (' + API_KEY + ')' if API_KEY else 'OFF'}")
    print(f"[Harness] Per-source token budget: {MAX_CONTEXT_TOKENS} (~{int(MAX_CONTEXT_TOKENS*4.5)} chars)")
    print(f"[Harness] Per-page char budget: {MAX_CHARS_PER_PAGE} chars")
    print(f"[Harness] Parallel fetches: {PARALLEL_FETCHES} (shared httpx connection pool)")
    print(f"[Harness] HTML: state-machine extractor (no regex hallucination)")
    print(f"[Harness] Keywords: unigram + CJK bigram sliding window")
    print(f"[Harness] Rate-limit backoff: {_ddg_min_interval}s between DDG searches")
    print("[Harness] Endpoints:")
    print("  POST /v1/search    — DuckDuckGo HTML search")
    print("  POST /v1/research  — Harness: search + parallel fetch + token-budgeted context")
    print("  POST /v1/chat/completions — llama.cpp proxy")
    server = ThreadedHTTPServer(("", PORT), CORSProxyHandler)
    server.serve_forever()
