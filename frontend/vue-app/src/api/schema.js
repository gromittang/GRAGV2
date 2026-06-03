import http from './index'

const schemaApi = {
  /**
   * 搜索Schema（表名/字段注释）
   */
  searchSchema: (query, limit = 10) => {
    return http.get(`/query/schema/search`, { params: { q: query, limit } })
  },

  /**
   * 获取表字段详情
   */
  getTableFields: (tableName) => {
    return http.get(`/query/schema/table/${tableName}/fields`)
  },
}

export default schemaApi