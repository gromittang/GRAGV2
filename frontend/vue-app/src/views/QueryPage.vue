<template>
  <div class="flex-1 flex flex-col bg-paper overflow-hidden">
    <!-- Header -->
    <header class="h-20 hairline-b flex items-center justify-between px-12 sticky top-0 bg-paper z-40">
      <div class="flex items-center gap-4">
        <h1 class="font-space text-2xl font-bold text-primary tracking-tight">数据查询</h1>
        <span class="w-1 h-1 bg-grid/60 rounded-full"></span>
        <span class="font-mono text-[12px] uppercase text-accent-orange tracking-widest font-bold">NL2SQL</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="flex items-center gap-1.5 font-mono text-[10px] text-primary/40">
          <span class="w-2 h-2" :class="store.connectionOk ? 'bg-accent-green' : store.connectionOk === false ? 'bg-red-500' : 'bg-grid'"></span>
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
      <aside class="w-[280px] border-r border-grid overflow-y-auto bg-warm-gray/30 flex-shrink-0">
        <SchemaBrowser
          :schema="store.schema"
          :connection-ok="store.connectionOk"
          @load-schema="store.fetchSchema()"
          @preview="store.previewTable($event)"
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
        <div class="max-w-4xl mx-auto p-8 space-y-5">
          <!-- Query Input -->
          <QueryInput :loading="store.loading" @query="store.executeQueryWithInsight($event)" />

          <!-- Error -->
          <div v-if="store.error" class="border border-red-200 bg-red-50 p-4">
            <p class="text-[13px] text-red-600">{{ store.error }}</p>
          </div>

          <!-- SQL Display -->
          <SqlDisplay :sql="store.sql" />

          <!-- Export button -->
          <div v-if="store.sql && store.hasResults" class="flex items-center justify-between">
            <span class="font-mono text-[11px] text-primary/40">
              {{ store.totalCount ? '共 ' + store.totalCount.toLocaleString() + ' 条结果' : '' }}
            </span>
            <ExportButton :sql="store.sql" title="查询结果" />
          </div>

          <!-- Results Table -->
          <ResultTable
            :columns="store.columns"
            :results="store.results"
            :total-count="store.totalCount"
          />

          <!-- AI分析卡片 -->
          <InsightCard
            :insight="store.insight"
            @followUp="store.handleFollowUp($event)"
          />

          <!-- Empty state -->
          <div v-if="!store.loading && !store.hasResults && !store.sql" class="py-20 text-center">
            <Icon icon="lucide:search" class="text-5xl text-grid mb-4 mx-auto" />
            <p class="text-[14px] text-slate-500">使用自然语言查询 WMS 数据库</p>
            <p class="text-[11px] text-slate-400 mt-1">仅支持 SELECT 查询，确保数据安全</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import { useQueryStore } from '../stores/query'
import QueryInput from '../components/query/QueryInput.vue'
import SqlDisplay from '../components/query/SqlDisplay.vue'
import ResultTable from '../components/query/ResultTable.vue'
import SchemaBrowser from '../components/query/SchemaBrowser.vue'
import ExportButton from '../components/query/ExportButton.vue'
import InsightCard from '../components/query/InsightCard.vue'
import QueryHistory from '../components/query/QueryHistory.vue'

const store = useQueryStore()

onMounted(() => {
  store.fetchSchema()
  store.testConnection()
  store.loadHistory()
})
</script>
