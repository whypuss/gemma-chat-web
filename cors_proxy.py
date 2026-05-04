#!/usr/bin/env python3
"""CORS-aware reverse proxy with free web search + chat completions proxy to llama.cpp."""
import http.server
import urllib.request
import urllib.error
import urllib.parse
import json
import sys
import socketserver
import os
from urllib.parse import urlparse
import httpx

PORT = 18080
BACKEND = "http://localhost:8080"
PATH_PREFIX = "/1edf5d12423b60e8"

# ─── Web Search (DuckDuckGo HTML scraping — FREE) ─────────────────────────────

def search_ddg(query: str, limit: int = 8) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    try:
        resp = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        return {"success": False, "error": str(e)}

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for result in soup.select(".result")[:limit]:
            a_tag = result.select_one(".result__a")
            snippet = result.select_one(".result__snippet")
            if a_tag:
                title = a_tag.get_text(strip=True)
                href = a_tag.get("href", "")
                try:
                    parsed = urllib.parse.urlparse(href)
                    if parsed.query:
                        qs = urllib.parse.parse_qs(parsed.query)
                        real_url = qs.get("uddg", [href])[0]
                    else:
                        real_url = href
                except Exception:
                    real_url = href
                results.append({
                    "title": title,
                    "url": real_url,
                    "snippet": snippet.get_text(strip=True) if snippet else ""
                })
        return {"success": True, "query": query, "results": results}
    except Exception as e:
        return {"success": False, "error": f"Parse error: {e}"}


class CORSProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        sys.stderr.write("[CORS] " + (fmt % args) + "\n")

    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._set_cors()
        self.end_headers()
        self.wfile.write(body)

    def _do_search(self):
        """Handle /v1/search endpoint (with or without prefix)."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                body = json.loads(self.rfile.read(length))
                q = body.get("q", body.get("query", ""))
            else:
                q = ""
        except Exception:
            q = ""

        if not q:
            # Try query param
            parsed = urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            q = params.get("q", [""])[0]

        if not q:
            self._send_json({"success": False, "error": "q parameter required"})
            return

        result = search_ddg(q)
        self._send_json(result)

    def do_GET(self):
        parsed = urlparse(self.path)

        # Search endpoint: /v1/search or /1edf5d12423b60e8/v1/search
        path = parsed.path.rstrip("/")
        if path in ("/v1/search", PATH_PREFIX + "/v1/search"):
            self._do_search()
            return

        self._proxy("GET")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # Search endpoint: /v1/search or /1edf5d12423b60e8/v1/search
        if path in ("/v1/search", PATH_PREFIX + "/v1/search"):
            self._do_search()
            return

        self._proxy("POST")

    def _proxy(self, method):
        parsed = urlparse(self.path)
        new_path = parsed.path[len(PATH_PREFIX):] if parsed.path.startswith(PATH_PREFIX) else parsed.path
        if not new_path: new_path = "/"
        backend_url = BACKEND + new_path + (("?" + parsed.query) if parsed.query else "")

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None
        skip = {"host", "connection", "content-length"}
        headers = {k: v for k, v in self.headers.items() if k.lower() not in skip}

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
                if content: self.wfile.write(content)
        except urllib.error.HTTPError as e:
            content = e.read()
            self.send_response(e.code)
            self._set_cors()
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if content: self.wfile.write(content)
        except Exception as e:
            sys.stderr.write("[CORS] Error: " + str(e) + "\n")
            self.send_response(502)
            self._set_cors()
            self.end_headers()
            err = json.dumps({"error": str(e)}).encode()
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    print(f"[CORS] Proxy: {PORT} -> {BACKEND}")
    print(f"[CORS] Search: http://localhost:{PORT}/v1/search?q=...")
    print(f"[CORS] Chat:   http://localhost:{PORT}/v1/chat/completions")
    server = ThreadedHTTPServer(("", PORT), CORSProxyHandler)
    server.serve_forever()
