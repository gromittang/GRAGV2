<template>
  <div class="border-t border-grid rounded">
    <div class="h-10 hairline-b flex items-center justify-between px-4">
      <span class="font-mono text-[10px] uppercase text-primary/40 tracking-wider">查询历史</span>
      <button @click="$emit('clear')"
              class="text-[11px] text-primary/30 hover:text-danger transition-colors">
        清空
      </button>
    </div>

    <div v-if="history.length === 0" class="p-4 text-center text-[12px] text-primary/30">
      暂无历史记录
    </div>

    <div v-else class="max-h-[200px] overflow-y-auto">
      <div v-for="item in history" :key="item.id"
           @click="$emit('select', item)"
           class="p-3 border-b border-grid last:border-0 hover:bg-warm-gray cursor-pointer transition-colors">
        <div class="flex items-center gap-2 mb-1">
          <span class="history-badge" :class="getSourceClass(item)">{{ getSourceLabel(item) }}</span>
          <p class="text-[12px] text-primary truncate flex-1">{{ item.question }}</p>
        </div>
        <div class="flex items-center justify-between text-[10px] text-tertiary">
          <span class="font-mono truncate max-w-[150px]">{{ item.sql?.slice(0, 50) }}...</span>
          <span>{{ formatTime(item.created_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  history: {
    type: Array,
    default: () => []
  }
})

defineEmits(['select', 'clear'])

function formatTime(timeStr) {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  const now = new Date()
  const diff = now - date

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return date.toLocaleDateString()
}

function getSourceLabel(item) {
  try {
    const trace = JSON.parse(item.trace_json || '{}')
    if (trace.source_label?.includes('MCP')) return 'MCP'
    if (trace.source_label?.includes('本地')) return 'SQL'
    return 'SQL'
  } catch { return 'SQL' }
}

function getSourceClass(item) {
  try {
    const trace = JSON.parse(item.trace_json || '{}')
    if (trace.source_label?.includes('MCP')) return 'mcp'
    if (trace.source_label?.includes('本地')) return 'local'
    return 'agent'
  } catch { return 'agent' }
}
</script>

<style scoped>
.history-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 9999px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}
.history-badge.mcp { background: rgba(184,138,68,0.12); color: var(--color-accent-gold); }
.history-badge.local { background: rgba(61,122,110,0.1); color: var(--color-accent-green); }
.history-badge.agent { background: rgba(156,151,146,0.1); color: var(--color-tertiary); }
</style>