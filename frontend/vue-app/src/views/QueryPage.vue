<template>
  <div class="flex-1 flex flex-col bg-paper overflow-hidden">
    <!-- Header -->
    <header class="h-20 hairline-b flex items-center justify-between px-12 sticky top-0 bg-paper z-40">
      <div class="flex items-center gap-4">
        <h1 class="font-display text-2xl font-bold text-primary tracking-tight">数据查询</h1>
        <span class="w-1 h-1 bg-grid/60 rounded-full"></span>
        <span class="font-mono text-[12px] uppercase text-accent-orange tracking-widest font-bold">NL2SQL</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="flex items-center gap-1.5 font-mono text-[10px] text-primary/40">
          <span class="w-2 h-2" :class="store.connectionOk ? 'bg-accent-green' : store.connectionOk === false ? 'bg-danger' : 'bg-grid'"></span>
          {{ store.connectionOk ? 'MySQL 已连接' : store.connectionOk === false ? 'MySQL 断开' : 'MySQL 未知' }}
        </span>
        <button
          @click="store.testConnection()"
          class="px-3 h-7 border border-grid text-[11px] text-primary/40 hover:text-accent-orange transition-colors font-mono"
        >测试连接</button>
      </div>
    </header>

    <!-- Content: split layout with schema sidebar -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Schema Browser Sidebar -->
      <aside class="w-[220px] border-r border-grid overflow-y-auto bg-warm-gray flex-shrink-0">
        <SchemaBrowser
          :schema="store.schema"
          :connection-ok="store.connectionOk"
          @load-schema="store.fetchSchema()"
          @preview="store.previewTable($event)"
          @open-window="openTableWindow($event)"
        />
        <!-- Preview data for selected table -->
        <div v-if="store.previewData" class="border-t border-grid p-4">
          <div class="flex items-center justify-between mb-3">
            <span class="font-mono text-[11px] font-bold text-primary">{{ store.previewTableName }}</span>
          </div>
          <div class="space-y-1">
            <div
              v-for="(row, i) in (store.previewData.rows || store.previewData.data || []).slice(0, 5)"
              :key="i"
              class="text-[11px] text-primary/60 font-mono"
            >{{ typeof row === 'object' ? JSON.stringify(row).slice(0, 120) : row }}</div>
          </div>
        </div>
        <!-- 查询历史 -->
        <QueryHistory
          :history="store.history"
          @select="store.executeQueryWithInsight($event.question)"
          @clear="store.clearHistoryData()"
        />
      </aside>

      <!-- Main query area -->
      <div class="flex-1 overflow-y-auto">
        <div class="max-w-5xl mx-auto p-8 space-y-5">
          <!-- Query Input (全宽) -->
          <QueryInput :loading="store.loading" @query="store.executeQueryWithInsight($event)" />

          <!-- Error (全宽) -->
          <div v-if="store.error" class="border border-danger/20 bg-danger-soft rounded p-4">
            <p class="text-[13px] text-danger">{{ store.error }}</p>
          </div>

          <!-- SQL Display (全宽) -->
          <SqlDisplay :sql="store.sql" />

          <!-- Bento Grid: 左列(SQL信息+结果表) | 右列(AI洞察) -->
          <div v-if="store.sql || store.hasResults" class="bento-grid">
            <!-- 左列: 导出信息 + 结果表 -->
            <div class="bento-main">
              <div v-if="store.sql && store.hasResults" class="flex items-center justify-between">
                <span class="font-mono text-[11px] text-tertiary">
                  {{ store.totalCount ? '共 ' + store.totalCount.toLocaleString() + ' 条结果' : '' }}
                </span>
                <ExportButton :sql="store.sql" title="查询结果" />
              </div>
              <ResultTable
                :columns="store.columns"
                :results="store.results"
                :total-count="store.totalCount"
              />
            </div>

            <!-- 右列: AI 洞察 -->
            <div class="bento-side">
              <InsightCard
                :insight="store.insight"
                @followUp="store.handleFollowUp($event)"
              />
            </div>
          </div>

          <!-- 查询评价表单 (全宽) -->
          <FeedbackForm />

          <!-- Empty state -->
          <div v-if="!store.loading && !store.hasResults && !store.sql" class="py-20 text-center">
            <Icon icon="lucide:search" class="text-5xl text-grid mb-4 mx-auto" />
            <p class="text-[14px] text-tertiary">使用自然语言查询 WMS 数据库</p>
            <p class="text-[11px] text-tertiary/60 mt-1">仅支持 SELECT 查询，确保数据安全</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 悬浮窗 -->
    <FloatingWindow
      v-for="win in floatingWindows"
      :key="win.id"
      :table-info="win.tableInfo"
      :initial-x="win.x"
      :initial-y="win.y"
      :z-index="win.zIndex"
      @close="closeWindow(win.id)"
      @focus="focusWindow(win.id)"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import { useQueryStore } from '../stores/query'
import QueryInput from '../components/query/QueryInput.vue'
import SqlDisplay from '../components/query/SqlDisplay.vue'
import ResultTable from '../components/query/ResultTable.vue'
import SchemaBrowser from '../components/query/SchemaBrowser.vue'
import ExportButton from '../components/query/ExportButton.vue'
import InsightCard from '../components/query/InsightCard.vue'
import QueryHistory from '../components/query/QueryHistory.vue'
import FloatingWindow from '../components/query/FloatingWindow.vue'
import FeedbackForm from '../components/query/FeedbackForm.vue'
import schemaApi from '../api/schema'

const store = useQueryStore()

// 悬浮窗状态管理
const floatingWindows = ref([])
const maxWindows = 5
const baseOffset = { x: 100, y: 150 }

function openTableWindow(tableName) {
  if (floatingWindows.value.length >= maxWindows) {
    floatingWindows.value.shift()
  }

  const windowCount = floatingWindows.value.length
  const offset = {
    x: baseOffset.x + windowCount * 30,
    y: baseOffset.y + windowCount * 30
  }

  const tables = store.schema?.tables || []
  const tableInfo = tables.find(t => t.name === tableName || t.table_name === tableName) || { name: tableName }

  floatingWindows.value.push({
    id: `${tableName}-${Date.now()}`,
    tableName,
    tableInfo,
    x: offset.x,
    y: offset.y,
    zIndex: 100 + windowCount
  })
}

function closeWindow(windowId) {
  floatingWindows.value = floatingWindows.value.filter(w => w.id !== windowId)
}

function focusWindow(windowId) {
  const maxZ = Math.max(...floatingWindows.value.map(w => w.zIndex))
  const window = floatingWindows.value.find(w => w.id === windowId)
  if (window) {
    window.zIndex = maxZ + 1
  }
}

onMounted(() => {
  store.fetchSchema()
  store.testConnection()
  store.loadHistory()
})
</script>

<style scoped>
.bento-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 16px;
}
.bento-main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  animation: fade-up 600ms cubic-bezier(0.32, 0.72, 0, 1) forwards;
}
.bento-side {
  display: flex;
  flex-direction: column;
  gap: 16px;
  animation: fade-up 600ms cubic-bezier(0.32, 0.72, 0, 1) forwards;
  animation-delay: 120ms;
}
@media (max-width: 1024px) {
  .bento-grid { grid-template-columns: 1fr; }
}
</style>
