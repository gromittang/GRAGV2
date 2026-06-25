import api from './index'

const PM_SOLUTION_BASE = '/pm-solution'

export const pmSolutionApi = {
  // 创建新方案会话
  // knowledgeId: 知识库ID，空字符串''表示"不限定知识库（检索全部）"，null表示使用默认PM方案知识库
  createSession(problemDescription, title = null, knowledgeId = null) {
    return api.post(`${PM_SOLUTION_BASE}/sessions`, {
      problem: problemDescription,
      title: title,
      knowledge_id: knowledgeId  // 空字符串''会被正确传递
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
  // currentPhase: 用户当前所在的阶段索引(0-3)，用于确定生成下一阶段内容
  chatStream(sessionId, userInput, currentPhase = null) {
    const body = { user_input: userInput }
    if (currentPhase !== null) {
      body.current_phase = currentPhase
    }
    return fetch(`/api/v1${PM_SOLUTION_BASE}/sessions/${sessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  },

  // 获取对话记录（包含sources）
  getChats(sessionId) {
    return api.get(`${PM_SOLUTION_BASE}/sessions/${sessionId}/chats`)
  },

  // 确认当前阶段，推进到下一阶段（SSE流式，LangGraph 会同步生成下一阶段内容）
  confirm(sessionId, userInput = null) {
    const body = {}
    if (userInput) body.user_input = userInput
    return fetch(`/api/v1${PM_SOLUTION_BASE}/sessions/${sessionId}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  },

  // 切换当前显示阶段（纯导航，不影响阶段数据）
  switchStage(sessionId, currentStage) {
    return api.patch(`${PM_SOLUTION_BASE}/sessions/${sessionId}/current-stage`, {
      current_stage: currentStage
    })
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
  },

  // 提交阶段反馈
  submitFeedback(data) {
    return api.post(`${PM_SOLUTION_BASE}/feedback`, data)
  },
  // 获取反馈统计
  getFeedbackStats() {
    return api.get(`${PM_SOLUTION_BASE}/feedback/stats`)
  },
}

export default pmSolutionApi