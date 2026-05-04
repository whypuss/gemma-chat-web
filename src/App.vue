<template>
  <div class="app-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h1>gemma-chat</h1>
        <span>🔍 free search + local gguf</span>
      </div>
      <button class="new-chat-btn" @click="newChat">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        New chat
      </button>
      <div class="chat-history">
        <div
          v-for="(chat, i) in chatHistory"
          :key="i"
          class="history-item"
          :class="{ active: i === activeChatIndex }"
          @click="loadChat(i)"
        >
          {{ chat[0]?.text?.substring(0, 30) || 'New chat' }}...
        </div>
      </div>
      <div class="sidebar-footer">
        Sunny版 · 免費搜索 + 本地模型
      </div>
    </aside>

    <!-- Main -->
    <main class="main">
      <!-- Header -->
      <div class="header">
        <span class="header-title">{{ currentChat.length > 1 ? 'Conversation' : 'New Chat' }}</span>
        <div style="display:flex;gap:8px;align-items:center;">
          <span class="header-model">{{ apiModel }}</span>
          <button class="settings-btn" @click="showSettings = true">Settings</button>
        </div>
      </div>

      <!-- Chat Area -->
      <div class="chat-area" ref="chatArea">
        <div v-if="!currentChat.length" class="chat-empty">
          <div class="logo">🤖</div>
          <div>Send a message to start chatting</div>
          <div style="font-size:12px;">Powered by Gemma on your phone · Free web search included</div>
        </div>

        <div
          v-for="(msg, i) in currentChat"
          :key="i"
        >
          <!-- Search Results Card -->
          <div v-if="msg.type === 'search_results'" class="search-card">
            <div class="search-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              Web Search · {{ msg.query }}
            </div>
            <div class="search-result" v-for="(r, ri) in msg.results" :key="ri">
              <a :href="r.url" target="_blank" rel="noopener">{{ r.title }}</a>
              <p>{{ r.snippet }}</p>
            </div>
          </div>

          <!-- Message -->
          <div
            v-else
            class="message"
            :class="msg.role"
          >
            <div class="message-avatar">{{ msg.role === 'user' ? 'U' : msg.role === 'loading' ? '' : 'G' }}</div>
            <div class="message-content">
              <div class="bubble" v-if="msg.role === 'user'">{{ msg.text }}</div>
              <div class="bubble" v-else-if="msg.role === 'assistant'" v-html="formatContent(msg.text)"></div>
              <div class="bubble error" v-else-if="msg.role === 'error'">{{ msg.text }}</div>
              <div class="bubble loading-bubble" v-else-if="msg.role === 'loading'">
                <span class="loading-dot"></span>
                <span class="loading-dot"></span>
                <span class="loading-dot"></span>
              </div>
              <div class="meta" v-if="msg.role === 'assistant' && msg.tokens">{{ msg.tokens }} tokens · {{ msg.time }}s</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Input -->
      <div class="input-area">
        <div class="input-wrapper">
          <div class="input-row">
            <textarea
              id="chat-input"
              v-model="inputText"
              placeholder="Ask anything... (e.g. 'What is the weather in Macau today?')"
              rows="1"
              @keydown.enter.exact.prevent="sendMessage"
              @input="autoResize"
              :disabled="loading"
            ></textarea>
            <button class="send-btn" @click="sendMessage" :disabled="loading || !inputText.trim()">
              <svg v-if="!loading" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
              <span v-else class="spinner"></span>
            </button>
          </div>
          <div class="hint">Enter to send · Shift+Enter for new line · Questions are auto-searched</div>
        </div>
      </div>
    </main>

    <!-- Settings Overlay -->
    <div class="settings-overlay" v-if="showSettings" @click.self="showSettings = false">
      <div class="settings-panel">
        <button class="close-btn" @click="showSettings = false">&times;</button>
        <h2>⚙️ Settings</h2>

        <label>API URL</label>
        <input v-model="apiUrl" placeholder="https://your-tunnel-url.trycloudflare.com" />

        <label>Model Name</label>
        <input v-model="apiModel" placeholder="gemma-2-2b-it-abliterated-Q4_K_M.gguf" />

        <label>Max Tokens</label>
        <input type="number" v-model.number="maxTokens" min="10" max="32768" />

        <label>System Prompt</label>
        <input v-model="systemPrompt" placeholder="You are a helpful assistant..." />

        <div class="settings-hint" style="margin-top:12px;">
          Search is automatic — no extra config needed. Works for queries with "what", "who", "when", "where", "latest", etc.
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'

const apiUrl = ref('https://invision-dental-reliance-branches.trycloudflare.com')
const apiModel = ref('gemma-2-2b-it-abliterated-Q4_K_M.gguf')
const maxTokens = ref(512)
const systemPrompt = ref('You are a helpful assistant. When answering questions that need current information, use the search results provided to give accurate answers.')
const showSettings = ref(false)

const inputText = ref('')
const loading = ref(false)
const chatArea = ref(null)
const chatHistory = ref([[]])
const activeChatIndex = ref(0)

const currentChat = computed(() => chatHistory.value[activeChatIndex.value])

function newChat() {
  chatHistory.value.unshift([])
  activeChatIndex.value = 0
  inputText.value = ''
}

function loadChat(i) {
  activeChatIndex.value = i
}

function isSearchQuery(text) {
  const q = text.trim()
  if (q.length > 80) return false
  // Chinese/English trigger words
  const searchTriggers = /^(what|who|when|where|why|how|which|whose|latest|new|current|recent|today|now|202[4-9]|yesterday|tomorrow|weather|news|price|stock|score|result|今天|明天|昨天|今日|天氣|天預|天氣|最新|最近|天預|天氣|天气)/i
  if (searchTriggers.test(q)) return true
  if (q.includes('?')) return true
  // Chinese question patterns
  if (/[一二三四五六七八九十百千萬億零〇]/.test(q) && /[天氣风雨雪冷热温雨晴阴]./.test(q)) return true
  return false
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  currentChat.value.push({ role: 'user', text })
  inputText.value = ''
  autoResize()
  currentChat.value.push({ role: 'loading', text: '' })
  scrollToBottom()

  try {
    let searchResults = null

    // Auto-detect search query
    if (isSearchQuery(text)) {
      currentChat.value.pop()
      currentChat.value.push({ role: 'loading', text: '', type: 'loading' })

      try {
        const sr = await fetch(apiUrl.value + '/v1/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ q: text })
        })
        searchResults = await sr.json()
      } catch (e) {
        console.warn('Search failed:', e)
      }

      currentChat.value.pop()
      if (searchResults?.success && searchResults.results?.length > 0) {
        currentChat.value.push({
          type: 'search_results',
          query: text,
          results: searchResults.results
        })
        scrollToBottom()
      }

      // Synthesize answer with LLM (streaming)
      currentChat.value.push({ role: 'loading', text: '' })
      const startTime = Date.now()
      const messages = []
      if (systemPrompt.value) messages.push({ role: 'system', content: systemPrompt.value })
      messages.push({
        role: 'user',
        content: `Based on these web search results, please answer the question.\n\nSearch results:\n${(searchResults?.results || []).map(r => `Title: ${r.title}\nURL: ${r.url}\nSnippet: ${r.snippet}`).join('\n\n')}\n\nQuestion: ${text}`
      })

      const assistantMsg = { role: 'assistant', text: '', tokens: 0, time: 0 }
      currentChat.value.pop()
      currentChat.value.push(assistantMsg)

      await streamLLM(messages, assistantMsg, startTime)
    } else {
      // Direct chat (streaming)
      currentChat.value.pop()
      const messages = []
      if (systemPrompt.value) messages.push({ role: 'system', content: systemPrompt.value })
      currentChat.value
        .filter(m => ['user', 'assistant', 'error'].includes(m.role))
        .forEach(m => messages.push({ role: m.role === 'assistant' ? 'assistant' : 'user', content: m.text }))

      const assistantMsg = { role: 'assistant', text: '', tokens: 0, time: 0 }
      currentChat.value.push(assistantMsg)
      const startTime = Date.now()
      await streamLLM(messages, assistantMsg, startTime)
    }
  } catch (e) {
    currentChat.value.pop()
    if (currentChat.value.length && currentChat.value[currentChat.value.length - 1].role === 'loading') {
      currentChat.value.pop()
    }
    currentChat.value.push({ role: 'error', text: 'Network error: ' + e.message })
  }

  scrollToBottom()
}

async function streamLLM(messages, msgObj, startTime) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 120000)

  try {
    const r = await fetch(apiUrl.value + '/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: apiModel.value,
        messages,
        max_tokens: maxTokens.value,
        stream: true
      }),
      signal: controller.signal
    })

    if (!r.ok) {
      const err = await r.text()
      msgObj.text = 'API error: ' + r.status + ' ' + err
      return
    }

    const reader = r.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let totalTokens = 0

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data: ')) continue
        const data = trimmed.slice(6).trim()
        if (data === '[DONE]') continue

        try {
          const parsed = JSON.parse(data)
          const content = parsed.choices?.[0]?.delta?.content
          if (content) {
            msgObj.text += content
            totalTokens++
            // Throttle DOM updates to every ~3 chars for smooth streaming
            if (msgObj.text.length % 3 === 0) scrollToBottom()
          }
        } catch (e) {
          // Skip malformed JSON
        }
      }
    }

    msgObj.tokens = totalTokens
    msgObj.time = ((Date.now() - startTime) / 1000).toFixed(1)
    scrollToBottom()
  } catch (e) {
    msgObj.text = 'Stream error: ' + e.message
  } finally {
    clearTimeout(timeout)
    loading.value = false
  }
}

function formatContent(text) {
  if (!text) return ''
  // Escape HTML
  let escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  // Bold for **text**
  escaped = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // Italic for *text* (but not **)
  escaped = escaped.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')
  // Code for `text`
  escaped = escaped.replace(/`(.+?)`/g, '<code>$1</code>')
  // Line breaks
  escaped = escaped.replace(/\n/g, '<br>')
  return escaped
}

function autoResize() {
  nextTick(() => {
    const el = document.getElementById('chat-input')
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 120) + 'px'
    }
  })
}

function scrollToBottom() {
  nextTick(() => {
    if (chatArea.value) chatArea.value.scrollTop = chatArea.value.scrollHeight
  })
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --bg: #0a0a0f;
  --sidebar-bg: #10101a;
  --header-bg: #0f0f18;
  --border: #1a1a2e;
  --user-bubble: #2d5a8a;
  --ai-bubble: #1a1a2a;
  --text: #e0e0e8;
  --text-dim: #888;
  --accent: #4a9eff;
  --error: #ff6b6b;
  --search-bg: #0f1a12;
  --search-border: #1a3020;
}

body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; }

.app-layout { display: flex; height: 100vh; }

/* Sidebar */
.sidebar { width: 240px; background: var(--sidebar-bg); border-right: 1px solid var(--border); display: flex; flex-direction: column; }
.sidebar-header { padding: 16px; border-bottom: 1px solid var(--border); }
.sidebar-header h1 { font-size: 16px; font-weight: 600; color: var(--accent); }
.sidebar-header span { font-size: 11px; color: var(--text-dim); }

.new-chat-btn {
  margin: 12px 12px 8px;
  padding: 8px 12px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
  width: calc(100% - 24px);
}

.chat-history { flex: 1; overflow-y: auto; padding: 0 8px; }
.history-item {
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text-dim);
  cursor: pointer;
  border-radius: 6px;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.history-item:hover, .history-item.active { background: var(--border); color: var(--text); }

.sidebar-footer { padding: 12px; font-size: 11px; color: var(--text-dim); border-top: 1px solid var(--border); }

/* Main */
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.header {
  padding: 12px 20px;
  background: var(--header-bg);
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-title { font-size: 14px; color: var(--text-dim); }
.header-model { font-size: 11px; color: var(--accent); background: rgba(74,158,255,0.1); padding: 3px 8px; border-radius: 12px; }

.settings-btn {
  padding: 5px 12px;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-dim);
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}
.settings-btn:hover { border-color: var(--accent); color: var(--accent); }

/* Chat Area */
.chat-area { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }

.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-dim);
  font-size: 14px;
}
.logo { font-size: 48px; }

/* Messages */
.message { display: flex; gap: 12px; align-items: flex-start; }
.message.user { flex-direction: row-reverse; }
.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.message.user .message-avatar { background: #4a9eff; color: white; }
.message.assistant .message-avatar { background: #2d8a4e; color: white; }
.message.loading .message-avatar { background: var(--border); }

.message-content { max-width: 72%; display: flex; flex-direction: column; gap: 4px; }
.message.user .message-content { align-items: flex-end; }
.message.assistant .message-content { align-items: flex-start; }

.bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
}
.message.user .bubble { background: var(--user-bubble); color: white; border-bottom-right-radius: 4px; }
.message.assistant .bubble { background: var(--ai-bubble); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
.bubble.error { background: rgba(255,107,107,0.1); border: 1px solid var(--error); color: var(--error); }

.loading-bubble { display: flex; gap: 4px; padding: 12px 16px; }
.loading-dot {
  width: 6px; height: 6px;
  background: var(--text-dim);
  border-radius: 50%;
  animation: bounce 1.2s infinite;
}
.loading-dot:nth-child(2) { animation-delay: 0.2s; }
.loading-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%, 80%, 100% { transform: translateY(0); opacity: 0.4; } 40% { transform: translateY(-6px); opacity: 1; } }

.meta { font-size: 11px; color: var(--text-dim); padding: 0 4px; }

/* Search Card */
.search-card {
  background: var(--search-bg);
  border: 1px solid var(--search-border);
  border-radius: 10px;
  overflow: hidden;
  max-width: 600px;
}
.search-header {
  padding: 8px 12px;
  background: rgba(74,158,255,0.08);
  font-size: 12px;
  color: var(--accent);
  display: flex;
  align-items: center;
  gap: 6px;
  border-bottom: 1px solid var(--search-border);
}
.search-result { padding: 8px 12px; border-bottom: 1px solid var(--search-border); }
.search-result:last-child { border-bottom: none; }
.search-result a { font-size: 13px; color: var(--accent); text-decoration: none; }
.search-result a:hover { text-decoration: underline; }
.search-result p { font-size: 12px; color: var(--text-dim); margin-top: 3px; line-height: 1.4; }

/* Input Area */
.input-area { padding: 12px 20px 16px; background: var(--header-bg); border-top: 1px solid var(--border); }
.input-wrapper { max-width: 800px; margin: 0 auto; }
.input-row { display: flex; gap: 8px; align-items: flex-end; }

#chat-input {
  flex: 1;
  padding: 10px 14px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text);
  font-size: 14px;
  font-family: inherit;
  resize: none;
  outline: none;
  max-height: 120px;
}
#chat-input:focus { border-color: var(--accent); }
#chat-input::placeholder { color: var(--text-dim); }
#chat-input:disabled { opacity: 0.5; }

.send-btn {
  width: 40px;
  height: 40px;
  background: var(--accent);
  border: none;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.send-btn:not(:disabled):hover { background: #3a8eef; }

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.hint { font-size: 11px; color: var(--text-dim); margin-top: 6px; text-align: center; }

/* Settings */
.settings-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.settings-panel {
  background: #1a1a2e;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
  width: 420px;
  max-width: 90vw;
  position: relative;
}
.close-btn {
  position: absolute;
  top: 12px;
  right: 16px;
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 20px;
  cursor: pointer;
}
.settings-panel h2 { font-size: 16px; margin-bottom: 16px; color: var(--text); }
.settings-panel label { display: block; font-size: 12px; color: var(--text-dim); margin-bottom: 4px; margin-top: 12px; }
.settings-panel input {
  width: 100%;
  padding: 8px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: 13px;
  margin-top: 4px;
}
.settings-panel input:focus { border-color: var(--accent); outline: none; }
.settings-hint { font-size: 11px; color: var(--text-dim); margin-top: 6px; line-height: 1.4; }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
