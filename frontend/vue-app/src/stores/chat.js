import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import chatApi from '../api/chat'

export const useChatStore = defineStore('chat', () => {
  const messages = ref([])
  const sessions = ref([])
  const currentSessionId = ref(null)
  const loading = ref(false)
  const streaming = ref(false)
  const streamingContent = ref('')
  const tools = ref([])

  const hasMessages = computed(() => messages.value.length > 0)

  async function fetchSessions() {
    try {
      const res = await chatApi.sessions()
      sessions.value = res.data.sessions || []
    } catch (e) {
      console.error('Failed to fetch sessions:', e)
    }
  }

  async function loadSession(sessionId) {
    try {
      const res = await chatApi.sessionDetail(sessionId)
      const history = res.data.history || []
      // Clean messages: ensure content is plain text, extract sources
      messages.value = history.map(msg => {
        let content = msg.content || ''
        // If content is a JSON string, try to extract the real answer
        if (typeof content === 'string' && content.trim().startsWith('{')) {
          try {
            const parsed = JSON.parse(content)
            if (parsed.answer) content = parsed.answer
          } catch (e) { /* not JSON, keep as-is */ }
        }
        return {
          role: msg.role,
          content,
          sources: msg.sources || null,
        }
      })
      currentSessionId.value = sessionId
    } catch (e) {
      console.error('Failed to load session:', e)
    }
  }

  async function deleteSession(sessionId) {
    try {
      await chatApi.deleteSession(sessionId)
      sessions.value = sessions.value.filter(s => s.session_id !== sessionId)
      if (currentSessionId.value === sessionId) {
        newChat()
      }
    } catch (e) {
      console.error('Failed to delete session:', e)
    }
  }

  function newChat() {
    messages.value = []
    currentSessionId.value = null
    streamingContent.value = ''
    streaming.value = false
  }

  async function fetchTools() {
    try {
      const res = await chatApi.agentTools()
      tools.value = res.data.tools || []
    } catch (e) {
      // Tools endpoint may not be available
    }
  }

  async function sendMessage(content) {
    messages.value.push({ role: 'user', content })
    loading.value = true
    streaming.value = true
    streamingContent.value = ''

    try {
      const response = await chatApi.sendStream(content, currentSessionId.value)
      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      let fullContent = ''
      let sources = null
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const text = decoder.decode(value, { stream: true })
        const lines = text.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.type === 'token') {
                fullContent += data.content
                streamingContent.value = fullContent
              } else if (data.type === 'done') {
                streamingContent.value = ''
                // Keep sources as objects (ChatMessage will extract title)
                if (data.sources && data.sources.length > 0) {
                  sources = data.sources
                }
                messages.value.push({
                  role: 'assistant',
                  content: fullContent,
                  sources,
                })
                fullContent = ''
                sources = null
              } else if (data.type === 'session_created') {
                // 收到session_created事件，刷新历史记录
                currentSessionId.value = data.session_id
                fetchSessions()
              } else if (data.type === 'status') {
                // Status updates only logged
              }
            } catch (e) {
              // Partial chunk or non-JSON line, skip
            }
          }
        }
      }

      // If stream ended without done event, save what we have
      if (fullContent) {
        messages.value.push({ role: 'assistant', content: fullContent })
        if (!currentSessionId.value) {
          fetchSessions()
        }
      }
    } catch (e) {
      console.error('Stream error, trying non-stream:', e)
      try {
        const res = await chatApi.send(content, currentSessionId.value)
        const data = res.data
        // Keep sources as objects
        const sources = data.sources || null
        messages.value.push({
          role: 'assistant',
          content: data.answer || '',
          sources,
        })
        if (data.session_id) {
          currentSessionId.value = data.session_id
          fetchSessions()
        }
      } catch (e2) {
        messages.value.push({ role: 'assistant', content: '抱歉，请求失败，请稍后重试。' })
      }
    } finally {
      loading.value = false
      streaming.value = false
      streamingContent.value = ''
    }
  }

  return {
    messages, sessions, currentSessionId, loading, streaming,
    streamingContent, tools, hasMessages,
    fetchSessions, loadSession, deleteSession, newChat, sendMessage, fetchTools,
  }
})
