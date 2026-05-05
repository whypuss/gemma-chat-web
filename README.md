# gemma-chat-web

Vue 3 SPA 接入本地 AI（Gemma 2B on Android Termux）或任何 OpenAI 相容 API，內建 Hermes-style 研究管線。

**Live:** https://whypuss.github.io/gemma-chat-web/

---

## 架構

```
┌─────────────────────────────────────────────────────────┐
│              Vue 3 SPA (GitHub Pages)                   │
│   isSearch() → research 管線 → streaming 回答            │
│   Thinking bubble: 步進顯示（分析/搜尋/獲取/整理）        │
└────────────────────┬────────────────────────────────────┘
                     │ fetch() — CORS 取決於連接模式
         ┌───────────┴────────────┐
         ▼                        ▼
┌──────────────────┐    ┌──────────────────────────┐
│  Local Mode       │    │  Direct Mode             │
│  手機 CORS Proxy  │    │  OpenAI 相容 API         │
│  (serveo tunnel)  │    │  (OpenRouter / 自架)     │
└──────────────────┘    └──────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  Android Termux (Sony SO-51B)                          │
│  llama.cpp :8080     CORS Proxy :18080                  │
│  gemma-2-2b-it-abliterated-Q4_K_M.gguf                  │
│  SSH reverse tunnel (serveo.net) → moggy.moggy.ccwu.cc  │
└─────────────────────────────────────────────────────────┘
```

---

## 兩種連接模式

### Local Mode（預設）
- CORS proxy URL 指向手機的 serveo tunnel（`https://moggy.moggy.ccwu.cc`）
- 手機跑 `llama.cpp` + CORS proxy，完全免費推論
- Tunnel 断了就 "Failed to fetch"

### Direct Mode
- 任何 OpenAI 相容 API endpoint
- 需自行確保 CORS 允許瀏覽器訪問

---

## 研究管線（isSearch 觸發）

```
用戶問題
    │
    ▼ isSearch() 符合？
    ├─ NO  → 直接 streaming 回答（無 research）
    └─ YES → 研究管線：
                │
                ├─ 1. Thinking bubble 顯示
                │     [🤔 分析問題] → [🔍 搜尋] → [📄 獲取頁面] → [✨ 整理]
                │
                ├─ 2. POST /v1/research
                │     → 手機 CORS proxy (:18080) 处理：
                │           ├─ DuckDuckGo HTML 搜尋
                │           ├─ 並行抓取 top 3 頁面（semaphore 限制）
                │           ├─ Regex 抽出正文（無 bs4）
                │           └─ 句感斷詞（每頁 ~600 chars）
                │
                └─ 3. 合併進 system prompt，streaming 回答
                      research 內容 **不在 UI 顯示**，只進 system prompt
```

**isSearch() 觸發詞（部分）：**
`what|who|when|where|why|how|介紹|比較|推薦|解釋|分析|原因|歷史|多少|幾多|幾個|有多少|天氣|價格`

---

## 專案結構

```
gemma-chat-web/
├── index.html
├── package.json
├── vite.config.js
├── .github/workflows/deploy.yml    ← GitHub Pages auto-deploy
└── src/
    └── App.vue                     ← 全部：UI + 邏輯 + 樣式

phone/                              ← Android Termux 後端
├── cors_proxy.py                   ← CORS proxy + /v1/research
├── watchdog.sh                     ← llama.cpp + proxy + tunnel 看門狗
├── start_all.sh                    ← 一鍵啟動全部服務
└── start_cf_v2.sh                 ← Cloudflare Tunnel v2
```

---

## 樣式系統

iOS Light Design（純 CSS，無 framework）：

```css
--bg: #FFFFFF
--surface: #F5F5F7
--accent: #007AFF
--text: #1D1D1F
--text2: #86868B
--border: #E5E5EA
--radius: 12px
```

Font: `-apple-system, BlinkMacSystemFont, 'SF Pro Display', system-ui`

---

## CORS Proxy Endpoints（:18080）

```
POST /v1/chat/completions   →  轉發至 llama.cpp :8080
POST /v1/models             →  轉發至 llama.cpp :8080
POST /v1/research           →  Hermes 研究管線（搜 → 抓 → 斷）
GET  /                      →  瀏覽器測試頁（含 API key 設定）
```

---

## 部署

### 前端（GitHub Pages）
```bash
npm install
npm run build    # → dist/
git add -A && git commit && git push
# GitHub Actions 自動部署到 https://whypuss.github.io/gemma-chat-web/
```

### 後端（Android Termux）
```bash
# 依賴（只有 httpx）
pip install httpx

# llama.cpp（context=2048，CPU 推理）
llama-server \
  -m /path/to/gemma-2-2b-it-abliterated-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 -ngl 0 -c 2048

# CORS proxy（port 18080）
python3 cors_proxy.py

# SSH reverse tunnel（固定 subdomain）
ssh -i ~/.ssh/id_ed25519 \
  -o StrictHostKeyChecking=no \
  -R moggy:80:localhost:18080 \
  serveo.net
```

---

## 設定（localStorage key: `gc-v5`）

| Key | 預設值 | 說明 |
|-----|--------|------|
| `connMode` | `local` | `local` 或 `direct` |
| `localTunnelUrl` | `https://moggy.moggy.ccwu.cc` | 手機 tunnel URL |
| `directApiUrl` | （空） | Direct API URL |
| `apiModel` | `gemma-2-2b-it-abliterated-Q4_K_M.gguf` | 模型名稱 |
| `maxTokens` | `1024` | 最大回應 tokens |
| `systemPrompt` | 中文研究助手 prompt | system prompt |

---

## Tech Stack

- **前端：** Vue 3 (Composition API) + Vite + GitHub Pages
- **樣式：** Pure CSS，iOS Design System
- **後端：** Python 3 + httpx on Android Termux
- **AI：** llama.cpp (Gemma 2B Q4_K_M) 或任何 OpenAI 相容 API
- **Tunnel：** SSH reverse tunnel（serveo.net）綁定 `moggy.moggy.ccwu.cc`
- **部署：** GitHub Pages（靜態） + GitHub Actions auto-deploy

---

## 已知限制

- **llama.cpp context：** 2048 tokens（手機硬體限制）
- **Research 內容：** 每頁 ~600 chars（句感斷詞），3 個來源
- **Tunnel URL：** serveo 連線斷了需重連，URL 可能改變
- **CORS：** 瀏覽器 fetch 需走 proxy（local mode），Direct mode 需 API 支援 CORS
