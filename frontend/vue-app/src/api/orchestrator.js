import api from './index'

export function orchestratorChat(question) {
  return api.post('/orchestrator/chat', { question })
}
