<template>
  <div
    class="flex gap-3 message-enter"
    :class="role === 'user' ? 'flex-row-reverse' : ''"
  >
    <!-- Avatar -->
    <div
      class="w-8 h-8 flex-shrink-0 flex items-center justify-center"
      :class="role === 'user' ? 'bg-warm-gray' : 'bg-accent-green/10'"
    >
      <Icon
        :icon="role === 'user' ? 'lucide:user' : 'lucide:bot'"
        class="text-sm"
        :class="role === 'user' ? 'text-primary/60' : 'text-accent-green'"
      />
    </div>

    <!-- Bubble -->
    <div class="max-w-[75%] min-w-0">
      <div
        class="px-4 py-3 text-[14px] leading-relaxed"
        :class="role === 'user'
          ? 'bg-warm-gray text-primary'
          : 'bg-surface border border-grid border-l-[3px] border-l-accent-green text-primary/80'"
      >
        <!-- 用户消息保持纯文本 -->
        <div v-if="role === 'user'" class="whitespace-pre-wrap break-words">{{ content }}</div>
        <!-- AI消息使用MD解析 -->
        <div v-else class="message-md-content prose prose-sm max-w-none" v-html="renderedContent"></div>
      </div>

      <!-- Tool tag -->
      <div v-if="tool" class="mt-1 flex items-center gap-1">
        <span class="font-mono text-[9px] uppercase text-accent-orange bg-accent-orange/5 px-1.5 py-0.5 border border-accent-orange/20">
          {{ tool }}
        </span>
      </div>

      <!-- Source citations -->
      <div v-if="sources && sources.length" class="mt-2">
        <span class="font-mono text-[9px] text-primary/30 uppercase tracking-wider">参考来源</span>
        <div class="mt-1 flex items-center gap-1.5 flex-wrap">
          <button
            v-for="(src, i) in displaySources"
            :key="i"
            @click="openPreview(src.documentId)"
            class="inline-flex items-center gap-1 font-mono text-[10px] text-primary/50 bg-warm-gray px-1.5 py-0.5 border border-grid/50 hover:text-accent-orange hover:border-accent-orange/30 transition-colors cursor-pointer"
            :title="src.fullTitle"
          >
            <Icon icon="lucide:file-text" class="text-[10px]" />
            <span class="truncate max-w-[80px]">{{ src.display }}</span>
          </button>
        </div>
      </div>

      <!-- Source images -->
      <div v-if="sourceImages && sourceImages.length" class="mt-3">
        <span class="font-mono text-[9px] text-primary/30 uppercase tracking-wider">相关图片</span>
        <div class="mt-1 flex flex-wrap gap-2">
          <div
            v-for="(img, i) in sourceImages"
            :key="i"
            class="relative cursor-pointer group"
            @click="openImagePreview(img.url)"
          >
            <img
              :src="getImageUrl(img.url)"
              :alt="img.label"
              class="w-24 h-24 object-cover rounded border border-grid/50 hover:border-accent-orange/50 transition-colors"
            />
            <div class="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors rounded flex items-center justify-center">
              <Icon
                icon="lucide:zoom-in"
                class="text-white opacity-0 group-hover:opacity-100 transition-opacity text-lg"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Feedback (AI messages only) -->
      <div v-if="role === 'assistant' && messageIndex >= 0" class="mt-2">
        <div v-if="feedbackDone" class="text-[10px] text-accent-green font-mono">
          已反馈
        </div>
        <div v-else class="flex items-center gap-2">
          <button
            @click="feedbackRating.helpful = true; feedbackExpanded = true"
            :class="feedbackExpanded && feedbackRating.helpful ? 'border-accent-green/40 text-accent-green bg-accent-green/5' : 'border-grid/50 text-primary/40 hover:border-accent-green/30 hover:text-accent-green'"
            class="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-mono border transition-colors"
          >
            <Icon icon="lucide:thumbs-up" class="text-xs" />
          </button>
          <button
            @click="feedbackRating.helpful = false; feedbackExpanded = true"
            :class="feedbackExpanded && !feedbackRating.helpful ? 'border-danger/20 text-danger bg-danger-soft' : 'border-grid/50 text-primary/40 hover:border-danger/20 hover:text-red-400'"
            class="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-mono border transition-colors"
          >
            <Icon icon="lucide:thumbs-down" class="text-xs" />
          </button>
        </div>

        <!-- Expanded detail -->
        <div v-if="feedbackExpanded && !feedbackDone" class="mt-2 space-y-2 border border-grid p-3 bg-warm-gray/30">
          <div class="flex items-center justify-between">
            <span class="text-[11px] text-primary/60 font-mono">来源准确？</span>
            <button
              @click="feedbackRating.sourceAccurate = !feedbackRating.sourceAccurate"
              :class="feedbackRating.sourceAccurate ? 'bg-accent-green/10 text-accent-green border-accent-green/30' : 'bg-danger-soft text-danger border-danger/20'"
              class="px-2 py-0.5 text-[10px] font-mono border transition-colors"
            >{{ feedbackRating.sourceAccurate ? '是' : '否' }}</button>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-[11px] text-primary/60 font-mono">回答完整？</span>
            <button
              @click="feedbackRating.answerComplete = !feedbackRating.answerComplete"
              :class="feedbackRating.answerComplete ? 'bg-accent-green/10 text-accent-green border-accent-green/30' : 'bg-danger-soft text-danger border-danger/20'"
              class="px-2 py-0.5 text-[10px] font-mono border transition-colors"
            >{{ feedbackRating.answerComplete ? '是' : '否' }}</button>
          </div>
          <textarea
            v-model="feedbackRating.comment"
            placeholder="补充说明（可选）"
            rows="2"
            class="w-full border border-grid p-1.5 text-[11px] font-mono text-primary/60 bg-white resize-none focus:outline-none focus:border-accent-orange/40"
          ></textarea>
          <button
            @click="handleFeedbackSubmit"
            :disabled="feedbackSubmitting"
            class="w-full h-7 border border-accent-orange/40 text-[11px] font-mono text-accent-orange hover:bg-accent-orange hover:text-white transition-colors disabled:opacity-40"
          >{{ feedbackSubmitting ? '提交中...' : '提交评价' }}</button>
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

    <!-- Image Preview Modal -->
    <div
      v-if="imagePreviewVisible"
      class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center"
      @click="imagePreviewVisible = false"
    >
      <img
        :src="imagePreviewUrl"
        class="max-w-[90vw] max-h-[90vh] rounded-lg shadow-2xl"
        @click.stop
      />
      <button
        @click="imagePreviewVisible = false"
        class="absolute top-4 right-4 text-white hover:text-gray-300"
      >
        <Icon icon="lucide:x" class="text-2xl" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Icon } from '@iconify/vue'
import { marked } from 'marked'
import PreviewModal from '../knowledge/PreviewModal.vue'
import documentsV2Api from '../../api/documentsV2'
import { useChatStore } from '../../stores/chat'

marked.setOptions({
  headerIds: false,
  mangle: false
})

const props = defineProps({
  role: { type: String, default: 'assistant' },
  content: { type: String, default: '' },
  tool: { type: String, default: '' },
  sources: { type: Array, default: null },
  messageIndex: { type: Number, default: -1 },
  feedbackSubmitted: { type: Boolean, default: false },
})

const store = useChatStore()

// 预览状态
const previewVisible = ref(false)
const previewDoc = ref(null)

// 图片预览状态
const imagePreviewVisible = ref(false)
const imagePreviewUrl = ref('')

// 反馈状态
const feedbackExpanded = ref(false)
const feedbackSubmitting = ref(false)
const feedbackDone = ref(false)
const feedbackRating = ref({
  helpful: true,
  sourceAccurate: true,
  answerComplete: true,
  comment: '',
})

async function handleFeedbackSubmit() {
  if (props.messageIndex < 0) return
  feedbackSubmitting.value = true
  const ok = await store.submitFeedback(props.messageIndex, {
    helpful: feedbackRating.value.helpful,
    source_accurate: feedbackRating.value.sourceAccurate,
    answer_complete: feedbackRating.value.answerComplete,
    comment: feedbackRating.value.comment,
  })
  feedbackSubmitting.value = false
  if (ok) {
    feedbackDone.value = true
  }
}

// MD解析内容：只对assistant角色的消息进行MD解析
const renderedContent = computed(() => {
  if (!props.content) return ''
  // 只对assistant角色的消息进行MD解析
  if (props.role === 'user') return props.content
  return marked.parse(props.content)
})

// 处理source显示：提取文档名称和document_id
const displaySources = computed(() => {
  if (!props.sources) return []
  return props.sources.map(s => {
    // 如果是字符串，尝试解析
    if (typeof s === 'string') {
      return { display: s, fullTitle: s, documentId: null }
    }
    // 如果是对象，提取文档名和ID
    if (typeof s === 'object') {
      const meta = s.metadata || {}
      const docName = meta.document_name || meta.title || ''
      const docId = meta.document_id || null
      const paraTitle = meta.title || ''

      // 显示格式：文档名 + 段落标题（如果有且不同）
      let display = docName
      if (paraTitle && paraTitle !== docName) {
        display = `${docName} - ${paraTitle.slice(0, 10)}`
      }

      return {
        display: display.slice(0, 25) || `来源${props.sources.indexOf(s) + 1}`,
        fullTitle: display || `来源${props.sources.indexOf(s) + 1}`,
        documentId: docId
      }
    }
    return { display: '', fullTitle: '', documentId: null }
  }).filter(s => s.display).slice(0, 5) // 最多显示5个
})

// 从所有sources中提取图片
const sourceImages = computed(() => {
  if (!props.sources) return []
  const allImages = []
  for (const s of props.sources) {
    if (s.images && Array.isArray(s.images)) {
      allImages.push(...s.images)
    }
  }
  return allImages.slice(0, 10) // 最多显示10张图片
})

// 打开预览
async function openPreview(documentId) {
  if (!documentId) {
    console.log('[ChatMessage] No documentId, cannot preview')
    return
  }

  console.log('[ChatMessage] Opening preview for documentId:', documentId)
  try {
    // 获取文档详情
    const res = await documentsV2Api.detail(documentId)
    console.log('[ChatMessage] Detail response:', res.data)
    previewDoc.value = res.data
    previewVisible.value = true
  } catch (e) {
    console.error('[ChatMessage] 获取文档详情失败:', e)
  }
}

// 获取图片完整URL（处理相对路径）
function getImageUrl(url) {
  if (!url) return ''
  if (url.startsWith('/')) {
    // 相对路径，需要拼接后端地址
    const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8812'
    return baseUrl + url
  }
  return url
}

// 打开图片预览
function openImagePreview(url) {
  imagePreviewUrl.value = getImageUrl(url)
  imagePreviewVisible.value = true
}
</script>

<style scoped>
.message-enter {
  animation: msg-in 300ms ease-out both;
}
@keyframes msg-in {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* MD解析内容样式 */
.message-md-content {
  line-height: 1.7;
}
.message-md-content h1,
.message-md-content h2,
.message-md-content h3 {
  font-weight: 600;
  margin-top: 1em;
  margin-bottom: 0.5em;
}
.message-md-content h3 {
  font-size: 16px;
}
.message-md-content p {
  margin-bottom: 0.8em;
}
.message-md-content ul,
.message-md-content ol {
  margin-left: 1.5em;
  margin-bottom: 0.8em;
}
.message-md-content li {
  margin-bottom: 0.3em;
}
.message-md-content code {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 13px;
}
.message-md-content pre {
  background: #1f2937;
  color: #e5e7eb;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}
.message-md-content pre code {
  background: none;
  padding: 0;
}
.message-md-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.8em 0;
}
.message-md-content th,
.message-md-content td {
  border: 1px solid #d1d5db;
  padding: 8px 12px;
}
.message-md-content th {
  background: #f3f4f6;
  font-weight: 600;
}
.message-md-content blockquote {
  border-left: 3px solid #d1d5db;
  padding-left: 1em;
  color: #64748b;
}
.message-md-content a {
  color: #EA580C;
  text-decoration: underline;
}
.message-md-content img {
  max-width: 100%;
  border-radius: 4px;
}
</style>
