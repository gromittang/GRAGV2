import api from './index'

export default {
  send(question, sessionId, streamFailed = false) {
    return api.post('/chat/', { question, session_id: sessionId, stream_failed: streamFailed })
  },
  sendStream(question, sessionId) {
    // 使用相对路径，让浏览器自动使用当前页面的协议、主机和端口
    return fetch(`/api/v1/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, session_id: sessionId }),
    })
  },
  status() {
    return api.get('/chat/status')
  },
  clear() {
    return api.post('/chat/clear')
  },
  sessions() {
    return api.get('/chat/sessions')
  },
  sessionDetail(sessionId) {
    return api.get(`/chat/sessions/${sessionId}`)
  },
  deleteSession(sessionId) {
    return api.delete(`/chat/sessions/${sessionId}`)
  },
  submitFeedback(data) {
    return api.post('/chat/feedback', data)
  },
  getFeedbackStats() {
    return api.get('/chat/feedback/stats')
  },
}
