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
  let _messageIndex = 0

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
      _messageIndex = 0
      messages.value = history.map((msg, idx) => {
        let content = msg.content || ''
        if (typeof content === 'string' && content.trim().startsWith('{')) {
          try {
            const parsed = JSON.parse(content)
            if (parsed.answer) content = parsed.answer
          } catch (e) { /* not JSON, keep as-is */ }
        }
        if (msg.role === 'assistant') {
          _messageIndex++
        }
        return {
          role: msg.role,
          content,
          sources: msg.sources || null,
          messageIndex: msg.role === 'assistant' ? _messageIndex - 1 : -1,
          bestRelevanceScore: msg.best_relevance_score || 0,
          feedbackSubmitted: false,
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
    _messageIndex = 0
  }

  async function sendMessage(content) {
    messages.value.push({ role: 'user', content, messageIndex: -1, sources: null, bestRelevanceScore: 0, feedbackSubmitted: false })
    loading.value = true
    streaming.value = true
    streamingContent.value = ''

    try {
      const response = await chatApi.sendStream(content, currentSessionId.value)
      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      let fullContent = ''
      let sources = null
      let bestRelevanceScore = 0
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
                if (data.sources && data.sources.length > 0) {
                  sources = data.sources
                }
                bestRelevanceScore = data.best_relevance_score || 0
                const msgIndex = _messageIndex++
                messages.value.push({
                  role: 'assistant',
                  content: fullContent,
                  sources,
                  messageIndex: msgIndex,
                  bestRelevanceScore,
                  feedbackSubmitted: false,
                })
                fullContent = ''
                sources = null
                bestRelevanceScore = 0
              } else if (data.type === 'session_created') {
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

      if (fullContent) {
        const msgIndex = _messageIndex++
        messages.value.push({
          role: 'assistant', content: fullContent,
          messageIndex: msgIndex, bestRelevanceScore: 0, feedbackSubmitted: false,
        })
        if (!currentSessionId.value) {
          fetchSessions()
        }
      }
    } catch (e) {
      console.error('Stream error, trying non-stream:', e)
      try {
        const res = await chatApi.send(content, currentSessionId.value, true)
        const data = res.data
        const sources = data.sources || null
        const bestRelevanceScore = data.best_relevance_score || 0
        const msgIndex = _messageIndex++
        messages.value.push({
          role: 'assistant',
          content: data.answer || '',
          sources,
          messageIndex: msgIndex,
          bestRelevanceScore,
          feedbackSubmitted: false,
        })
        if (data.session_id) {
          currentSessionId.value = data.session_id
          fetchSessions()
        }
      } catch (e2) {
        const msgIndex = _messageIndex++
        messages.value.push({
          role: 'assistant', content: '抱歉，请求失败，请稍后重试。',
          messageIndex: msgIndex, bestRelevanceScore: 0, feedbackSubmitted: false,
        })
      }
    } finally {
      loading.value = false
      streaming.value = false
      streamingContent.value = ''
    }
  }

  async function submitFeedback(messageIndex, feedbackData) {
    const msg = messages.value.find(m => m.messageIndex === messageIndex)
    if (!msg) return false

    const data = {
      session_id: currentSessionId.value,
      message_index: messageIndex,
      question: messages.value.find(m => m.role === 'user' && messages.value.indexOf(m) < messages.value.indexOf(msg))?.content || '',
      answer: msg.content,
      sources: JSON.stringify(msg.sources || []),
      best_relevance_score: msg.bestRelevanceScore || 0,
      ...feedbackData,
    }

    try {
      await chatApi.submitFeedback(data)
      msg.feedbackSubmitted = true
      return true
    } catch (e) {
      console.error('Failed to submit feedback:', e)
      return false
    }
  }

  return {
    messages, sessions, currentSessionId, loading, streaming,
    streamingContent, hasMessages,
    fetchSessions, loadSession, deleteSession, newChat, sendMessage,
    submitFeedback,
  }
})
