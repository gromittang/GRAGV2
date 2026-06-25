import api from './index'

export default {
  getRecent(type = 'logs', limit = 50, minutes = 60) {
    return api.get('/logs/recent', { params: { type, limit, minutes } })
  },
  getQueries(limit = 50, minutes = 60) {
    return api.get('/logs/recent', { params: { type: 'queries', limit, minutes } })
  },
}
