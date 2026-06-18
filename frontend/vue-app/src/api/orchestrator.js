import api from './index'

export function orchestratorChat(question) {
  // hybrid pipeline: NL2SQL(~30s) + RAG(~10s) + Synthesis(~3s) ≈ 45s
  return api.post('/orchestrator/chat', { question }, { timeout: 120000 })
}
