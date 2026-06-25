<template>
  <div class="flex-1 flex flex-col bg-paper overflow-hidden min-h-0">
    <!-- Header -->
    <header class="h-20 hairline-b flex items-center px-12 flex-shrink-0 bg-paper z-40">
      <div class="flex items-center gap-4">
        <h1 class="font-display text-2xl font-bold text-primary tracking-tight">智能助手</h1>
        <span class="w-1 h-1 bg-grid/60 rounded-full"></span>
        <span class="font-mono text-[12px] uppercase text-accent-orange tracking-widest font-bold">Orchestrator</span>
      </div>
    </header>

    <!-- Input Area -->
    <div class="px-12 pt-8 pb-6">
      <div class="max-w-3xl mx-auto">
        <div class="flex gap-3">
          <input
            v-model="question"
            @keydown.enter="send"
            placeholder="输入您的问题，例如：查询最近入库单、SOP操作规范、设计方案..."
            class="flex-1 px-4 py-3 bg-warm-gray border border-grid rounded text-[15px] text-primary placeholder:text-tertiary focus:outline-none focus:border-accent-orange/40 focus:shadow-glow transition-all duration-150 ease-out-expo"
            :disabled="loading"
          />
          <button
            @click="send"
            :disabled="loading || !question.trim()"
            class="px-6 py-3 bg-accent-orange text-white rounded text-[14px] font-semibold hover:bg-accent-orange-hover transition-all duration-150 ease-spring disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98]"
          >发送</button>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="px-12 pb-4">
      <div class="max-w-3xl mx-auto flex items-center gap-3 text-primary/40 text-[14px]">
        <span class="inline-block w-4 h-4 border-2 border-accent-orange/40 border-t-accent-orange rounded-full animate-spin"></span>
        正在分析...
      </div>
    </div>

    <!-- Result -->
    <div v-if="result && !loading" class="flex-1 overflow-y-auto px-12 pb-8">
      <div class="max-w-3xl mx-auto space-y-5">

        <!-- Routing Badge -->
        <div class="flex items-center gap-2 flex-wrap">
          <span class="inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-mono font-bold"
            :class="badgeClass"
          >
            <span class="w-1.5 h-1.5 rounded-full" :class="badgeDotClass"></span>
            {{ intentLabel }}
          </span>
          <span class="text-[11px] text-primary/30 font-mono">
            {{ sourceLabel }} · 置信度 {{ (result.confidence * 100).toFixed(0) }}%
          </span>
        </div>

        <!-- Error -->
        <div v-if="result.error" class="p-4 border border-danger/20 bg-danger-soft rounded text-danger text-[13px]">
          {{ result.error }}
        </div>

        <!-- NL2SQL Result -->
        <template v-if="result.routed_to === 'nl2sql'">
          <div v-if="result.sql" class="space-y-2">
            <div class="text-[11px] font-mono uppercase text-primary/40 tracking-wider">生成的 SQL</div>
            <pre class="p-4 bg-warm-gray border border-grid text-[13px] text-primary/70 font-mono overflow-x-auto whitespace-pre-wrap">{{ result.sql }}</pre>
          </div>
          <div v-if="result.data && result.data.rows" class="space-y-2">
            <div class="text-[11px] font-mono uppercase text-primary/40 tracking-wider">
              查询结果 · {{ result.data.total ?? result.data.rows.length }} 行
            </div>
            <div class="overflow-x-auto border border-grid">
              <table class="w-full text-[12px]">
                <thead>
                  <tr class="bg-warm-gray">
                    <th v-for="col in (result.data.columns || [])" :key="col" class="px-3 py-2 text-left font-mono text-primary/60 whitespace-nowrap">{{ col }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in result.data.rows" :key="i" class="border-t border-grid/50 hover:bg-warm-gray/50">
                    <td v-for="col in (result.data.columns || [])" :key="col" class="px-3 py-1.5 font-mono text-primary/80 whitespace-nowrap">{{ row[col] }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-if="result.insight" class="p-4 bg-warm-gray/50 border border-grid space-y-2">
            <div class="text-[13px] text-primary/80">{{ result.insight.summary }}</div>
            <ul v-if="result.insight.insights" class="space-y-1">
              <li v-for="(item, i) in result.insight.insights" :key="i" class="text-[12px] text-primary/60 flex gap-2">
                <span class="text-accent-orange">→</span> {{ item }}
              </li>
            </ul>
          </div>
        </template>

        <!-- RAG Result -->
        <template v-if="result.routed_to === 'rag'">
          <div v-if="result.answer" class="text-[14px] text-primary/80 leading-relaxed whitespace-pre-wrap">{{ result.answer }}</div>
          <div v-if="result.sources && result.sources.length" class="space-y-2">
            <div class="text-[11px] font-mono uppercase text-primary/40 tracking-wider">参考来源</div>
            <div v-for="(src, i) in result.sources" :key="i" class="p-3 bg-warm-gray/50 border border-grid text-[12px] text-primary/60">
              <div class="font-medium text-primary/80 mb-1">{{ src.document_title || src.title || '来源 ' + (i + 1) }}</div>
              <div class="line-clamp-3">{{ src.content || src.text || '' }}</div>
            </div>
          </div>
        </template>

        <!-- Clarify -->
        <template v-if="result.routed_to === 'none' && result.clarification">
          <div class="p-4 bg-warm-gray/50 border border-grid text-[14px] text-primary/70">
            {{ result.clarification }}
          </div>
        </template>

        <!-- Hybrid result: steps + synthesis -->
        <template v-if="result.routed_to === 'hybrid'">
          <div class="space-y-3">
            <div class="text-[11px] font-mono uppercase text-primary/40 tracking-wider">执行计划</div>

            <div v-for="(s, i) in result.steps" :key="i"
                 class="flex items-start gap-3 p-3 border"
                 :class="s.error ? 'border-red-500/30 bg-red-500/5' : 'border-grid bg-warm-gray/30'">
              <span class="text-[10px] font-mono text-primary/30 mt-0.5 w-4 flex-shrink-0">{{ s.step }}</span>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-0.5">
                  <span class="text-[10px] font-mono font-bold px-1.5 py-0.5"
                        :class="s.intent === 'nl2sql' ? 'bg-accent-orange/10 text-accent-orange' :
                                s.intent === 'rag' ? 'bg-blue-500/10 text-blue-400' :
                                'bg-green-500/10 text-green-400'"
                  >{{ s.intent.toUpperCase() }}</span>
                  <span class="text-[13px] text-primary/80 truncate">{{ s.goal }}</span>
                </div>
                <div v-if="s.error" class="text-[11px] text-red-400 mt-1">{{ s.error }}</div>
                <div v-else class="text-[11px] text-primary/40 mt-0.5">{{ stepSummary(s) }}</div>
              </div>
            </div>

            <div v-if="result.synthesis"
                 class="p-4 border border-accent-orange/20 bg-accent-orange/5 space-y-2">
              <div class="text-[11px] font-mono uppercase text-accent-orange tracking-wider">综合分析结论</div>
              <div class="text-[14px] text-primary/80 leading-relaxed whitespace-pre-wrap">{{ result.synthesis }}</div>
            </div>
          </div>
        </template>

        <!-- PM / Direct -->
        <template v-if="result.routed_to === 'pm' || result.routed_to === 'direct'">
          <div v-if="result.answer" class="text-[14px] text-primary/80">{{ result.answer }}</div>
        </template>

      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!result && !loading" class="flex-1 flex items-center justify-center">
      <div class="text-center space-y-2">
        <div class="text-[48px] opacity-10">&#x2726;</div>
        <div class="text-[14px] text-primary/30">输入问题，智能助手将自动判断意图并路由到对应模块</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { orchestratorChat } from '../api/orchestrator'

const question = ref('')
const loading = ref(false)
const result = ref(null)

const INTENT_LABELS = {
  data_query: '数据查询',
  knowledge_search: '文档检索',
  solution_design: '方案设计',
  hybrid: '跨模块分析',
  clarify: '需要澄清',
  direct_answer: '直接回复',
}

const SOURCE_LABELS = {
  rule: '规则命中',
  llm: 'LLM 分类',
  fallback: '降级路由',
}

const intentLabel = computed(() => INTENT_LABELS[result.value?.intent] || result.value?.intent || '')
const sourceLabel = computed(() => SOURCE_LABELS[result.value?.source] || '')

const badgeClass = computed(() => {
  if (!result.value) return ''
  if (result.value.error) return 'text-red-400 bg-red-500/10 border border-red-500/20'
  if (result.value.source === 'fallback') return 'text-yellow-400 bg-yellow-500/10 border border-yellow-500/20'
  return 'text-accent-orange bg-accent-orange/10 border border-accent-orange/20'
})

const badgeDotClass = computed(() => {
  if (!result.value) return ''
  if (result.value.error) return 'bg-red-400'
  if (result.value.source === 'fallback') return 'bg-yellow-400'
  return 'bg-accent-orange'
})

function stepSummary(s) {
  const r = s.result || {}
  if (s.intent === 'nl2sql') {
    const rows = r.data?.rows?.length ?? r.data?.count ?? r.data?.total
    return rows != null ? `${rows} 行数据` : ''
  }
  if (s.intent === 'rag') {
    const count = r.sources?.length ?? null
    return count != null ? `${count} 条文档` : ''
  }
  return ''
}

async function send() {
  if (!question.value.trim() || loading.value) return
  loading.value = true
  result.value = null
  try {
    const { data } = await orchestratorChat(question.value.trim())
    result.value = data
  } catch (e) {
    result.value = { intent: 'clarify', confidence: 0, source: 'fallback', routed_to: 'none', error: '请求失败：' + (e.message || '未知错误') }
  } finally {
    loading.value = false
  }
}
</script>
