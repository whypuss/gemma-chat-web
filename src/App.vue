<template>
  <div class="app">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-head">
        <div class="app-brand">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#007AFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M20.188 10.934A8.5 8.5 0 0 1 21 12a8.5 8.5 0 0 1-8.5 8.5 8.5 8.5 0 0 1-8.5-8.5 8.5 8.5 0 0 1 .812-3.866"/><path d="M10.545 5.239A8.5 8.5 0 0 1 12 3a8.5 8.5 0 0 1 8.5 8.5 8.5 8.5 0 0 1-2.756 6.338"/></svg>
          <span>gemma</span>
        </div>
        <button class="icon-btn" @click="newChat" title="New chat">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </button>
      </div>

      <div class="chat-list">
        <div
          v-for="(chat, i) in chatHistory"
          :key="i"
          class="chat-item"
          :class="{ active: i === activeChatIndex }"
          @click="loadChat(i)"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          {{ chatTitle(chat) }}
        </div>
      </div>

      <div class="sidebar-foot">
        <button class="sidebar-action" @click="showSettings = true">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          <span>Settings</span>
        </button>
        <div class="conn-badge" :class="connMode">
          {{ connMode === 'local' ? '📱' : '☁️' }}
        </div>
      </div>
    </aside>

    <!-- Main -->
    <main class="main">
      <!-- Topbar -->
      <header class="topbar">
        <div class="topbar-left">
          <span class="model-label">{{ shortModel }}</span>
        </div>
        <div class="topbar-right">
          <span class="status-dot" :class="statusClass"></span>
          <span class="status-label">{{ statusText }}</span>
          <button class="icon-btn" @click="showSettings = true" title="Settings">⚙️</button>
        </div>
      </header>

      <!-- Messages -->
      <div class="messages" ref="msgEl">
        <div v-if="!currentChat.length" class="empty">
          <div class="empty-ico">
            <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#007AFF" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M20.188 10.934A8.5 8.5 0 0 1 21 12a8.5 8.5 0 0 1-8.5 8.5 8.5 8.5 0 0 1-8.5-8.5 8.5 8.5 0 0 1 .812-3.866"/><path d="M10.545 5.239A8.5 8.5 0 0 1 12 3a8.5 8.5 0 0 1 8.5 8.5 8.5 8.5 0 0 1-2.756 6.338"/></svg>
          </div>
          <p class="empty-title">Start chatting</p>
          <p class="empty-sub">Questions auto-search the web</p>
        </div>

        <div v-for="(msg, i) in currentChat" :key="i">

          <!-- Research block (Hermes-style: keywords + relevance + full page content) -->
          <div v-if="msg.type === 'research_results'" class="research-block">
            <div class="research-hdr">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#007AFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              Research
              <span class="research-q">"{{ msg.query }}"</span>
              <span class="src-count">{{ msg.research.source_count }} sources</span>
              <span v-if="msg.research.context_chars" class="ctx-chars">{{ Math.round(msg.research.context_chars / 100) / 10 }}k chars</span>
              <span v-if="msg.research.keywords && msg.research.keywords.length" class="kw-list">
                <span v-for="kw in msg.research.keywords.slice(0,6)" :key="kw" class="kw-tag">{{ kw }}</span>
              </span>
            </div>
            <div class="sr-list">
              <div v-for="(r, ri) in msg.research.results" :key="ri" class="sr-item">
                <div class="sr-title">
                  <a :href="r.url" target="_blank" rel="noopener">{{ r.title }}</a>
                  <span v-if="r.relevance !== undefined && r.relevance > 0" class="rel-badge" title="Relevance score">{{ r.relevance }}pts</span>
                </div>
                <p class="sr-snippet">{{ r.snippet }}</p>
                <details v-if="r.content && !r.content.startsWith('[Failed')" class="sr-content">
                  <summary>Page content</summary>
                  <div class="sr-content-text">{{ r.content }}</div>
                </details>
              </div>
            </div>
          </div>

          <!-- Message -->
          <div v-else class="msg-row" :class="msg.role">
            <div class="msg-avatar">{{ msg.role === 'user' ? 'U' : 'G' }}</div>
            <div class="msg-content">
              <div class="bubble" v-if="msg.role === 'user'">{{ msg.text }}</div>
              <div class="bubble" v-else-if="msg.role === 'assistant'" v-html="fmt(msg.text)"></div>
              <div class="bubble err-bubble" v-else-if="msg.role === 'error'">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                {{ msg.text }}
              </div>
              <div class="bubble loading-bubble" v-else-if="msg.role === 'loading'">
                <span v-if="isResearching" class="research-status">
                  <span class="pulse-dot"></span>
                  {{ researchPhase === 'searching' ? '🔍 搜索中...' :
                     researchPhase === 'analyzing' ? '⏳ 整合資料中...' :
                     researchPhase === 'streaming' ? '✨ 回答中...' : '處理中...' }}
                </span>
                <span v-else class="ldots">
                  <span class="ldot"></span><span class="ldot"></span><span class="ldot"></span>
                </span>
              </div>
              <!-- Thinking process steps -->
              <div class="bubble thinking-bubble" v-else-if="msg.type === 'thinking'">
                <div class="thinking-hdr">
                  <span class="pulse-dot"></span>
                  思考中 <span class="thinking-time">{{ msg.elapsed }}s</span>
                </div>
                <div class="thinking-steps">
                  <div
                    v-for="(step, si) in msg.steps"
                    :key="si"
                    class="think-step"
                    :class="step.done ? 'done' : 'active'"
                  >
                    <span class="step-icon">{{ step.icon }}</span>
                    <span class="step-text">{{ step.text }}</span>
                  </div>
                </div>
              </div>
              <div class="msg-meta" v-if="msg.role === 'assistant' && msg.time">
                {{ msg.tokens || '?' }} tokens · {{ msg.time }}s
                <span v-if="msg.searchUsed" class="searched-tag">searched</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Input -->
      <div class="input-area">
        <div class="input-card">
          <div class="input-row">
            <textarea
              id="chat-input"
              v-model="inputText"
              placeholder="Ask anything..."
              rows="1"
              @keydown.enter.exact.prevent="sendMessage"
              @input="resize"
              :disabled="loading"
            ></textarea>
            <button class="send-btn" @click="sendMessage" :disabled="loading || !inputText.trim()">
              <svg v-if="!loading" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
              <span v-else class="spin"></span>
            </button>
          </div>
          <div class="input-foot">{{ connModeLabel }} · {{ searchModeLabel }}</div>
        </div>
      </div>
    </main>

    <!-- Settings Sheet -->
    <div class="sheet-overlay" v-if="showSettings" @click.self="showSettings = false">
      <div class="settings-sheet">
        <div class="sheet-handle"></div>
        <div class="sheet-head">
          <h2>Settings</h2>
          <button class="icon-btn" @click="showSettings = false">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="sheet-body">

          <!-- Mode -->
          <div class="field">
            <div class="field-label">Connection</div>
            <div class="seg">
              <button :class="{ on: connMode === 'local' }" @click="connMode = 'local'">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>
                Local
              </button>
              <button :class="{ on: connMode === 'direct' }" @click="connMode = 'direct'">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/></svg>
                Direct
              </button>
            </div>
          </div>

          <!-- Search mode -->
          <div class="field">
            <div class="field-label">Search mode</div>
            <div class="seg">
              <button :class="{ on: searchMode === 'auto' }" @click="searchMode = 'auto'" title="自動判斷是否搜索">
                🔍 自動
              </button>
              <button :class="{ on: searchMode === 'always' }" @click="searchMode = 'always'" title="所有問題都先搜索">
                🌐 總是搜索
              </button>
              <button :class="{ on: searchMode === 'never' }" @click="searchMode = 'never'" title="純本地生成，不搜索">
                🤖 純本地
              </button>
            </div>
          </div>

          <!-- Local fields -->
          <template v-if="connMode === 'local'">
            <div class="field">
              <div class="field-label">Phone tunnel URL</div>
              <input v-model="localTunnelUrl" placeholder="https://xxx.trycloudflare.com" />
            </div>
            <div class="field">
              <div class="field-label">Model name</div>
              <input v-model="apiModel" placeholder="gemma-2-2b-it-abliterated-Q4_K_M.gguf" />
            </div>
          </template>

          <!-- Direct fields -->
          <template v-else>
            <div class="field">
              <div class="field-label">API URL</div>
              <input v-model="directApiUrl" placeholder="https://api.example.com/v1" />
            </div>
            <div class="field">
              <div class="field-label">Model name</div>
              <input v-model="apiModel" placeholder="gpt-4o-mini" />
            </div>
          </template>

          <div class="field">
            <div class="field-label">Max tokens</div>
            <input type="number" v-model.number="maxTokens" min="10" max="32768" />
          </div>

          <div class="field">
            <div class="field-label">System prompt</div>
            <textarea v-model="systemPrompt" rows="3" placeholder="You are a helpful assistant..."></textarea>
          </div>

          <button class="test-btn" @click="testConn" :disabled="testing">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            {{ testing ? 'Testing...' : 'Test connection' }}
          </button>
          <div v-if="testMsg" class="test-msg" :class="testOk ? 'ok' : 'err'">{{ testMsg }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, watch } from 'vue'

const SK = 'gc-v5'

// ── State ────────────────────────────────────────────────
const inputText = ref('')
const loading = ref(false)
const isResearching = ref(false)
const researchPhase = ref('')   // 'searching' | 'fetching' | 'analyzing'
const msgEl = ref(null)
const chatHistory = ref([[]])
const activeChatIndex = ref(0)
const showSettings = ref(false)
const testing = ref(false)
const testMsg = ref('')
const testOk = ref(false)
const connReady = ref(true)
const thinkingSteps = ref([])

// ── Request abort controller + request ID (prevents stale streams) ─
let currentCtrl = null   // cleared after each request cycle
let currentReqId = 0     // incremented on each sendMessage; stale responses are discarded

// ── History memory management ────────────────────────────────────────
// Freeze old messages + cap total history chars to prevent Vue reactive OOM
const MAX_HISTORY_CHARS = 1500   // ~300-500 tokens for gemma-2b; safe for 1024 ctx

function _freezeAndCap(chat) {
  // Freeze oldest messages first (oldest = start of array)
  // Work backwards, freezing until total chars ≤ MAX_HISTORY_CHARS
  let total = 0
  const preserved = []
  for (let i = chat.length - 1; i >= 0; i--) {
    const m = chat[i]
    const cost = (m.text || '').length + 40   // 40 = role overhead
    if (total + cost <= MAX_HISTORY_CHARS) {
      total += cost
      preserved.push(m)
    } else {
      // Freeze the rest to kill deep-reactivity overhead
      if (!Object.isFrozen(m)) Object.freeze(m)
    }
  }
  // Reverse: oldest trimmed messages are frozen; preserved ones stay reactive
  return preserved.reverse()
}

function trimCurrentChat() {
  const chat = currentChat.value
  if (chat.length <= 4) return   // ≤2 exchanges: not worth trimming
  const trimmed = _freezeAndCap(chat)
  if (trimmed.length < chat.length) {
    chat.length = 0
    chat.push(...trimmed)
  }
}

// ── Persisted ────────────────────────────────────────────
const connMode = ref('local')
const localTunnelUrl = ref('https://moggy.moggy.ccwu.cc')
const directApiUrl = ref('')
const apiModel = ref('gemma-2-2b-it-abliterated-Q4_K_M.gguf')
const maxTokens = ref(1024)
const searchMode = ref('auto')   // 'auto' | 'always' | 'never'
const systemPrompt = ref('你是一個專業的研究員助手。請嚴格按照以下步驟回答：\n1. 【閱讀】仔細閱讀每個來源的內容，標記關鍵事實和數據\n2. 【對比】如果不同來源有矛盾，標注出來\n3. 【回答】用條列式（- 或 1. 2. 3.）回答用戶問題，禁止胡說八道\n4. 【引用】在回答末尾標明：資料來源：[序号]\n\n重要原則：\n- 如果某個來源沒有提及某信息，明確說「未提及」，而不是猜測\n- 不要摻雜個人意見或猜測，只能基於提供的來源\n- 回答簡潔有力，每點不超過兩句話\n- 如果信息不足，直接說「根據現有資料無法確定」')

function save() {
  localStorage.setItem(SK, JSON.stringify({
    connMode: connMode.value,
    localTunnelUrl: localTunnelUrl.value,
    directApiUrl: directApiUrl.value,
    apiModel: apiModel.value,
    maxTokens: maxTokens.value,
    searchMode: searchMode.value,
    systemPrompt: systemPrompt.value,
  }))
}
function load() {
  try {
    const s = JSON.parse(localStorage.getItem(SK) || '{}')
    if (s.connMode) connMode.value = s.connMode
    if (s.localTunnelUrl) localTunnelUrl.value = s.localTunnelUrl
    if (s.directApiUrl) directApiUrl.value = s.directApiUrl
    if (s.apiModel) apiModel.value = s.apiModel
    if (s.maxTokens) maxTokens.value = s.maxTokens
    if (s.searchMode) searchMode.value = s.searchMode
    if (s.systemPrompt) systemPrompt.value = s.systemPrompt
  } catch {}
  // Migrate stale tunnel URLs
  if (['https://ai.moggy.ccwu.cc', 'https://moggy.serveousercontent.com'].includes(localTunnelUrl.value)) {
    localTunnelUrl.value = 'http://moggy.moggy.ccwu.cc'
    save()
  }
}
onMounted(load)

// Auto-save settings whenever they change (no need to send a message first)
watch([connMode, localTunnelUrl, directApiUrl, apiModel, maxTokens, searchMode], () => save())

// ── Computed ─────────────────────────────────────────────
const currentChat = computed(() => chatHistory.value[activeChatIndex.value])
const baseUrl = computed(() =>
  (connMode.value === 'local' ? localTunnelUrl.value : directApiUrl.value).replace(/\/$/, '')
)
const shortModel = computed(() => {
  const m = apiModel.value
  return m.length > 24 ? m.slice(0, 22) + '…' : m
})
const connModeLabel = computed(() => connMode.value === 'local' ? '📱 local mode' : '☁️ direct mode')
const searchModeLabel = computed(() => ({
  auto: '🔍 auto-search',
  always: '🌐 always search',
  never: '🤖 local only',
}[searchMode.value] || ''))
const statusClass = computed(() => loading.value ? 'loading' : connReady.value ? 'ok' : 'err')
const statusText = computed(() => loading.value ? 'thinking…' : connReady.value ? 'ready' : 'offline')

// ── Chat ops ─────────────────────────────────────────────
function chatTitle(chat) {
  const u = chat.find(m => m.role === 'user')
  if (!u) return 'Empty'
  return u.text.slice(0, 28) || 'Empty'
}
function newChat() { chatHistory.value.unshift([]); activeChatIndex.value = 0; inputText.value = '' }
function loadChat(i) { activeChatIndex.value = i }

// ── Search detection ─────────────────────────────────────
function isSearch(q) {
  q = q.trim()
  if (q.length > 120) return false
  // Intent triggers: info-seeking question words + explicit question mark
  // Note: intentionally excludes bare Chinese numerals (e.g. "列出三個優點")
  // to avoid forcing research on non-search queries that happen to contain numbers
  // Cantonese (廣東話) patterns: 點睇 好唔好 值唔值得 幾時 幾耐 係邊 係咪 聽講 知唔知 etc.
  return /(what|who|when|where|why|how|which|whose|latest|news|weather|current|recent|today|now|yesterday|tomorrow|介紹|比較|推薦|解釋|分析|原理|原因|結果|影響|歷史 最新|最近|今日今天|天氣|天氣預報|天氣怎樣|澳門天|香港天|天氣如何|天氣情況|價格|多少|幾多|幾個|有多少|邊個|邊間|點解|點樣|如何|怎樣|係咩|係邊|關於|討論|點睇|好唔好|值唔值得|幾時|幾耐|可唔可以|可不可以|有無|有冇|係咪|係唔係|聽講|聽說|知唔知|係真假)/i.test(q) || q.includes('?')
}

// ── API ──────────────────────────────────────────────────

// Hermes-style research: search + fetch page content + extract text
// NOTE: wraps in AbortSignal.timeout(30000) — if tunnel is假死 (silent drop)
// without closing the connection, we bail out after 30s instead of hanging forever
async function doResearch(q) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 30000)
  try {
    if (connMode.value === 'direct') {
      try {
        const r = await fetch(baseUrl.value + '/v1/research', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ q }),
          signal: controller.signal,
        })
        clearTimeout(timer)
        if (r.ok) return await r.json()
      } catch (e) {
        clearTimeout(timer)
        if (e.name === 'AbortError') return { research_aborted: true }
        return null
      }
    } else {
      try {
        const r = await fetch(baseUrl.value + '/v1/research', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ q }),
          signal: controller.signal,
        })
        clearTimeout(timer)
        if (r.ok) return await r.json()
      } catch (e) {
        clearTimeout(timer)
        if (e.name === 'AbortError') return { research_aborted: true }
        return null
      }
    }
  } finally {
    clearTimeout(timer)
  }
  return null
}

async function streamChat(msgs, out, abortSignal) {
  // Use shared abort controller if provided (from sendMessage), otherwise fresh one
  const ctrl = abortSignal ? null : new AbortController()
  const id = setTimeout(() => { if (ctrl) ctrl.abort() }, 60000)   // 60s max streaming
  const signal = abortSignal || (ctrl ? ctrl.signal : null)
  try {
    const r = await fetch(baseUrl.value + '/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: apiModel.value, messages: msgs, max_tokens: maxTokens.value, stream: true }),
      signal
    })
    if (!r.ok) {
      const text = await r.text()
      console.error('[streamChat] HTTP error', r.status, text)
      throw new Error(`HTTP ${r.status}`)
    }
    const reader = r.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      // Keep incomplete last line in buffer for next chunk (fixes JSON truncation)
      buf = lines.pop() || ''
      for (const l of lines) {
        const t = l.trim()
        if (!t.startsWith('data: ')) continue
        const data = t.slice(6)
        if (data === '[DONE]') continue
        try {
          const p = JSON.parse(data)
          const c = p.choices?.[0]?.delta?.content
          if (c) { out.text += c; scroll() }
        } catch {
          // Silent: JSON truncated by network boundary — will retry on next chunk
        }
      }
    }
  } catch (e) {
    // Swallow abort — caller (sendMessage) may have intentionally cancelled us
    if (e.name === 'AbortError' || e.message?.includes('abort')) return
    throw e   // re-throw real errors so sendMessage catch can display them
  } finally {
    clearTimeout(id)
  }
}

// ── Send ─────────────────────────────────────────────────
// fetchResearch: wrapper that bridges sendMessage's AbortSignal to doResearch's internal controller
async function fetchResearch(q, signal) {
  // Run doResearch but abort early if signal is cancelled
  const timeout = AbortSignal.timeout(30000)
  const combined = AbortSignal.any([signal, timeout])
  const r = await fetch(baseUrl.value + '/v1/research', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q }),
    signal: combined,
  })
  if (!r.ok) return null
  return r.json()
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  const reqId = ++currentReqId
  if (currentCtrl) currentCtrl.abort()
  currentCtrl = new AbortController()

  inputText.value = ''
  loading.value = true

  const chat = currentChat.value
  chat.push({ role: 'user', text })
  scroll()

  try {
    let context = ""
    let timerId = null

    const shouldSearch = searchMode.value === 'always' || (searchMode.value === 'auto' && isSearch(text))

    if (shouldSearch && searchMode.value !== 'never') {
      isResearching.value = true

      const thinkingMsg = {
        type: 'thinking',
        elapsed: '0.0',
        steps: [
          { text: '分析問題中...', icon: '🤔', done: true },
          { text: '搜尋網頁中...', icon: '🔍', done: false }
        ]
      }
      chat.push(thinkingMsg)
      scroll()

      const startMs = Date.now()
      timerId = setInterval(() => {
        thinkingMsg.elapsed = ((Date.now() - startMs) / 1000).toFixed(1)
      }, 100)

      const resData = await fetchResearch(text, currentCtrl.signal)
      if (reqId !== currentReqId) {
        clearInterval(timerId)
        return
      }

      clearInterval(timerId)

      if (resData && resData.results) {
        context = ((resData.context || '').replace(/\[ ?\d+ ?\]/g, '').replace(/\s+/g, ' ').trim().slice(0, 3000))
        thinkingMsg.steps[1].done = true
        thinkingMsg.steps.push({ text: `已獲取 ${resData.source_count} 個頁面內容`, icon: '📄', done: true })
      } else {
        thinkingMsg.steps[1].done = true
        thinkingMsg.steps.push({ text: `無法獲取資料`, icon: '⚠️', done: true })
      }
    }

    const reply = { role: 'assistant', text: '', searchUsed: !!context, time: 0 }
    chat.push(reply)
    scroll()

    const startTime = Date.now()

    const msgs = buildMsgs(context)
    console.log("[DEBUG] context:", context?.slice(0,100), "msgs:", JSON.stringify(msgs))
    researchPhase.value = 'streaming'

    await streamChat(msgs, reply, currentCtrl.signal, reqId)

    const ti = chat.indexOf(chat.find(m => m.type === 'thinking'))
    if (ti !== -1) chat.splice(ti, 1)

    reply.time = ((Date.now() - startTime) / 1000).toFixed(1)
    reply.tokens = reply.text.split(/\s+/).length
    trimCurrentChat()

  } catch (e) {
    if (e.name !== 'AbortError') {
      chat.push({ role: 'error', text: `Connection Error: ${e.message}` })
    }
  }

  if (reqId === currentReqId) {
    currentCtrl = null
    loading.value = false
    isResearching.value = false
    scroll()
    save()
  }
}

function buildMsgs(context) {
  const msgs = []
  if (systemPrompt.value) msgs.push({ role: 'system', content: systemPrompt.value })
  currentChat.value
    .filter(m => ['user','assistant'].includes(m.role) && m.text)
    .forEach(m => msgs.push({ role: m.role, content: m.text }))
  // Inject research context into last user message
  if (context) {
    const lastIdx = msgs.length - 1
    if (msgs[lastIdx]?.role === 'user') {
      msgs[lastIdx] = {
        role: 'user',
        content: `資料庫參考內容：\n${context}\n\n用戶問題：${msgs[lastIdx].content}`
      }
    }
  }
  return msgs
}

// ── Test ────────────────────────────────────────────────
async function testConn() {
  testing.value = true
  testMsg.value = ''
  try {
    const r = await fetch(baseUrl.value + '/v1/models', {
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(10000)
    })
    if (r.ok) {
      const d = await r.json()
      connReady.value = true
      testMsg.value = `Connected — ${d.data?.[0]?.id || 'ok'}`
      testOk.value = true
    } else {
      connReady.value = false
      testMsg.value = `HTTP ${r.status}`
      testOk.value = false
    }
  } catch (e) {
    connReady.value = false
    testMsg.value = e.message
    testOk.value = false
  }
  testing.value = false
}

// ── Helpers ─────────────────────────────────────────────
function truncateContext(text, maxChars) {
  // Rough truncation: 1 token ≈ 4 chars in Chinese, stay well under context limit
  if (!text || text.length <= maxChars) return text
  // Cut at sentence boundary near maxChars
  const cut = text.slice(0, maxChars)
  const lastPeriod = cut.lastIndexOf('。')
  const lastNewline = cut.lastIndexOf('\n')
  const cutoff = Math.max(lastPeriod, lastNewline) + 1
  return text.slice(0, Math.max(cutoff, maxChars * 0.85)) + '\n\n... [內容已截斷]'
}
function fmt(t) {
  if (!t) return ''
  // Step 1: escape ALL HTML entities FIRST (before any markdown transforms)
  // This ensures raw HTML from the model cannot execute
  const esc = t
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
  // Step 2: safe markdown-to-HTML (only creates <strong>, <em>, <code>)
  // These are safe even if source contains malicious text (already escaped above)
  return esc
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}
function resize() {
  nextTick(() => {
    const el = document.getElementById('chat-input')
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 120) + 'px' }
  })
}
function scroll() {
  nextTick(() => { if (msgEl.value) msgEl.value.scrollTop = msgEl.value.scrollHeight })
}
</script>

<style>
/* ── iOS Light Design System ──────────────────────────── */
:root {
  --bg: #FFFFFF;
  --surface: #F5F5F7;
  --surface2: #FAFAFA;
  --border: #E5E5EA;
  --border2: #D1D1D6;
  --text: #1D1D1F;
  --text2: #86868B;
  --text3: #AEAEB2;
  --accent: #007AFF;
  --accent-bg: rgba(0,122,255,0.08);
  --err: #FF3B30;
  --ok: #34C759;
  --warn: #FF9500;
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.04);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.10), 0 2px 8px rgba(0,0,0,0.06);
  --radius: 12px;
  --radius-sm: 8px;
  --radius-lg: 16px;
  --font: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text', system-ui, sans-serif;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body { height: 100%; }
body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

.app { display: flex; height: 100dvh; overflow: hidden; }

/* ── Sidebar ──────────────────────────────────────────── */
.sidebar {
  width: 210px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 14px 14px;
  border-bottom: 1px solid var(--border);
}

.app-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.3px;
}

.icon-btn {
  width: 30px; height: 30px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .15s;
  box-shadow: var(--shadow-sm);
}
.icon-btn:hover { background: var(--accent); border-color: var(--accent); color: white; }

.chat-list { flex: 1; overflow-y: auto; padding: 8px 8px; }
.chat-list::-webkit-scrollbar { width: 3px; }
.chat-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.chat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  font-size: 13px;
  color: var(--text2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background .12s, color .12s;
  margin-bottom: 1px;
}
.chat-item:hover { background: var(--bg); color: var(--text); box-shadow: var(--shadow-sm); }
.chat-item.active { background: var(--bg); color: var(--accent); box-shadow: var(--shadow-sm); }

.sidebar-foot {
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-action {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: var(--text2);
  font-size: 13px;
  font-family: var(--font);
  cursor: pointer;
  padding: 5px 7px;
  border-radius: var(--radius-sm);
  transition: color .12s, background .12s;
}
.sidebar-action:hover { color: var(--text); background: var(--bg); }

.conn-badge {
  font-size: 12px;
  padding: 2px 8px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow-sm);
}

/* ── Main ─────────────────────────────────────────────── */
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }

/* Topbar */
.topbar {
  padding: 13px 20px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  flex-shrink: 0;
  -webkit-app-region: drag;
  position: relative;
  z-index: 10;
}
.topbar-left, .topbar-right { display: flex; align-items: center; gap: 8px; -webkit-app-region: no-drag; }

.model-label {
  font-size: 12px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--text2);
  background: var(--surface);
  padding: 3px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
}

.status-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--ok);
}
.status-dot.loading { background: var(--warn); animation: pulse 1.5s infinite; }
.status-dot.err { background: var(--err); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

.status-label { font-size: 12px; color: var(--text2); }

/* Messages */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: var(--bg);
}
.messages::-webkit-scrollbar { width: 5px; }
.messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

/* Empty state */
.empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding-bottom: 60px;
  gap: 6px;
}
.empty-ico { margin-bottom: 6px; }
.empty-title { font-size: 18px; font-weight: 600; color: var(--text); }
.empty-sub { font-size: 13px; color: var(--text2); }

/* Msg rows */
.msg-row {
  display: flex;
  flex-direction: column;
  max-width: 68%;
  animation: appear .18s ease;
}
@keyframes appear { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
.msg-row.user { align-self: flex-end; align-items: flex-end; }
.msg-row.assistant { align-self: flex-start; align-items: flex-start; }

.msg { display: flex; gap: 10px; align-items: flex-start; }
.msg-row.user .msg { flex-direction: row-reverse; }

.msg-avatar {
  width: 30px; height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
  font-family: var(--font);
}
.msg-row.user .msg-avatar { background: var(--accent); color: white; }
.msg-row.assistant .msg-avatar { background: var(--surface); border: 1px solid var(--border); color: var(--text2); }

.msg-content { display: flex; flex-direction: column; gap: 4px; min-width: 0; }

/* Bubbles */
.bubble {
  padding: 11px 15px;
  border-radius: var(--radius);
  font-size: 15px;
  line-height: 1.55;
  word-break: break-word;
}
.msg-row.user .bubble {
  background: var(--accent);
  color: white;
  border-bottom-right-radius: 4px;
}
.msg-row.assistant .bubble {
  background: var(--surface);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}
.err-bubble {
  background: rgba(255,59,48,0.06);
  border: 1px solid rgba(255,59,48,0.2);
  color: var(--err);
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

/* Loading dots */
.loading-bubble { display: flex; align-items: center; gap: 5px; padding: 12px 16px; }
.ldot {
  width: 6px; height: 6px;
  background: var(--text3);
  border-radius: 50%;
  animation: bounce 1.3s infinite;
}
.ldot:nth-child(2) { animation-delay: .2s; }
.ldot:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%,60%,100%{transform:translateY(0);opacity:.35} 30%{transform:translateY(-5px);opacity:1} }

/* Research phase indicator */
.research-status {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text2);
  font-size: 13px;
}
.pulse-dot {
  width: 7px;
  height: 7px;
  background: var(--accent);
  border-radius: 50%;
  animation: pulse-ring 1.4s ease-out infinite;
  flex-shrink: 0;
}
@keyframes pulse-ring {
  0%   { box-shadow: 0 0 0 0 rgba(0,122,255,0.4); }
  70%  { box-shadow: 0 0 0 6px rgba(0,122,255,0); }
  100% { box-shadow: 0 0 0 0 rgba(0,122,255,0); }
}

.msg-meta {
  font-size: 11px;
  color: var(--text3);
  padding: 0 2px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.searched-tag {
  background: var(--accent-bg);
  color: var(--accent);
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 10px;
}

/* Research block (Hermes-style enriched search) */
.research-block {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  max-width: 600px;
  box-shadow: var(--shadow-sm);
}
.research-hdr {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 14px;
  font-size: 12px;
  color: var(--accent);
  background: var(--accent-bg);
  border-bottom: 1px solid var(--border);
  font-weight: 500;
}
.research-q { color: var(--text2); font-style: italic; flex: 1; }
.src-count {
  background: var(--accent);
  color: white;
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 9px;
  font-weight: 600;
}
.ctx-chars {
  color: var(--text2);
  font-size: 11px;
}
.kw-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-left: 4px;
}
.kw-tag {
  background: rgba(0,122,255,0.08);
  color: var(--accent);
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 6px;
  font-weight: 400;
}
.rel-badge {
  background: rgba(52,199,89,0.1);
  color: var(--ok);
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 6px;
  margin-left: 6px;
  font-weight: 500;
}
.sr-list { }
.sr-item {
  padding: 11px 14px;
  border-bottom: 1px solid var(--border);
}
.sr-item:last-child { border-bottom: none; }
.sr-title a {
  font-size: 13px;
  color: var(--accent);
  text-decoration: none;
  font-weight: 500;
}
.sr-title a:hover { text-decoration: underline; }
.sr-snippet {
  font-size: 12px;
  color: var(--text2);
  margin-top: 3px;
  line-height: 1.4;
}
.sr-content {
  margin-top: 6px;
}
.sr-content summary {
  font-size: 11px;
  color: var(--text3);
  cursor: pointer;
  user-select: none;
  padding: 2px 0;
}
.sr-content summary:hover { color: var(--accent); }
.sr-content-text {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text2);
  line-height: 1.5;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  max-height: 180px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── Input ────────────────────────────────────────────── */
.input-area {
  padding: 14px 20px 18px;
  background: var(--bg);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.input-card {
  max-width: 720px;
  margin: 0 auto;
}
.input-row { display: flex; gap: 10px; align-items: flex-end; }

#chat-input {
  flex: 1;
  padding: 11px 15px;
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 15px;
  font-family: var(--font);
  resize: none;
  outline: none;
  max-height: 120px;
  transition: border-color .15s, box-shadow .15s;
}
#chat-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-bg);
  background: var(--bg);
}
#chat-input::placeholder { color: var(--text3); }
#chat-input:disabled { opacity: .5; }

.send-btn {
  width: 40px; height: 40px;
  background: var(--accent);
  border: none;
  border-radius: var(--radius);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: opacity .15s, transform .1s;
  box-shadow: var(--shadow-sm);
}
.send-btn:not(:disabled):hover { opacity: .88; }
.send-btn:not(:disabled):active { transform: scale(.94); }
.send-btn:disabled { opacity: .3; cursor: not-allowed; }

.spin {
  width: 15px; height: 15px;
  border: 2px solid rgba(255,255,255,.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to{transform:rotate(360deg)} }

.input-foot {
  font-size: 11px;
  color: var(--text3);
  margin-top: 7px;
  text-align: center;
}

/* ── Settings Sheet (iOS Bottom Sheet) ────────────────── */
.sheet-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.35);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  z-index: 200;
}

.settings-sheet {
  background: var(--bg);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  width: 100%;
  max-width: 540px;
  max-height: 88dvh;
  overflow-y: auto;
  animation: sheetUp .3s cubic-bezier(0.32, 0.72, 0, 1);
  box-shadow: var(--shadow-lg);
}
@keyframes sheetUp { from{transform:translateY(100%)} to{transform:translateY(0)} }

.sheet-handle {
  width: 36px; height: 4px;
  background: var(--border2);
  border-radius: 2px;
  margin: 10px auto 0;
}

.sheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px 10px;
  border-bottom: 1px solid var(--border);
}
.sheet-head h2 { font-size: 17px; font-weight: 600; color: var(--text); }

.sheet-body { padding: 16px 20px 32px; }

.field { margin-bottom: 18px; }
.field-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  margin-bottom: 7px;
}

.field input,
.field textarea {
  width: 100%;
  padding: 10px 13px;
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  font-size: 14px;
  font-family: var(--font);
  outline: none;
  transition: border-color .15s, box-shadow .15s;
}
.field input:focus,
.field textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-bg);
}
.field textarea { resize: vertical; min-height: 64px; }

.seg {
  display: flex;
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 3px;
  gap: 3px;
}
.seg button {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 14px;
  background: none;
  border: none;
  border-radius: 6px;
  color: var(--text2);
  font-size: 14px;
  font-family: var(--font);
  font-weight: 500;
  cursor: pointer;
  transition: all .15s;
}
.seg button.on {
  background: var(--bg);
  color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.test-btn {
  width: 100%;
  padding: 12px;
  background: var(--accent);
  border: none;
  border-radius: var(--radius-sm);
  color: white;
  font-size: 15px;
  font-family: var(--font);
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin-top: 8px;
  transition: opacity .15s;
  box-shadow: var(--shadow-sm);
}
.test-btn:not(:disabled):hover { opacity: .88; }
.test-btn:disabled { opacity: .45; cursor: not-allowed; }

.test-msg {
  margin-top: 10px;
  padding: 10px 13px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}
.test-msg.ok { background: rgba(52,199,89,0.08); border: 1px solid rgba(52,199,89,0.2); color: var(--ok); }
.test-msg.err { background: rgba(255,59,48,0.06); border: 1px solid rgba(255,59,48,0.2); color: var(--err); }

/* ── Mobile ───────────────────────────────────────────── */
@media (max-width: 600px) {
  .sidebar { display: none; }
  .msg-row { max-width: 94%; }
  .search-block { max-width: 94%; }
  .messages { padding: 16px 14px; }
}

/* ── Thinking bubble ──────────────────────────────────── */
.thinking-bubble {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  padding: 12px 16px !important;
  min-width: 220px;
}
.thinking-hdr {
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.thinking-time {
  font-size: 11px;
  color: var(--text-dim);
  opacity: 0.6;
  margin-left: 4px;
}
.thinking-steps {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.think-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-dim);
  transition: color .2s;
}
.think-step.active {
  color: var(--accent);
}
.think-step.done {
  color: var(--ok, #34c759);
}
.think-step.done .step-text {
  text-decoration: line-through;
  opacity: 0.6;
}
.step-icon {
  font-size: 14px;
  flex-shrink: 0;
  width: 20px;
  text-align: center;
}
.step-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
