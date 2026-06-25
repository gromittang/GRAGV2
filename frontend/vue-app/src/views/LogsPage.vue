<template>
  <div class="flex-1 flex flex-col bg-paper overflow-hidden">
    <!-- Header -->
    <header class="h-20 hairline-b flex items-center justify-between px-12 sticky top-0 bg-paper z-40">
      <div class="flex items-center gap-4">
        <Icon icon="lucide:scroll-text" class="text-accent-orange text-xl" />
        <h1 class="font-space text-2xl font-bold text-primary tracking-tight">系统日志</h1>
      </div>
      <div class="flex items-center gap-3">
        <label class="flex items-center gap-2 text-[13px] text-primary/60 cursor-pointer select-none">
          <input type="checkbox" v-model="autoRefresh" class="accent-accent-orange" />
          自动刷新 (10s)
        </label>
        <button
          @click="refresh"
          class="flex items-center gap-1.5 px-3 py-1.5 text-[13px] text-primary/60 hover:text-primary hover:bg-warm-gray rounded transition-colors"
        >
          <Icon icon="lucide:refresh-cw" :class="{ 'animate-spin': loading }" class="w-4 h-4" />
          刷新
        </button>
      </div>
    </header>

    <!-- Tab switcher -->
    <div class="flex items-center gap-0 px-12 pt-4 pb-0">
      <button
        v-for="tab in tabs" :key="tab.id"
        @click="activeTab = tab.id"
        :class="[
          'px-4 py-2 text-[13px] font-medium border-b-2 transition-colors',
          activeTab === tab.id
            ? 'border-accent-orange text-primary'
            : 'border-transparent text-primary/40 hover:text-primary/70'
        ]"
      >{{ tab.label }}</button>
      <div class="flex-1 hairline-b"></div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-12 py-4">

      <!-- Logs Tab -->
      <div v-if="activeTab === 'logs'" class="space-y-1">
        <!-- Level filter -->
        <div class="flex items-center gap-2 mb-3">
          <span class="text-[12px] text-primary/40">级别:</span>
          <button
            v-for="lv in logLevels" :key="lv"
            @click="logLevelFilter = lv"
            :class="[
              'px-2 py-0.5 text-[11px] rounded transition-colors',
              logLevelFilter === lv ? 'bg-sidebar text-white' : 'bg-warm-gray text-primary/50 hover:text-primary'
            ]"
          >{{ lv === 'ALL' ? '全部' : lv }}</button>
        </div>

        <!-- Log table -->
        <div v-if="filteredLogs.length === 0" class="text-center py-20 text-[13px] text-primary/30">
          暂无日志，请先发起一次查询
        </div>
        <table v-else class="w-full text-[12px] font-mono">
          <thead>
            <tr class="text-left text-primary/40 border-b border-grid">
              <th class="py-2 pr-4 w-[90px] font-normal">时间</th>
              <th class="py-2 pr-4 w-[70px] font-normal">级别</th>
              <th class="py-2 pr-4 w-[140px] font-normal">模块</th>
              <th class="py-2 font-normal">消息</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(entry, idx) in filteredLogs" :key="idx">
              <tr
                @click="expandedLogIdx === idx ? (expandedLogIdx = null) : (expandedLogIdx = idx)"
                :class="[
                  'cursor-pointer border-b border-grid/50',
                  expandedLogIdx === idx ? 'bg-warm-gray' : 'hover:bg-warm-gray/50'
                ]"
              >
                <td class="py-1.5 pr-4 text-primary/50 whitespace-nowrap">{{ formatTime(entry.timestamp) }}</td>
                <td class="py-1.5 pr-4">
                  <span :class="levelClass(entry.level)" class="font-medium">{{ entry.level }}</span>
                </td>
                <td class="py-1.5 pr-4 text-primary/60 truncate max-w-[140px]">{{ entry.module }}</td>
                <td class="py-1.5 text-primary/80 truncate max-w-[500px]">{{ entry.message }}</td>
              </tr>
              <!-- Expanded detail row -->
              <tr v-if="expandedLogIdx === idx">
                <td colspan="4" class="py-3 px-4 bg-warm-gray/70 border-b border-grid/50">
                  <pre class="text-[11px] text-primary/60 overflow-x-auto max-h-[300px] whitespace-pre-wrap">{{ JSON.stringify(entry, null, 2) }}</pre>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <!-- Traces Tab -->
      <div v-if="activeTab === 'traces'" class="space-y-4">
        <div v-if="traceTrees.length === 0" class="text-center py-20 text-[13px] text-primary/30">
          暂无追踪数据，请先发起一次 RAG 查询
        </div>
        <div v-for="tree in traceTrees" :key="tree.trace_id" class="border border-grid bg-surface">
          <div class="h-8 hairline-b flex items-center px-3 bg-warm-gray gap-2">
            <Icon icon="lucide:git-branch" class="text-accent-green text-sm flex-shrink-0" />
            <span class="font-mono text-[11px] text-primary/60">Trace: {{ tree.trace_id }}</span>
            <span class="text-[10px] text-primary/30">{{ treeTime(tree) }}</span>
            <span class="ml-auto text-[10px] text-primary/30">{{ tree.spans.length }} spans</span>
          </div>
          <div class="p-2">
            <div v-for="span in treeRoots(tree.spans)" :key="span.span_id">
              <TraceSpanNode :span="span" :all-spans="tree.spans" :depth="0" />
            </div>
          </div>
        </div>
      </div>

      <!-- Queries Tab -->
      <div v-if="activeTab === 'queries'" class="space-y-1">
        <div v-if="queries.length === 0" class="text-center py-20 text-[13px] text-primary/30">
          暂无查询记录，请先在数据查询页面发起一次查询
        </div>
        <table v-else class="w-full text-[12px]">
          <thead>
            <tr class="text-left text-primary/40 border-b border-grid">
              <th class="py-2 pr-3 w-[80px] font-normal">时间</th>
              <th class="py-2 pr-3 font-normal">问题</th>
              <th class="py-2 pr-3 w-[90px] font-normal">管线</th>
              <th class="py-2 pr-3 w-[70px] font-normal text-right">耗时</th>
              <th class="py-2 w-[50px] font-normal text-center">结果</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(q, idx) in queries" :key="idx">
              <tr
                @click="expandedQIdx === idx ? (expandedQIdx = null) : (expandedQIdx = idx)"
                :class="[
                  'cursor-pointer border-b border-grid/50',
                  expandedQIdx === idx ? 'bg-warm-gray' : 'hover:bg-warm-gray/50'
                ]"
              >
                <td class="py-1.5 pr-3 text-primary/50 whitespace-nowrap">{{ formatTime(q.created_at) }}</td>
                <td class="py-1.5 pr-3 text-primary/80 truncate max-w-[400px]">{{ q.question }}</td>
                <td class="py-1.5 pr-3">
                  <span :class="pipelineBadgeClass(q.trace?.pipeline?.source)" class="px-1.5 py-0.5 rounded text-[10px] font-medium">
                    {{ pipelineLabel(q.trace?.pipeline?.source) }}
                  </span>
                </td>
                <td class="py-1.5 pr-3 text-primary/50 text-right whitespace-nowrap">
                  {{ fmtLatency(q.trace?.pipeline?.total_latency_ms) }}
                </td>
                <td class="py-1.5 text-center">
                  <span v-if="q.trace?.pipeline?.success === true" class="text-emerald-500">OK</span>
                  <span v-else-if="q.trace?.pipeline?.success === false" class="text-red-500">FAIL</span>
                  <span v-else class="text-primary/30">-</span>
                </td>
              </tr>
              <!-- Expanded detail cards -->
              <tr v-if="expandedQIdx === idx">
                <td colspan="5" class="py-3 px-4 bg-warm-gray/70 border-b border-grid/50">
                  <div class="space-y-3 text-[12px]">

                    <!-- 📊 查询概览 -->
                    <div class="border border-grid/30 bg-surface p-3">
                      <div class="flex items-center gap-2 mb-2">
                        <Icon icon="lucide:bar-chart-3" class="text-accent-orange text-sm" />
                        <span class="font-medium text-primary/80">查询概览</span>
                      </div>
                      <div class="space-y-1 text-primary/60 pl-6">
                        <div v-if="q.trace?.leader_view?.one_liner">
                          <span class="text-primary/80 font-medium">{{ q.trace.leader_view.one_liner }}</span>
                        </div>
                        <div>管线: <span class="text-primary/80">{{ q.trace?.pipeline?.path || '-' }}</span></div>
                        <div>问题: <span class="text-primary/80">{{ q.question }}</span></div>
                        <div>耗时: <span class="text-primary/80">{{ fmtLatency(q.trace?.pipeline?.total_latency_ms) }}</span>
                          · 返回 <span class="text-primary/80">{{ q.result_count ?? q.trace?.pipeline?.total ?? '-' }}</span> 条
                        </div>
                        <div v-if="q.trace?.pipeline?.error_code">
                          错误: <span class="text-red-500">{{ q.trace.pipeline.error_code }}</span>
                          <span v-if="q.trace.pipeline.error_message" class="text-primary/40"> — {{ q.trace.pipeline.error_message }}</span>
                        </div>
                      </div>
                    </div>

                    <!-- 🔧 运维信息 -->
                    <div class="border border-grid/30 bg-surface p-3">
                      <div class="flex items-center gap-2 mb-2">
                        <Icon icon="lucide:settings-2" class="text-accent-blue text-sm" />
                        <span class="font-medium text-primary/80">运维信息</span>
                      </div>
                      <div class="space-y-1 text-primary/60 pl-6">
                        <div>熔断器: <span :class="q.trace?.ops_view?.circuit_breaker?.includes('OPEN') ? 'text-red-500' : 'text-emerald-500'">{{ q.trace?.ops_view?.circuit_breaker || '-' }}</span></div>
                        <div>
                          触发回退:
                          <span v-if="q.trace?.ops_view?.fallback_triggered" class="text-amber-500">是</span>
                          <span v-else class="text-primary/40">否</span>
                          <span v-if="q.trace?.ops_view?.fallback_from" class="text-primary/40">
                            · {{ q.trace.ops_view.fallback_from }} → {{ q.trace.ops_view.fallback_to }}
                            <span v-if="q.trace.ops_view.fallback_reason"> ({{ q.trace.ops_view.fallback_reason }})</span>
                          </span>
                        </div>
                        <div>追踪ID: <span class="font-mono text-[11px] text-primary/40">{{ q.trace?.ops_view?.trace_id || '-' }}</span></div>
                      </div>
                    </div>

                    <!-- 🔬 开发详情 -->
                    <div class="border border-grid/30 bg-surface p-3">
                      <div class="flex items-center gap-2 mb-2">
                        <Icon icon="lucide:code-2" class="text-accent-purple text-sm" />
                        <span class="font-medium text-primary/80">开发详情</span>
                      </div>
                      <div class="space-y-2 text-primary/60 pl-6">

                        <!-- MCP 资格判定 -->
                        <div>
                          <span class="text-primary/40">MCP 资格判定：</span>
                          <span v-if="q.trace?.debug_view?.eligibility?.domain" class="text-primary/80">
                            领域={{ q.trace.debug_view.eligibility.domain }}
                            · 判定={{ q.trace.debug_view.eligibility.eligible ? '通过' : '未通过' }}
                            · 原因={{ q.trace.debug_view.eligibility.reason || '-' }}
                          </span>
                          <span v-else class="text-primary/30">-</span>
                        </div>

                        <!-- LLM Tool 选择 -->
                        <div v-if="q.trace?.debug_view?.mcp_tool_selection?.candidates?.length">
                          <span class="text-primary/40">LLM 工具选择：</span>
                          <span class="text-primary/80">
                            候选=[{{ q.trace.debug_view.mcp_tool_selection.candidates.join(', ') }}]
                            → 选中 <span class="font-medium">{{ q.trace.debug_view.mcp_tool_selection.selected || '-' }}</span>
                          </span>
                          <div v-if="q.trace.debug_view.mcp_tool_selection.reason" class="text-primary/50 text-[11px]">
                            理由：{{ q.trace.debug_view.mcp_tool_selection.reason }}
                          </div>
                          <div v-if="q.trace.debug_view.mcp_tool_selection.confidence != null" class="text-primary/50 text-[11px]">
                            置信度：{{ q.trace.debug_view.mcp_tool_selection.confidence }}
                          </div>
                        </div>

                        <!-- MCP Tool 参数 -->
                        <div v-if="q.trace?.debug_view?.tool_calls?.length">
                          <span class="text-primary/40">MCP 调用参数：</span>
                          <span class="font-mono text-[11px] text-primary/70">{{ JSON.stringify(q.trace.debug_view.tool_calls[0].args) }}</span>
                        </div>

                        <!-- 耗时分解 -->
                        <div v-if="q.trace?.debug_view?.latency_breakdown">
                          <span class="text-primary/40">耗时分解：</span>
                          <span class="text-primary/70">
                            总耗时 {{ fmtLatency(q.trace.debug_view.latency_breakdown.total_ms) }}
                            <span v-if="q.trace.debug_view.latency_breakdown.mcp_graph_ms != null">
                              · MCP 图执行 {{ fmtLatency(q.trace.debug_view.latency_breakdown.mcp_graph_ms) }}
                            </span>
                          </span>
                        </div>

                        <!-- 执行时间线 -->
                        <div v-if="q.trace?.debug_view?.timeline?.length">
                          <span class="text-primary/40">执行链路：</span>
                          <span class="font-mono text-[11px] text-primary/70">
                            {{ q.trace.debug_view.timeline.map(e => e.executor + '(' + (e.success ? 'OK' : 'FAIL') + (e.error_code ? ':' + e.error_code : '') + ')').join(' → ') }}
                          </span>
                        </div>

                        <!-- SQL -->
                        <div>
                          <span class="text-primary/40">SQL：</span>
                          <span v-if="q.trace?.debug_view?.sql" class="font-mono text-[11px] text-primary/70 block mt-1 bg-warm-gray p-1.5 max-h-[120px] overflow-auto">{{ q.trace.debug_view.sql }}</span>
                          <span v-else class="text-primary/30">(预构建查询，无 SQL)</span>
                        </div>

                      </div>
                    </div>

                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Icon } from '@iconify/vue'
import logsApi from '../api/logs'
import TraceSpanNode from '../components/logs/TraceSpanNode.vue'

const activeTab = ref('queries')
const loading = ref(false)
const autoRefresh = ref(false)
const logLevelFilter = ref('ALL')
const expandedLogIdx = ref(null)
const expandedQIdx = ref(null)

const logs = ref([])
const traces = ref([])
const queries = ref([])

const tabs = [
  { id: 'queries', label: '查询追踪' },
  { id: 'logs', label: '应用日志' },
  { id: 'traces', label: '调用追踪' },
]

const logLevels = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR']

const filteredLogs = computed(() => {
  if (logLevelFilter.value === 'ALL') return logs.value
  return logs.value.filter(e => e.level === logLevelFilter.value)
})

// Build trace trees from flat span list
const traceTrees = computed(() => {
  // Group spans by trace_id
  const groups = {}
  for (const span of traces.value) {
    if (!groups[span.trace_id]) groups[span.trace_id] = []
    groups[span.trace_id].push(span)
  }
  return Object.entries(groups).map(([trace_id, spans]) => ({
    trace_id,
    spans,
  }))
})

function treeRoots(spans) {
  const spanIds = new Set(spans.map(s => s.span_id))
  return spans.filter(s => !s.parent_span_id || !spanIds.has(s.parent_span_id))
}

function treeTime(tree) {
  const root = treeRoots(tree.spans)[0]
  return root ? formatTime(root.timestamp) : ''
}

function formatTime(ts) {
  if (!ts) return ''
  // Extract HH:mm:ss from ISO timestamp
  const match = ts.match(/T?(\d{2}:\d{2}:\d{2})/)
  return match ? match[1] : ts.slice(0, 8)
}

function levelClass(level) {
  switch (level) {
    case 'ERROR': return 'text-red-500'
    case 'WARNING': return 'text-amber-500'
    case 'INFO': return 'text-emerald-500'
    case 'DEBUG': return 'text-primary/30'
    default: return 'text-primary/60'
  }
}

function pipelineLabel(source) {
  const map = { mcp: 'MCP', local: '本地', queryagent: '旧版', gateway: '网关' }
  return map[source] || source || '未知'
}

function pipelineBadgeClass(source) {
  switch (source) {
    case 'mcp': return 'bg-emerald-100 text-emerald-700'
    case 'local': return 'bg-slate-100 text-slate-600'
    case 'queryagent': return 'bg-red-100 text-red-600'
    default: return 'bg-warm-gray text-primary/50'
  }
}

function fmtLatency(ms) {
  if (ms == null) return '-'
  if (ms >= 1000) return (ms / 1000).toFixed(1) + 's'
  return Math.round(ms) + 'ms'
}

async function fetchQueries() {
  try {
    const res = await logsApi.getQueries(200, 480)
    queries.value = res.data.entries || []
  } catch (e) {
    console.error('获取查询记录失败:', e)
  }
}

async function fetchLogs() {
  try {
    const res = await logsApi.getRecent('logs', 500, 480)
    logs.value = res.data.entries || []
  } catch (e) {
    console.error('获取日志失败:', e)
  }
}

async function fetchTraces() {
  try {
    const res = await logsApi.getRecent('traces', 500, 480)
    traces.value = res.data.entries || []
  } catch (e) {
    console.error('获取追踪失败:', e)
  }
}

async function refresh() {
  if (loading.value) return
  loading.value = true
  expandedLogIdx.value = null
  try {
    await Promise.all([fetchLogs(), fetchTraces(), fetchQueries()])
  } finally {
    loading.value = false
  }
}

// 自动刷新：仅获取当前 activeTab 数据，且不折叠展开行
async function autoRefreshTick() {
  if (loading.value) return
  loading.value = true
  try {
    if (activeTab.value === 'logs') await fetchLogs()
    else if (activeTab.value === 'traces') await fetchTraces()
    else if (activeTab.value === 'queries') await fetchQueries()
  } finally {
    loading.value = false
  }
}

let _interval = null
watch(autoRefresh, (on) => {
  if (on) {
    _interval = setInterval(autoRefreshTick, 10000)
  } else {
    clearInterval(_interval)
  }
})

onMounted(refresh)
onUnmounted(() => clearInterval(_interval))
</script>

