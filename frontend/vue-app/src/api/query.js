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
}
