import api from './index'

const PM_SOLUTION_BASE = '/pm-solution'

export const pmSolutionApi = {
  // 创建新方案会话
  createSession(problemDescription, title = null, knowledgeId = null) {
    return api.post(`${PM_SOLUTION_BASE}/sessions`, {
      problem: problemDescription,
      title: title,
      knowledge_id: knowledgeId
    })
  },

  // 获取会话列表
  getSessions() {
    return api.get(`${PM_SOLUTION_BASE}/sessions`)
  },

  // 获取单个会话详情
  getSession(sessionId) {
    return api.get(`${PM_SOLUTION_BASE}/sessions/${sessionId}`)
  },

  // 更新会话标题
  updateTitle(sessionId, title) {
    return api.patch(`${PM_SOLUTION_BASE}/sessions/${sessionId}/title`, {
      title: title
    })
  },

  // 阶段内对话（SSE流式）
  chatStream(sessionId, userInput) {
    return fetch(`/api/v1${PM_SOLUTION_BASE}/sessions/${sessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_input: userInput }),
    })
  },

  // 获取对话记录（包含sources）
  getChats(sessionId) {
    return api.get(`${PM_SOLUTION_BASE}/sessions/${sessionId}/chats`)
  },

  // 确认当前阶段，推进到下一阶段
  confirm(sessionId) {
    return api.post(`${PM_SOLUTION_BASE}/sessions/${sessionId}/confirm`)
  },

  // 回溯到指定阶段
  rollback(sessionId, targetPhase) {
    return api.post(`${PM_SOLUTION_BASE}/sessions/${sessionId}/rollback`, {
      target_phase: targetPhase
    })
  },

  // 导出PRD
  exportPRD(sessionId) {
    return api.post(`${PM_SOLUTION_BASE}/sessions/${sessionId}/export`)
  },

  // 删除会话
  deleteSession(sessionId) {
    return api.delete(`${PM_SOLUTION_BASE}/sessions/${sessionId}`)
  }
}

export default pmSolutionApi