<template>
  <div v-if="sql" class="bg-[#1E2127] rounded shadow-sm overflow-hidden">
    <div class="flex items-center justify-between px-4 py-2 border-b border-white/6">
      <span class="font-mono text-[10px] font-medium text-white/35 uppercase tracking-wider">Generated SQL</span>
      <button @click="copySql"
        class="px-[10px] py-[3px] border border-white/8 bg-transparent text-white/50 rounded-sm text-[10px] hover:bg-white/6 hover:text-white/80 transition-all font-mono cursor-pointer">
        {{ copied ? '已复制' : '复制' }}
      </button>
    </div>
    <pre class="px-5 py-4 text-[12.5px] leading-relaxed overflow-x-auto whitespace-pre-wrap"
         v-html="highlightedSql"></pre>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ sql: { type: String, default: '' } })
const copied = ref(false)

const SQL_KEYWORDS = [
  'SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER', 'ON',
  'GROUP', 'BY', 'ORDER', 'HAVING', 'LIMIT', 'OFFSET', 'UNION', 'AS',
  'INSERT', 'INTO', 'UPDATE', 'DELETE', 'SET', 'VALUES',
  'AND', 'OR', 'NOT', 'IN', 'LIKE', 'BETWEEN', 'IS', 'NULL',
  'DISTINCT', 'COUNT', 'SUM', 'AVG', 'MAX', 'MIN', 'ROUND',
  'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
  'ASC', 'DESC', 'INTERVAL', 'NOW', 'DATE_SUB', 'DATE_ADD',
  'CREATE', 'TABLE', 'INDEX', 'ALTER', 'DROP', 'PRIMARY', 'KEY',
]

const highlightedSql = computed(() => {
  if (!props.sql) return ''
  let html = escapeHtml(props.sql)

  // Step 1: 字符串字面量 (绿色)
  html = html.replace(/'[^']*'/g, '<span class="sql-string">$&</span>')

  // Step 2: 数字 (金色)
  html = html.replace(/\b(\d+\.?\d*)\b/g, '<span class="sql-number">$1</span>')

  // Step 3: SQL 关键字 (橙色)
  SQL_KEYWORDS.forEach(kw => {
    const regex = new RegExp(`\\b${kw}\\b`, 'gi')
    html = html.replace(regex, (match) => `<span class="sql-keyword">${match}</span>`)
  })

  return html
})

function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function copySql() {
  navigator.clipboard.writeText(props.sql)
  copied.value = true
  setTimeout(() => copied.value = false, 2000)
}
</script>

<style scoped>
.sql-keyword { color: #E8935A; }
.sql-string  { color: #8CB89F; }
.sql-number  { color: #C8A87C; }
</style>
