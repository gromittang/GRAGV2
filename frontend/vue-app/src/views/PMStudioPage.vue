<template>
  <div class="flex-1 flex flex-col bg-paper overflow-hidden">
    <!-- Header -->
    <header class="h-20 hairline-b flex items-center justify-between px-12 sticky top-0 bg-paper z-40">
      <div class="flex items-center gap-4">
        <h1 class="font-space text-2xl font-bold text-primary tracking-tight">PM方案工作室</h1>
        <span class="w-1 h-1 bg-grid/60 rounded-full"></span>
        <span class="font-mono text-[12px] uppercase text-accent-orange tracking-widest font-bold">4-Phase Workflow</span>
      </div>
      <div class="flex items-center gap-3">
        <button
          @click="showHistory = true"
          class="px-4 py-2 border border-grid text-[13px] font-medium text-primary hover:bg-warm-gray transition-colors inline-flex items-center gap-2"
        >
          <Icon icon="lucide:history" class="text-sm" />
          历史方案
        </button>
        <button
          @click="startNewSession"
          class="px-4 py-2 bg-accent-orange text-white text-[13px] font-medium hover:bg-accent-orange/90 transition-colors inline-flex items-center gap-2"
        >
          <Icon icon="lucide:plus" class="text-sm" />
          新方案
        </button>
      </div>
    </header>

    <!-- Timeline Stepper -->
    <TimelineStepper
      :phases="phases"
      :current-phase="currentPhase"
      :phase-statuses="phaseStatuses"
      @select-phase="rollbackTo"
    />

    <!-- Main Content -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Main Panel -->
      <main class="flex-1 flex flex-col overflow-hidden p-8 max-w-5xl mx-auto">
        <!-- Loading overlay - 现代样式 -->
        <div v-if="loading && !currentOutput" class="absolute inset-0 bg-gradient-to-br from-orange-50/80 via-white/60 to-amber-50/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div class="bg-white/90 rounded-2xl shadow-lg border border-orange-100 p-8 flex flex-col items-center gap-4">
            <!-- 脉冲圆环动画 -->
            <div class="relative w-12 h-12">
              <div class="absolute inset-0 bg-accent-orange/20 rounded-full animate-ping"></div>
              <div class="absolute inset-2 bg-accent-orange/30 rounded-full animate-ping" style="animation-delay: 0.5s"></div>
              <div class="absolute inset-4 bg-accent-orange rounded-full animate-pulse"></div>
            </div>
            <span class="text-primary font-medium">AI正在思考...</span>
            <span class="text-xs text-primary/50 font-mono">正在检索知识库并生成回答</span>
          </div>
        </div>

        <!-- No Session State -->
        <div v-if="!sessionId" class="flex-1 flex items-center justify-center">
          <div class="text-center max-w-md">
            <Icon icon="lucide:file-text" class="text-6xl text-grid mb-4" />
            <h2 class="font-space text-xl font-bold text-primary mb-2">开始你的方案设计</h2>
            <p class="text-grid text-sm mb-6">上传行业资料后，AI将引导你完成问题定义→方案对比→方案细化→PRD生成的完整流程</p>

            <!-- 知识库选择 -->
            <div class="mb-4">
              <label class="block text-xs text-primary/50 mb-1 font-mono">选择知识库（限定检索范围）</label>
              <select
                v-model="selectedKnowledgeId"
                class="w-full p-3 border border-grid rounded bg-white text-primary text-sm focus:border-accent-orange focus:outline-none"
              >
                <option value="">-- 不限定知识库（检索全部）--</option>
                <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
                  {{ kb.name }}
                </option>
              </select>
            </div>

            <!-- 方案标题输入 -->
            <div class="mb-4">
              <input
                v-model="titleInput"
                placeholder="输入方案标题（如：机组排班优化方案）"
                class="w-full p-3 border border-grid rounded bg-white text-primary text-sm focus:border-accent-orange focus:outline-none"
              />
            </div>

            <!-- 问题描述输入 -->
            <textarea
              v-model="problemInput"
              placeholder="描述你的问题场景，例如：某运行系统要增加机组排班优化功能..."
              class="w-full h-32 p-4 border border-grid rounded bg-white text-primary text-sm resize-none focus:border-accent-orange focus:outline-none"
            ></textarea>
            <button
              @click="createSession"
              :disabled="!problemInput.trim() || loading"
              class="mt-4 px-6 py-3 bg-accent-orange text-white font-medium hover:bg-accent-orange/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Icon icon="lucide:sparkles" class="mr-2 inline" />
              开始分析
            </button>
          </div>
        </div>

        <!-- Active Session -->
        <div v-else class="flex-1 flex flex-col overflow-hidden">
          <!-- Phase Content - 加宽显示，自动滚动到底部 -->
          <div class="flex-1 overflow-auto" ref="chatHistoryContainer">
            <div class="max-w-5xl mx-auto px-4">
              <!-- Phase Title with Edit -->
              <div class="mb-4">
                <span class="text-xs font-mono uppercase text-accent-orange tracking-wider">
                  {{ currentPhaseLabel }}
                </span>
                <div class="flex items-center gap-2 mt-1">
                  <h2 v-if="!editingTitle" class="font-space text-lg font-bold text-primary">
                    {{ sessionTitle }}
                  </h2>
                  <input
                    v-else
                    v-model="editedTitle"
                    @blur="saveTitle"
                    @keyup.enter="saveTitle"
                    class="font-space text-lg font-bold text-primary px-2 py-1 border border-accent-orange rounded focus:outline-none"
                    ref="titleInputRef"
                  />
                  <button
                    v-if="!editingTitle"
                    @click="startEditTitle"
                    class="text-grid hover:text-accent-orange transition-colors"
                    title="编辑标题"
                  >
                    <Icon icon="lucide:pencil" class="text-sm" />
                  </button>
                </div>
              </div>

              <!-- Phase Output - 显示对话历史 -->
              <div v-if="currentPhaseChatHistory.length > 0" class="space-y-4 mb-4">
                <div v-for="(chat, idx) in currentPhaseChatHistory" :key="idx">
                  <!-- 用户输入 -->
                  <div v-if="chat.role === 'user'" class="bg-warm-gray border border-grid rounded-lg p-4 mb-2">
                    <div class="flex items-start gap-2">
                      <Icon icon="lucide:user" class="text-accent-orange text-lg mt-1" />
                      <div class="text-sm text-primary">{{ chat.content }}</div>
                    </div>
                  </div>
                  <!-- AI回复 -->
                  <div v-if="chat.role === 'assistant'" class="bg-white border border-grid rounded-lg p-6">
                    <div class="pm-output prose prose-sm max-w-none leading-relaxed" v-html="renderMarkdown(chat.content)"></div>
                  </div>
                </div>
              </div>

              <!-- 当前生成中的内容 -->
              <div v-if="currentOutput && currentPhaseChatHistory.length === 0" class="bg-white border border-grid rounded-lg p-6 mb-4">
                <div class="pm-output prose prose-sm max-w-none leading-relaxed" v-html="renderedOutput"></div>
              </div>

              <!-- 正在生成提示 - 现代脉冲加载效果 -->
              <div v-if="loading && !currentOutput" class="relative overflow-hidden bg-gradient-to-r from-orange-50 to-amber-50 border border-orange-200 rounded-xl p-8 mb-6">
                <!-- 背景动画 -->
                <div class="absolute inset-0 bg-gradient-to-r from-transparent via-orange-100/50 to-transparent animate-shimmer"></div>

                <div class="relative flex flex-col items-center gap-4">
                  <!-- 三点脉冲动画 -->
                  <div class="flex gap-2">
                    <div class="w-3 h-3 bg-accent-orange rounded-full animate-bounce" style="animation-delay: 0ms"></div>
                    <div class="w-3 h-3 bg-accent-orange rounded-full animate-bounce" style="animation-delay: 150ms"></div>
                    <div class="w-3 h-3 bg-accent-orange rounded-full animate-bounce" style="animation-delay: 300ms"></div>
                  </div>

                  <div class="text-primary font-medium flex items-center gap-2">
                    <Icon icon="lucide:sparkles" class="text-accent-orange animate-pulse" />
                    正在生成回答...
                  </div>

                  <div class="text-xs text-primary/50 font-mono">AI正在分析知识库并生成内容</div>
                </div>
              </div>

              <!-- Source Citations -->
              <div v-if="displaySources.length > 0" class="mb-4">
                <span class="font-mono text-[10px] text-primary/40 uppercase tracking-wider">参考来源</span>
                <div class="mt-2 flex items-center gap-2 flex-wrap">
                  <button
                    v-for="(src, i) in displaySources"
                    :key="i"
                    @click="openPreview(src.documentId)"
                    class="inline-flex items-center gap-1.5 font-mono text-[11px] text-primary/50 bg-warm-gray px-2 py-1 border border-grid/50 hover:text-accent-orange hover:border-accent-orange/30 transition-colors cursor-pointer"
                    :title="src.fullTitle"
                  >
                    <Icon icon="lucide:file-text" class="text-xs" />
                    <span class="truncate max-w-[150px]">{{ src.display }}</span>
                    <span v-if="src.chunkCount > 1" class="text-[9px] text-accent-orange/70">×{{ src.chunkCount }}</span>
                  </button>
                </div>
              </div>

              <!-- User Input - 对话框模式，两个按钮 -->
              <div class="bg-warm-gray border border-grid rounded-lg p-4">
                <textarea
                  v-model="userInput"
                  placeholder="输入你的问题或修改意见，点击「对话」继续迭代..."
                  class="w-full h-24 p-3 border border-grid rounded bg-white text-primary text-sm resize-none focus:border-accent-orange focus:outline-none"
                ></textarea>
                <div class="flex justify-between gap-2 mt-3">
                  <!-- 左侧：返回按钮 -->
                  <button
                    v-if="canGoBack"
                    @click="rollbackToPrevPhase"
                    class="px-4 py-2 border border-grid text-sm text-primary hover:bg-white transition-colors"
                  >
                    <Icon icon="lucide:arrow-left" class="mr-1 inline" />
                    返回上一步
                  </button>
                  <div v-else></div>

                  <!-- 右侧：对话和确认按钮 -->
                  <div class="flex gap-2">
                    <button
                      @click="sendChat"
                      :disabled="loading || !userInput.trim()"
                      class="px-4 py-2 border border-accent-orange text-accent-orange text-sm font-medium hover:bg-accent-orange/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      <Icon icon="lucide:message-circle" class="mr-1 inline" />
                      对话
                    </button>
                    <button
                      @click="confirmAndNext"
                      :disabled="loading"
                      class="px-4 py-2 bg-accent-orange text-white text-sm font-medium hover:bg-accent-orange/90 disabled:opacity-50 transition-colors"
                    >
                      <Icon icon="lucide:arrow-right" class="mr-1 inline" />
                      {{ isLastPhase ? '生成PRD' : '确认并进入下一阶段' }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- History Modal -->
    <div v-if="showHistory" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg w-[600px] max-h-[80vh] overflow-hidden">
        <div class="p-4 border-b border-grid flex items-center justify-between">
          <h3 class="font-bold text-primary">历史方案</h3>
          <button @click="showHistory = false" class="text-grid hover:text-primary">
            <Icon icon="lucide:x" />
          </button>
        </div>
        <div class="p-4 overflow-auto max-h-[60vh]">
          <div v-if="historyLoading" class="text-center py-8 text-grid">加载中...</div>
          <div v-else-if="history.length === 0" class="text-center py-8 text-grid">暂无历史方案</div>
          <ul v-else class="space-y-2">
            <li v-for="item in history" :key="item.id"
              class="p-4 border border-grid rounded hover:bg-warm-gray cursor-pointer"
              @click="loadSession(item.id)">
              <div class="flex items-center justify-between">
                <div>
                  <div class="font-medium text-primary">{{ item.title }}</div>
                  <div class="text-xs text-grid mt-1">{{ formatDate(item.created_at) }}</div>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-xs px-2 py-1 bg-accent-orange/10 text-accent-orange rounded">
                    Phase {{ item.current_stage !== undefined ? item.current_stage + 1 : getPhaseNumber(item.current_phase) }}
                  </span>
                  <button
                    @click.stop="deleteSession(item.id)"
                    class="text-grid hover:text-red-500 p-1"
                  >
                    <Icon icon="lucide:trash-2" />
                  </button>
                </div>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Preview Modal -->
    <PreviewModal
      v-if="previewVisible"
      :visible="previewVisible"
      :doc="previewDoc"
      @close="previewVisible = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { Icon } from '@iconify/vue'
import { marked } from 'marked'
import pmSolutionApi from '../api/pmSolution'
import PreviewModal from '../components/knowledge/PreviewModal.vue'
import documentsV2Api from '../api/documentsV2'
import TimelineStepper from '../components/pm/TimelineStepper.vue'

// Phase definitions - matches backend STAGE_TEMPLATES
const phases = [
  { key: 'problem', label: '问题定义' },
  { key: 'analysis', label: '方案分析' },
  { key: 'detail', label: '方案细化' },
  { key: 'prd', label: 'PRD生成' },
]

// 阶段状态数据 - 用于跟踪每个阶段的状态
const phaseStatuses = ref({})  // { problem: 'active', analysis: 'generated', ... }

// State
const problemInput = ref('')
const titleInput = ref('')
const userInput = ref('')
const sessionId = ref(null)
const sessionTitle = ref('')
const currentPhase = ref('problem_definition')
const phaseOutputs = ref({})
const retrievedChunks = ref([])  // 存储检索到的知识库片段
const loading = ref(false)
const showHistory = ref(false)
const history = ref([])
const historyLoading = ref(false)
const editingTitle = ref(false)
const editedTitle = ref('')
const titleInputRef = ref(null)

// 对话历史 - 每个阶段的对话记录
const chatHistory = ref({})

// 知识库选择
const knowledgeBases = ref([])
const selectedKnowledgeId = ref('')

// Preview state
const previewVisible = ref(false)
const previewDoc = ref(null)

// 对话历史容器ref - 用于自动滚动
const chatHistoryContainer = ref(null)

// 自动滚动到底部
function scrollToBottom() {
  nextTick(() => {
    if (chatHistoryContainer.value) {
      chatHistoryContainer.value.scrollTop = chatHistoryContainer.value.scrollHeight
    }
  })
}

// Computed
const currentPhaseIndex = computed(() => {
  return phases.findIndex(p => p.key === currentPhase.value)
})

const currentPhaseLabel = computed(() => {
  const idx = currentPhaseIndex.value
  return idx >= 0 ? phases[idx].label : ''
})

const currentOutput = computed(() => {
  return phaseOutputs.value[currentPhase.value]
})

// 当前阶段的对话历史
const currentPhaseChatHistory = computed(() => {
  return chatHistory.value[currentPhase.value] || []
})

const renderedOutput = computed(() => {
  const output = currentOutput.value
  if (!output) return ''
  return marked.parse(output)
})

const canGoBack = computed(() => currentPhaseIndex.value > 0)

const isLastPhase = computed(() => currentPhaseIndex.value === phases.length - 1)

// Helper: render markdown
function renderMarkdown(text) {
  if (!text) return ''
  return marked.parse(text)
}

// Methods
function isCurrentPhase(index) {
  return index === currentPhaseIndex.value
}

function isCompletedPhase(index) {
  // 已确认的阶段（状态为confirmed）
  const phaseKey = phases[index]?.key
  return phaseStatuses.value[phaseKey] === 'confirmed'
}

function isGeneratedPhase(index) {
  // 已生成内容但未确认的阶段（状态为generated）
  const phaseKey = phases[index]?.key
  return phaseStatuses.value[phaseKey] === 'generated'
}

function getPhaseBadgeClass(index) {
  if (isCompletedPhase(index)) return 'bg-green-100 text-green-600'
  if (isGeneratedPhase(index)) return 'bg-blue-100 text-blue-600'  // 蓝色表示已生成但未确认
  if (isCurrentPhase(index)) return 'bg-accent-orange text-white'
  return 'bg-gray-100 text-gray-400'
}

function getPhaseDescClass(index) {
  if (isCurrentPhase(index)) return 'text-accent-orange/70'
  if (isCompletedPhase(index)) return 'text-green-600/50'
  if (isGeneratedPhase(index)) return 'text-blue-500/50'  // 蓝色
  return 'text-gray-400'
}

function getPhaseDesc(index) {
  const descriptions = ['分析问题背景', '对比多个方案', '展开选定方案', '输出需求文档']
  if (isGeneratedPhase(index)) return '已生成，待确认'
  return descriptions[index]
}

function getProgressText() {
  const completed = Object.values(phaseStatuses.value).filter(s => s === 'confirmed').length
  return `${completed}/${phases.length} 阶段已确认`
}

function canRollback(index) {
  // 可以回溯到：已完成的阶段、已生成的阶段
  const phaseKey = phases[index]?.key
  const status = phaseStatuses.value[phaseKey]
  return (status === 'confirmed' || status === 'generated') && sessionId.value
}

// Title editing functions
function startEditTitle() {
  editedTitle.value = sessionTitle.value
  editingTitle.value = true
  // Focus the input after it renders
  setTimeout(() => {
    if (titleInputRef.value) {
      titleInputRef.value.focus()
    }
  }, 50)
}

async function saveTitle() {
  if (!editedTitle.value.trim() || editedTitle.value === sessionTitle.value) {
    editingTitle.value = false
    return
  }

  try {
    await pmSolutionApi.updateTitle(sessionId.value, editedTitle.value.trim())
    sessionTitle.value = editedTitle.value.trim()
    editingTitle.value = false
  } catch (e) {
    console.error('Update title failed:', e)
    alert('保存标题失败')
    editingTitle.value = false
  }
}

// 获取最新对话的sources
async function fetchLatestSources(sid) {
  try {
    const chatsRes = await pmSolutionApi.getChats(sid)
    const chats = chatsRes.data.chats || []
    const lastAssistantChat = chats.filter(c => c.role === 'assistant').pop()
    if (lastAssistantChat && lastAssistantChat.sources) {
      retrievedChunks.value = lastAssistantChat.sources
    }
  } catch (e) {
    console.error('Fetch sources failed:', e)
  }
}

async function createSession() {
  if (!problemInput.value.trim()) return
  loading.value = true
  retrievedChunks.value = []
  chatHistory.value = {}
  phaseStatuses.value = {}

  try {
    // 1. 创建会话
    const customTitle = titleInput.value.trim() || null
    // 重要：空字符串''表示"不限定知识库"，不要用|| null转换
    const knowledgeId = selectedKnowledgeId.value  // ''表示不限定，null/undefined表示默认
    const res = await pmSolutionApi.createSession(problemInput.value.trim(), customTitle, knowledgeId)
    sessionId.value = res.data.id
    sessionTitle.value = res.data.title
    currentPhase.value = _getPhaseKey(res.data.current_stage)
    phaseStatuses.value[currentPhase.value] = 'active'

    // 初始化对话历史
    chatHistory.value[currentPhase.value] = [{
      role: 'user',
      content: problemInput.value.trim()
    }]

    // 2. 使用SSE流式对话（传入当前阶段索引）
    let assistantContent = ''
    const currentIdx = _getStageIndex(currentPhase.value)
    const streamRes = await pmSolutionApi.chatStream(sessionId.value, problemInput.value.trim(), currentIdx)

    const reader = streamRes.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'token') {
              assistantContent += data.content
              phaseOutputs.value[currentPhase.value] = assistantContent
            } else if (data.type === 'done') {
              // 保存assistant回复到对话历史
              chatHistory.value[currentPhase.value].push({
                role: 'assistant',
                content: assistantContent,
                sources: data.sources || []
              })
              phaseOutputs.value[currentPhase.value] = ''
              // 更新阶段状态为generated（已生成但未确认）
              phaseStatuses.value[currentPhase.value] = 'generated'

              if (!data.sources || data.sources.length === 0) {
                await fetchLatestSources(sessionId.value)
              } else {
                retrievedChunks.value = data.sources
              }
            }
          } catch (e) {
            // Ignore parse errors
          }
        }
      }
    }

    problemInput.value = ''
  } catch (e) {
    console.error('Create session failed:', e)
    alert('创建失败: ' + (e.response?.data?.detail || '请检查后端服务'))
  } finally {
    loading.value = false
  }
}

function _getPhaseKey(stageIndex) {
  return phases[stageIndex]?.key || 'problem'
}

function _getStageIndex(phaseKey) {
  return phases.findIndex(p => p.key === phaseKey)
}

// 对话按钮：发送用户输入，继续在当前阶段迭代
async function sendChat() {
  if (!sessionId.value || !userInput.value.trim()) return
  loading.value = true
  const inputText = userInput.value.trim()
  userInput.value = ''

  // 前端日志
  const startTime = performance.now()
  console.log(`[FRONTEND] ${new Date().toLocaleTimeString()} 开始sendChat, input_len=${inputText.length}`)

  // 保存用户输入到对话历史
  if (!chatHistory.value[currentPhase.value]) {
    chatHistory.value[currentPhase.value] = []
  }
  chatHistory.value[currentPhase.value].push({
    role: 'user',
    content: inputText
  })

  try {
    let assistantContent = ''
    console.log(`[FRONTEND] ${new Date().toLocaleTimeString()} 发送chatStream请求...`)
    const requestTime = performance.now()
    // 传入当前阶段索引
    const currentIdx = _getStageIndex(currentPhase.value)
    const streamRes = await pmSolutionApi.chatStream(sessionId.value, inputText, currentIdx)
    console.log(`[FRONTEND] ${(performance.now()-requestTime).toFixed(0)}ms 收到响应，开始读取流`)

    const reader = streamRes.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let firstTokenTime = null
    let tokenCount = 0
    let chunkCount = 0

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        console.log(`[FRONTEND] ${(performance.now()-startTime).toFixed(0)}ms 流读取完成(done=true)`)
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          chunkCount++
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'status') {
              console.log(`[FRONTEND] ${(performance.now()-startTime).toFixed(0)}ms 收到status: ${data.content}`)
            } else if (data.type === 'token') {
              if (!firstTokenTime) {
                firstTokenTime = performance.now()
                console.log(`[FRONTEND] ${(firstTokenTime-startTime).toFixed(0)}ms 收到第一个token!`)
              }
              tokenCount++
              assistantContent += data.content
              // 实时更新phaseOutputs（用于生成中显示）
              phaseOutputs.value[currentPhase.value] = assistantContent
            } else if (data.type === 'done') {
              console.log(`[FRONTEND] ${(performance.now()-startTime).toFixed(0)}ms 收到done, token_count=${tokenCount}, sources=${data.sources?.length || 0}`)
              // 保存assistant回复到对话历史
              chatHistory.value[currentPhase.value].push({
                role: 'assistant',
                content: assistantContent,
                sources: data.sources || []
              })
              // 清空phaseOutputs（因为历史已保存）
              phaseOutputs.value[currentPhase.value] = ''

              if (!data.sources || data.sources.length === 0) {
                await fetchLatestSources(sessionId.value)
              } else {
                retrievedChunks.value = data.sources
              }
            }
          } catch (e) {
            console.log(`[FRONTEND] 解析chunk失败: ${line.slice(0, 50)}`)
          }
        }
      }
    }

    console.log(`[FRONTEND] ${(performance.now()-startTime).toFixed(0)}ms sendChat完成, total_tokens=${tokenCount}, total_chunks=${chunkCount}`)
  } catch (e) {
    console.error('Chat failed:', e)
    alert('对话失败: ' + (e.response?.data?.detail || '请重试'))
  } finally {
    loading.value = false
  }
}

// 确认并进入下一阶段：确认当前阶段完成，推进
async function confirmAndNext() {
  if (!sessionId.value) return
  loading.value = true
  try {
    // 标记当前阶段为confirmed
    phaseStatuses.value[currentPhase.value] = 'confirmed'

    // 调用确认接口
    const confirmRes = await pmSolutionApi.confirm(sessionId.value)

    const stageOrder = ['problem', 'analysis', 'detail', 'prd']
    const currentIdx = stageOrder.indexOf(confirmRes.data.stage_type)

    // 判断是否已完成所有阶段
    if (currentIdx >= stageOrder.length - 1) {
      // 已完成PRD阶段，导出
      try {
        const exportRes = await pmSolutionApi.exportPRD(sessionId.value)
        downloadMarkdown(exportRes.data.prd_content, exportRes.data.filename)
        alert('PRD文档已生成并下载！')
      } catch (e) {
        console.error('Export failed:', e)
        alert('导出PRD失败')
      }
    } else {
      // 推进到下一阶段
      const nextIdx = currentIdx + 1
      const nextPhaseKey = phases[nextIdx].key
      currentPhase.value = nextPhaseKey
      phaseStatuses.value[nextPhaseKey] = 'active'

      // 初始化下一阶段的对话历史
      chatHistory.value[nextPhaseKey] = []

      // 自动发送初始对话启动下一阶段（传入当前阶段索引，让后端知道我们想生成下一阶段）
      const initPrompt = `请开始${phases[nextIdx].label}阶段的分析`
      chatHistory.value[nextPhaseKey].push({
        role: 'user',
        content: initPrompt
      })

      let assistantContent = ''
      // 传入当前阶段索引（我们已经在nextIdx阶段，想生成这个阶段的内容）
      const streamRes = await pmSolutionApi.chatStream(sessionId.value, initPrompt, nextIdx)

      const reader = streamRes.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.type === 'token') {
                assistantContent += data.content
                phaseOutputs.value[nextPhaseKey] = assistantContent
              } else if (data.type === 'done') {
                // 保存assistant回复
                chatHistory.value[nextPhaseKey].push({
                  role: 'assistant',
                  content: assistantContent,
                  sources: data.sources || []
                })
                phaseOutputs.value[nextPhaseKey] = ''
                retrievedChunks.value = data.sources || []
                // 更新阶段状态为generated
                phaseStatuses.value[nextPhaseKey] = 'generated'
              }
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
      }
    }

    userInput.value = ''
  } catch (e) {
    console.error('Confirm failed:', e)
    alert('操作失败: ' + (e.response?.data?.detail || '请重试'))
  } finally {
    loading.value = false
  }
}

async function confirmStep() {
  if (!sessionId.value) return
  loading.value = true
  try {
    // 1. 调用确认接口，推进阶段
    const confirmRes = await pmSolutionApi.confirm(sessionId.value)

    // 更新当前阶段
    const nextStage = confirmRes.data.stage_type
    const stageOrder = ['problem', 'analysis', 'detail', 'prd']
    const nextIdx = stageOrder.indexOf(nextStage) + 1

    if (nextIdx < phases.length) {
      currentPhase.value = phases[nextIdx].key

      // 2. 如果有用户输入，发送对话
      if (userInput.value.trim()) {
        phaseOutputs.value[currentPhase.value] = ''
        const streamRes = await pmSolutionApi.chatStream(sessionId.value, userInput.value.trim())

        // 解析SSE流
        const reader = streamRes.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                if (data.type === 'token') {
                  phaseOutputs.value[currentPhase.value] += data.content
                } else if (data.type === 'done') {
                  retrievedChunks.value = data.sources || []
                }
              } catch (e) {
                // Ignore parse errors
              }
            }
          }
        }
      }
    } else {
      // 已完成所有阶段，导出PRD
      try {
        const exportRes = await pmSolutionApi.exportPRD(sessionId.value)
        downloadMarkdown(exportRes.data.prd_content, exportRes.data.filename)
      } catch (e) {
        console.error('Export failed:', e)
      }
    }

    userInput.value = ''
  } catch (e) {
    console.error('Confirm failed:', e)
    alert('操作失败: ' + (e.response?.data?.detail || '请重试'))
  } finally {
    loading.value = false
  }
}

async function rollbackTo(targetPhase) {
  if (!sessionId.value) return

  // 如果目标阶段已有对话历史，直接切换显示（不重新生成）
  if (chatHistory.value[targetPhase] && chatHistory.value[targetPhase].length > 0) {
    currentPhase.value = targetPhase
    phaseStatuses.value[targetPhase] = 'active'
    // 从历史中获取sources
    const lastAssistant = chatHistory.value[targetPhase].filter(c => c.role === 'assistant').pop()
    retrievedChunks.value = lastAssistant?.sources || []
    return
  }

  // 目标阶段没有历史，需要加载
  loading.value = true
  try {
    const targetIdx = _getStageIndex(targetPhase)

    // 调用rollback API
    const res = await pmSolutionApi.rollback(sessionId.value, targetIdx)
    currentPhase.value = targetPhase
    phaseStatuses.value[targetPhase] = 'active'

    // 从API加载对话历史
    const chatsRes = await pmSolutionApi.getChats(sessionId.value)
    const allChats = chatsRes.data.chats || []

    if (allChats.length > 0) {
      // 加载到chatHistory
      chatHistory.value[targetPhase] = allChats.map(c => ({
        role: c.role,
        content: c.content,
        sources: c.sources || []
      }))
      const lastAssistant = allChats.filter(c => c.role === 'assistant').pop()
      retrievedChunks.value = lastAssistant?.sources || []
      // 如果有历史，标记为generated
      if (allChats.some(c => c.role === 'assistant')) {
        phaseStatuses.value[targetPhase] = 'generated'
      }
    } else {
      // 没有历史，需要生成
      chatHistory.value[targetPhase] = [{
        role: 'user',
        content: '请继续分析此阶段'
      }]

      let assistantContent = ''
      // 传入当前阶段索引
      const streamRes = await pmSolutionApi.chatStream(sessionId.value, '请继续分析此阶段', targetIdx)

      const reader = streamRes.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.type === 'token') {
                assistantContent += data.content
                phaseOutputs.value[targetPhase] = assistantContent
              } else if (data.type === 'done') {
                chatHistory.value[targetPhase].push({
                  role: 'assistant',
                  content: assistantContent,
                  sources: data.sources || []
                })
                phaseOutputs.value[targetPhase] = ''
                retrievedChunks.value = data.sources || []
                phaseStatuses.value[targetPhase] = 'generated'
              }
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
      }
    }

  } catch (e) {
    console.error('Rollback failed:', e)
    alert('回溯失败')
  } finally {
    loading.value = false
  }
}

function rollbackToPrevPhase() {
  const prevIdx = currentPhaseIndex.value - 1
  if (prevIdx >= 0) {
    rollbackTo(phases[prevIdx].key)
  }
}

async function loadSession(sid) {
  loading.value = true
  try {
    const res = await pmSolutionApi.getSession(sid)
    sessionId.value = res.data.id
    sessionTitle.value = res.data.title
    currentPhase.value = _getPhaseKey(res.data.current_stage)

    // 恢复阶段状态
    phaseStatuses.value = {}
    for (const stage of res.data.stages) {
      phaseStatuses.value[stage.type] = stage.status
    }
    // 当前阶段设为active
    phaseStatuses.value[currentPhase.value] = 'active'

    // 加载阶段输出（用于confirmed阶段的摘要）
    phaseOutputs.value = {}
    for (const stage of res.data.stages) {
      if (stage.status === 'confirmed' && stage.output_summary) {
        phaseOutputs.value[stage.type] = stage.output_summary
      }
    }

    // 获取对话记录（包含sources和stage_type）
    try {
      const chatsRes = await pmSolutionApi.getChats(sid)
      const chats = chatsRes.data.chats || []

      // 按stage_type分组对话历史
      chatHistory.value = {}
      for (const chat of chats) {
        const stageType = chat.stage_type || 'problem'
        if (!chatHistory.value[stageType]) {
          chatHistory.value[stageType] = []
        }
        chatHistory.value[stageType].push({
          role: chat.role,
          content: chat.content,
          sources: chat.sources || []
        })
      }

      // 对于有对话但状态不是confirmed的阶段，设置为generated
      for (const phaseKey of phases.map(p => p.key)) {
        if (chatHistory.value[phaseKey] && chatHistory.value[phaseKey].some(c => c.role === 'assistant')) {
          if (phaseStatuses.value[phaseKey] !== 'confirmed') {
            phaseStatuses.value[phaseKey] = 'generated'
          }
        }
      }

      // 从当前阶段获取最新sources
      const currentPhaseHistory = chatHistory.value[currentPhase.value] || []
      const lastAssistant = currentPhaseHistory.filter(c => c.role === 'assistant').pop()
      retrievedChunks.value = lastAssistant?.sources || []

      // 滚动到对话历史底部
      scrollToBottom()

    } catch (e) {
      console.error('Load chats failed:', e)
      retrievedChunks.value = []
      chatHistory.value = {}
    }

    showHistory.value = false
  } catch (e) {
    console.error('Load session failed:', e)
    alert('加载失败: ' + (e.message || '请重试'))
  } finally {
    loading.value = false
  }
}

async function deleteSession(sid) {
  if (!confirm('确定删除此方案？')) return
  try {
    await pmSolutionApi.deleteSession(sid)
    history.value = history.value.filter(h => h.id !== sid)
    if (sessionId.value === sid) {
      startNewSession()
    }
  } catch (e) {
    console.error('Delete failed:', e)
  }
}

function startNewSession() {
  sessionId.value = null
  sessionTitle.value = ''
  currentPhase.value = 'problem'
  phaseOutputs.value = {}
  phaseStatuses.value = {}
  retrievedChunks.value = []
  problemInput.value = ''
  titleInput.value = ''
  userInput.value = ''
  editingTitle.value = false
  chatHistory.value = {}
}

async function fetchHistory() {
  historyLoading.value = true
  try {
    const res = await pmSolutionApi.getSessions()
    history.value = res.data.sessions || []
  } catch (e) {
    console.error('Fetch history failed:', e)
  } finally {
    historyLoading.value = false
  }
}

async function fetchKnowledgeBases() {
  try {
    const res = await documentsV2Api.listKB()
    knowledgeBases.value = res.data.knowledge_list || []
  } catch (e) {
    console.error('Fetch knowledge bases failed:', e)
  }
}

function getPhaseNumber(phaseKey) {
  const idx = phases.findIndex(p => p.key === phaseKey)
  return idx >= 0 ? idx + 1 : 4
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function formatOutput(output) {
  if (!output) return ''
  if (typeof output === 'string') return output
  if (output.raw) return output.raw
  return JSON.stringify(output, null, 2)
}

function downloadMarkdown(content, filename) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// 打开文档预览
async function openPreview(documentId) {
  if (!documentId) return
  try {
    const res = await documentsV2Api.detail(documentId)
    previewDoc.value = res.data
    previewVisible.value = true
  } catch (e) {
    console.error('获取文档详情失败:', e)
  }
}

// 处理来源显示 - 按文档去重
const displaySources = computed(() => {
  if (!retrievedChunks.value || retrievedChunks.value.length === 0) return []

  // 按文档ID去重，只显示不同文档
  const seenDocIds = new Set()
  const uniqueDocs = []

  for (const src of retrievedChunks.value) {
    const docId = src.metadata?.document_id
    if (docId && !seenDocIds.has(docId)) {
      seenDocIds.add(docId)
      uniqueDocs.push({
        documentId: docId,
        display: src.metadata?.document_name?.slice(0, 30) || '未知文档',
        fullTitle: src.metadata?.document_name || '未知文档',
        score: src.score,
        chunkCount: retrievedChunks.value.filter(c => c.metadata?.document_id === docId).length
      })
    }
  }

  return uniqueDocs.slice(0, 5)
})

// Watch history modal
watch(showHistory, (val) => {
  if (val) fetchHistory()
})

// Watch currentPhaseChatHistory - 当对话历史更新时自动滚动到底部
watch(currentPhaseChatHistory, () => {
  scrollToBottom()
}, { deep: true })

// Mounted
onMounted(() => {
  fetchHistory()
  fetchKnowledgeBases()
})
</script>

<style scoped>
/* PM输出内容样式改善 */
.pm-output {
  line-height: 1.8;
  font-size: 14px;
}

.pm-output h3,
.pm-output h4 {
  font-weight: 600;
  font-size: 16px;
  margin-top: 1.5em;
  margin-bottom: 0.8em;
  color: #1a1a1a;
  border-bottom: 1px solid #e5e5e5;
  padding-bottom: 0.3em;
}

.pm-output h4 {
  font-size: 15px;
  color: #333;
  border-bottom: none;
}

.pm-output p {
  margin-bottom: 1em;
  color: #374151;
}

.pm-output ul,
.pm-output ol {
  margin-left: 1.5em;
  margin-bottom: 1em;
}

.pm-output li {
  margin-bottom: 0.5em;
  line-height: 1.6;
}

.pm-output strong {
  font-weight: 600;
  color: #1f2937;
}

/* 表格样式 - 自适应宽度，合理分配空间 */
.pm-output table {
  width: 100%;
  border-collapse: collapse;
  margin: 1em 0;
  font-size: 13px;
  table-layout: auto;
}

.pm-output th,
.pm-output td {
  border: 1px solid #d1d5db;
  padding: 0.75em 1.2em;
  text-align: left;
  line-height: 1.6;
  min-width: 80px;
}

.pm-output th {
  background: #f3f4f6;
  font-weight: 600;
  color: #1f2937;
  border-bottom: 2px solid #9ca3af;
  white-space: nowrap;
}

.pm-output td {
  background: #fff;
  word-break: break-word;
}

/* 第一列加宽 */
.pm-output td:first-child,
.pm-output th:first-child {
  min-width: 150px;
  font-weight: 500;
  background: #fafafa;
}

.pm-output tr:nth-child(even) td {
  background: #f9fafb;
}

.pm-output tr:hover td {
  background: #fef3c7;
}

.pm-output hr {
  border: none;
  border-top: 2px solid #e5e7eb;
  margin: 2em 0;
}

/* 阶段标题样式 */
.pm-output h3:first-child {
  margin-top: 0;
}

/* 内联代码和代码块 */
.pm-output code {
  background: #f3f4f6;
  padding: 0.2em 0.4em;
  border-radius: 3px;
  font-size: 13px;
}

.pm-output pre {
  background: #1f2937;
  color: #e5e7eb;
  padding: 1em;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
}

.pm-output pre code {
  background: none;
  padding: 0;
}

/* 用户对话框样式 */
.pm-output-user {
  background: #f5f5f4;
  border-radius: 8px;
  padding: 12px 16px;
}

/* 背景闪光动画 */
.animate-shimmer {
  animation: shimmer 2s infinite;
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
</style>