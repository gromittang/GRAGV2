<template>
  <div class="border border-grid bg-surface">
    <div class="h-10 hairline-b flex items-center justify-between px-4">
      <span class="font-mono text-[10px] uppercase text-tertiary tracking-wider">数据库结构</span>
      <span
        class="w-2 h-2 inline-flex items-center"
        :class="connectionOk === null ? '' : connectionOk ? 'text-accent-green' : 'text-danger'"
        :title="connectionOk ? '已连接' : connectionOk === false ? '连接断开' : '未知'"
      >
        <span class="w-2 h-2 rounded-full" :class="connectionOk === null ? 'bg-grid' : connectionOk ? 'bg-accent-green' : 'bg-danger'"></span>
      </span>
    </div>

    <div v-if="!schema" class="p-6 text-center">
      <button @click="$emit('load-schema')" class="font-mono text-[11px] text-accent-orange hover:underline uppercase">
        加载 Schema
      </button>
    </div>

    <template v-else>
      <div class="p-3 border-b border-grid">
        <input
          v-model="searchQuery"
          placeholder="搜索表名或注释..."
          class="w-full px-3 py-2 border border-grid rounded text-sm focus:border-accent-orange focus:outline-none"
        />
      </div>

      <div class="max-h-[500px] overflow-y-auto">
        <div v-if="filteredTables.length > 0">
          <div
            v-for="table in filteredTables"
            :key="table.name || table.table_name"
            class="border-b border-grid last:border-0"
          >
            <button
              @click="$emit('open-window', table.name || table.table_name)"
              class="w-full h-9 hairline-b flex items-center justify-between px-4 hover:bg-warm-gray transition-colors text-left"
            >
              <span class="font-mono text-[12px] font-bold text-primary">{{ table.name || table.table_name }}</span>
              <Icon icon="lucide:external-link" class="text-xs text-primary/30" />
            </button>
          </div>
        </div>

        <div v-else class="p-4">
          <p class="text-[12px] text-primary/50">无匹配的表</p>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  schema: { type: Object, default: null },
  connectionOk: { type: Boolean, default: null },
})

defineEmits(['load-schema', 'preview', 'open-window'])

const searchQuery = ref('')

const filteredTables = computed(() => {
  if (!searchQuery.value.trim()) return props.schema?.tables || []
  const query = searchQuery.value.toLowerCase()
  return (props.schema?.tables || []).filter(table => {
    const name = (table.name || table.table_name || '').toLowerCase()
    const displayName = (table.display_name || '').toLowerCase()
    return name.includes(query) || displayName.includes(query)
  })
})
</script>
