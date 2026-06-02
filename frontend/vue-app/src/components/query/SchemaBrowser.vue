<template>
  <div class="border border-grid bg-surface">
    <div class="h-10 hairline-b flex items-center justify-between px-4">
      <span class="font-mono text-[10px] uppercase text-primary/40 tracking-wider">Database Schema</span>
      <span
        class="w-2 h-2 inline-flex items-center"
        :class="connectionOk === null ? '' : connectionOk ? 'text-accent-green' : 'text-red-500'"
        :title="connectionOk ? '已连接' : connectionOk === false ? '连接断开' : '未知'"
      >
        <span class="w-2 h-2 rounded-full" :class="connectionOk === null ? 'bg-grid' : connectionOk ? 'bg-accent-green' : 'bg-red-500'"></span>
      </span>
    </div>

    <div v-if="!schema" class="p-6 text-center">
      <button @click="$emit('load-schema')" class="font-mono text-[11px] text-accent-orange hover:underline uppercase">
        加载 Schema
      </button>
    </div>

    <div v-else class="max-h-[500px] overflow-y-auto">
      <div v-if="schema.tables">
        <div
          v-for="table in schema.tables"
          :key="table.name || table.table_name"
          class="border-b border-grid last:border-0"
        >
          <button
            @click="toggleTable(table.name || table.table_name)"
            class="w-full h-9 hairline-b flex items-center justify-between px-4 hover:bg-warm-gray transition-colors text-left"
          >
            <span class="font-mono text-[12px] font-bold text-primary">{{ table.name || table.table_name }}</span>
            <Icon
              icon="lucide:chevron-down"
              class="text-xs text-primary/30 transition-transform"
              :class="expanded.has(table.name || table.table_name) ? 'rotate-180' : ''"
            />
          </button>

          <div v-if="expanded.has(table.name || table.table_name)" class="bg-warm-gray/50 px-4 py-2">
            <div
              v-for="col in (table.columns || table.fields || [])"
              :key="col.name || col.column_name"
              class="flex items-center justify-between py-1.5 text-[12px]"
            >
              <span class="text-primary/70">{{ col.name || col.column_name }}</span>
              <span class="font-mono text-[10px] text-primary/30">{{ col.type || col.data_type }}</span>
            </div>
            <button
              @click="$emit('preview', table.name || table.table_name)"
              class="mt-2 font-mono text-[10px] text-accent-orange hover:underline uppercase"
            >
              预览前5行
            </button>
          </div>
        </div>
      </div>

      <div v-else-if="schema.tables" class="p-4">
        <p class="text-[12px] text-primary/50">Tables: {{ Array.isArray(schema.tables) ? schema.tables.join(', ') : JSON.stringify(schema.tables) }}</p>
      </div>

      <div v-else class="p-4">
        <p class="text-[12px] text-primary/50">Schema 数据格式: {{ Object.keys(schema).join(', ') }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { Icon } from '@iconify/vue'

defineProps({
  schema: { type: Object, default: null },
  connectionOk: { type: Boolean, default: null },
})

defineEmits(['load-schema', 'preview'])

const expanded = reactive(new Set())

function toggleTable(name) {
  if (expanded.has(name)) {
    expanded.delete(name)
  } else {
    expanded.add(name)
  }
}
</script>
