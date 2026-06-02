import api from './index'

export default {
  generate(title, data) {
    return api.post('/reports/generate', { title, data }, { responseType: 'blob' })
  },
  generateFromQuery(sql, title) {
    return api.post('/reports/generate-from-query', { sql, title }, { responseType: 'blob' })
  },
  template() {
    return api.get('/reports/template')
  },
}
