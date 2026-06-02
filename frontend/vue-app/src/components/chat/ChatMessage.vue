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
        <div class="whitespace-pre-wrap break-words">{{ content }}</div>
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
import { ref, computed } from 'vue'
import { Icon } from '@iconify/vue'
import PreviewModal from '../knowledge/PreviewModal.vue'
import documentsV2Api from '../../api/documentsV2'

const props = defineProps({
  role: { type: String, default: 'assistant' },
  content: { type: String, default: '' },
  tool: { type: String, default: '' },
  sources: { type: Array, default: null },
})

// 预览状态
const previewVisible = ref(false)
const previewDoc = ref(null)

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
</script>

<style scoped>
.message-enter {
  animation: msg-in 300ms ease-out both;
}
@keyframes msg-in {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
