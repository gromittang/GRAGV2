import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import queryApi from '../api/query'

export const useQueryStore = defineStore('query', () => {
  const question = ref('')
  const sql = ref('')
  const results = ref([])
  const columns = ref([])
  const totalCount = ref(0)
  const loading = ref(false)
  const schema = ref(null)
  const connectionOk = ref(null)
  const previewData = ref(null)
  const previewTableName = ref('')
  const error = ref('')

  const hasResults = computed(() => results.value.length > 0)

  async function executeQuery(q) {
    question.value = q
    loading.value = true
    error.value = ''
    sql.value = ''
    results.value = []
    columns.value = []
    totalCount.value = 0

    try {
      const res = await queryApi.query(q)
      const data = res.data
      sql.value = data.sql || ''
      if (data.results && data.results.length > 0) {
        columns.value = Object.keys(data.results[0])
        results.value = data.results
        totalCount.value = data.total || data.results.length
      } else if (data.columns) {
        columns.value = data.columns
        results.value = data.rows || data.data || []
        totalCount.value = data.total || results.value.length
      }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '查询失败'
    } finally {
      loading.value = false
    }
  }

  async function executeSql(sqlText) {
    loading.value = true
    error.value = ''
    try {
      const res = await queryApi.execute(sqlText)
      const data = res.data
      sql.value = sqlText
      if (data.columns) {
        columns.value = data.columns
      }
      results.value = data.rows || data.data || []
      totalCount.value = data.total || results.value.length
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '执行失败'
    } finally {
      loading.value = false
    }
  }

  async function fetchSchema() {
    try {
      const res = await queryApi.schema()
      schema.value = res.data
    } catch (e) {
      console.error('Failed to fetch schema:', e)
    }
  }

  async function testConnection() {
    try {
      const res = await queryApi.testConnection()
      connectionOk.value = res.data.ok || res.data.connected || res.data.status === 'ok'
    } catch (e) {
      connectionOk.value = false
    }
  }

  async function previewTable(tableName, limit = 5) {
    try {
      const res = await queryApi.previewTable(tableName, limit)
      previewTableName.value = tableName
      previewData.value = res.data
    } catch (e) {
      console.error('Failed to preview table:', e)
    }
  }

  function clear() {
    question.value = ''
    sql.value = ''
    results.value = []
    columns.value = []
    totalCount.value = 0
    error.value = ''
  }

  return {
    question, sql, results, columns, totalCount, loading,
    schema, connectionOk, previewData, previewTableName, error,
    hasResults,
    executeQuery, executeSql, fetchSchema, testConnection, previewTable, clear,
  }
})
