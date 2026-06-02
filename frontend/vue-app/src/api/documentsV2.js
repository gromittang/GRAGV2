import api from './index'

export default {
  // V2 APIs
  upload(file, knowledgeId = null, knowledgeName = '默认知识库') {
    const form = new FormData()
    form.append('file', file)
    if (knowledgeId) {
      form.append('knowledge_id', knowledgeId)
    } else {
      form.append('knowledge_name', knowledgeName)
    }
    return api.post('/docs/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  list(page = 1, size = 50, params = {}) {
    return api.get(`/docs/list/${page}/${size}`, { params })
  },
  detail(documentId) {
    return api.get(`/docs/detail/${documentId}`)
  },
  delete(documentId) {
    return api.delete(`/docs/${documentId}`)
  },
  batchDelete(idList) {
    return api.put('/docs/batch-delete', { id_list: idList })
  },
  batchRefresh(idList, stateList) {
    return api.put('/docs/batch-refresh', { id_list: idList, state_list: stateList })
  },
  statusPoll(knowledgeId, documentIds) {
    return api.get('/docs/status-poll', { params: { knowledge_id: knowledgeId, document_ids: documentIds } })
  },
  downloadSource(documentId) {
    return api.get(`/docs/download-source/${documentId}`, { responseType: 'blob' })
  },
  taskStatus(taskId) {
    return api.get(`/docs/task-status/${taskId}`)
  },
  // Document content preview
  getParagraphs(documentId) {
    return api.get(`/docs/paragraphs/${documentId}`)
  },
  // Tags
  createTag(key, value, color, knowledgeId) {
    return api.post('/docs/tags', { key, value, color }, { params: { knowledge_id: knowledgeId } })
  },
  addTags(documentIds, tagIds) {
    return api.post('/docs/tags/add', { document_ids: documentIds, tag_ids: tagIds })
  },
  // Knowledge Base
  createKB(name, description = '') {
    return api.post('/docs/knowledge', { name, description })
  },
  listKB() {
    return api.get('/docs/knowledge/list')
  },
  deleteKB(knowledgeId) {
    return api.delete(`/docs/knowledge/${knowledgeId}`)
  },
  clearKB(knowledgeId) {
    return api.post(`/docs/knowledge/${knowledgeId}/clear`)
  },
}
