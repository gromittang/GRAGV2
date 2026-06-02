<template>
  <teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-[100] flex items-center justify-center px-4 animate-modal-in">
      <div class="absolute inset-0 bg-sidebar/40 backdrop-blur-[2px]" @click="$emit('close')"></div>
      <div class="relative bg-surface border border-grid w-full max-w-[720px] max-h-[80vh] flex flex-col overflow-hidden z-[110]">
        <!-- Header -->
        <div class="h-14 hairline-b flex items-center justify-between px-6 bg-warm-gray">
          <div class="flex items-center gap-3">
            <Icon :icon="fileIcon" class="text-accent-orange text-lg" />
            <span class="font-space text-[15px] font-bold text-primary tracking-tight truncate">{{ doc?.name || doc?.filename }}</span>
          </div>
          <button @click="$emit('close')" class="w-8 h-8 flex items-center justify-center text-primary/40 hover:text-accent-orange transition-colors">
            <Icon icon="lucide:x" class="text-xl" />
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-y-auto p-10">
          <div v-if="loading" class="flex items-center justify-center py-20">
            <span class="font-mono text-[12px] text-primary/40">加载中...</span>
          </div>
          <div v-else class="max-w-2xl mx-auto space-y-6">
            <div v-for="(chunk, i) in chunks" :key="i" class="space-y-3">
              <p class="text-[15px] leading-relaxed text-primary/80 whitespace-pre-wrap">{{ renderContent(chunk.content) }}</p>
              <!-- Image rendering -->
              <div v-if="hasImages(chunk.content)" class="border border-grid p-1 bg-warm-gray overflow-hidden">
                <img
                  v-for="(img, j) in extractImages(chunk.content)"
                  :key="j"
                  :src="img.src"
                  :alt="img.alt"
                  class="w-full"
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="h-12 hairline-t px-6 flex items-center justify-between bg-warm-gray">
          <div class="flex gap-8">
            <div class="flex flex-col">
              <span class="font-mono text-[9px] text-primary/30 uppercase tracking-wider">Chunks</span>
              <span class="font-mono text-[12px] font-bold text-accent-green">{{ chunkCount }}</span>
            </div>
            <div class="flex flex-col">
              <span class="font-mono text-[9px] text-primary/30 uppercase tracking-wider">Characters</span>
              <span class="font-mono text-[12px] font-bold text-accent-green">{{ charCount.toLocaleString() }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span class="font-mono text-[10px] text-primary/30 uppercase">Source: {{ fileType }}</span>
            <button @click="$emit('download')" class="font-mono text-[10px] text-accent-orange uppercase hover:underline">下载</button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Icon } from '@iconify/vue'
import documentsApi from '../../api/documents'
import documentsV2Api from '../../api/documentsV2'

const props = defineProps({
  visible: Boolean,
  doc: { type: Object, default: null },
})

defineEmits(['close', 'download'])

const chunks = ref([])
const loading = ref(false)

const fileExt = computed(() => {
  const name = (props.doc?.name || props.doc?.filename || '').toLowerCase()
  if (name.endsWith('.pdf')) return 'PDF'
  if (name.endsWith('.docx')) return 'DOCX'
  if (name.endsWith('.txt')) return 'TXT'
  if (name.endsWith('.md')) return 'MD'
  return 'PDF'
})

const FILE_ICONS = {
  PDF: 'lucide:file-text',
  DOCX: 'lucide:file-text',
  TXT: 'lucide:file-type',
  MD: 'lucide:file-code',
}

const fileIcon = computed(() => FILE_ICONS[fileExt.value] || 'lucide:file')
const fileType = computed(() => fileExt.value)

const chunkCount = computed(() => props.doc?.chunk_count || props.doc?.paragraph_count || chunks.value.length || 0)
const charCount = computed(() => props.doc?.char_length || chunks.value.reduce((s, c) => s + (c.content?.length || 0), 0))

watch([() => props.visible, () => props.doc?.id], async ([v, docId]) => {
  if (v && docId) {
    loading.value = true
    chunks.value = []
    console.log('[PreviewModal] Loading paragraphs for doc:', docId)
    try {
      // Try V2 API first (MySQL paragraphs)
      const res = await documentsV2Api.getParagraphs(docId)
      console.log('[PreviewModal] V2 paragraphs response:', res.data)
      chunks.value = res.data.documents || []
      // If V2 empty, try V1 (ChromaDB)
      if (chunks.value.length === 0) {
        console.log('[PreviewModal] V2 empty, trying V1')
        const v1Res = await documentsApi.batchContent([docId])
        chunks.value = v1Res.data.documents || []
      }
    } catch (e) {
      console.error('[PreviewModal] Failed to load:', e)
      // Fallback to V1
      try {
        const v1Res = await documentsApi.batchContent([docId])
        chunks.value = v1Res.data.documents || []
      } catch (e2) {
        console.error('[PreviewModal] V1 fallback also failed:', e2)
      }
    } finally {
      loading.value = false
    }
  }
}, { immediate: true })

const IMG_RE = /\[IMG\](.*?)\[\/IMG\]/g

function hasImages(content) {
  if (!content) return false
  IMG_RE.lastIndex = 0
  return IMG_RE.test(content)
}

function extractImages(content) {
  if (!content) return []
  IMG_RE.lastIndex = 0
  const images = []
  let m
  while ((m = IMG_RE.exec(content)) !== null) {
    let src = m[1]
    let alt = 'Image'
    if (src.includes('|')) {
      const parts = src.split('|')
      src = parts[0]
      alt = parts[1] || 'Image'
    }
    images.push({ src, alt })
  }
  return images
}

function renderContent(content) {
  if (!content) return ''
  return content.replace(IMG_RE, '')
}
</script>
