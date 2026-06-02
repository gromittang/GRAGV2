import api from './index'

export default {
  // V1 APIs
  upload(file) {
    const form = new FormData()
    form.append('file', file)
    return api.post('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  list() {
    return api.get('/documents/')
  },
  stats() {
    return api.get('/documents/stats')
  },
  batchContent(ids) {
    return api.get('/documents/batch-content', { params: { ids: ids.join(',') } })
  },
  detail(id) {
    return api.get(`/documents/${id}`)
  },
  delete(id) {
    return api.delete(`/documents/${id}`)
  },
  sync() {
    return api.post('/documents/sync')
  },
  clearAll() {
    return api.post('/documents/clear-all')
  },
}
