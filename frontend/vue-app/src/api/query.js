import api from './index'

export default {
  query(question) {
    return api.post('/query/', { question })
  },
  execute(sql) {
    return api.post('/query/execute', { sql })
  },
  schema() {
    return api.get('/query/schema')
  },
  testConnection() {
    return api.get('/query/test-connection')
  },
  previewTable(tableName, limit = 5) {
    return api.get(`/query/preview/${tableName}`, { params: { limit } })
  },

  getInsight(question, sql, results) {
    return api.post('/query/insight', { question, sql, results })
  },

  getHistory(sessionId) {
    return api.get(`/query/history/${sessionId}`)
  },

  getAllHistory(limit = 20) {
    return api.get('/query/history/all', { params: { limit } })
  },

  saveHistory(sessionId, item) {
    return api.post(`/query/history/${sessionId}`, item)
  },

  clearHistory(sessionId) {
    return api.delete(`/query/history/${sessionId}`)
  },
}
