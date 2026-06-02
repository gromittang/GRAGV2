<template>
  <div
    class="grid grid-cols-[40px_1fr_120px_100px] h-[44px] items-center px-4 hairline-b transition-colors group"
    :class="even ? 'bg-slate-50/50' : 'bg-surface'"
  >
    <!-- Checkbox -->
    <div class="flex items-center">
      <input
        type="checkbox"
        :checked="selected"
        @change="$emit('toggle')"
        class="w-4 h-4 border-grid accent-accent-orange"
      />
    </div>

    <!-- Col 1: File name + meta -->
    <div class="flex flex-col justify-center overflow-hidden" @click="$emit('preview')" style="cursor: pointer;">
      <div class="flex items-center gap-2">
        <Icon :icon="fileIcon" class="text-[16px] flex-shrink-0" :style="{ color: fileColor }" />
        <span class="text-[14px] font-bold text-primary truncate">{{ doc.name || doc.filename }}</span>
        <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" :class="statusDotClass" :title="statusTitle"></span>
      </div>
      <span class="font-mono text-[10px] text-primary/30 uppercase">
        {{ formatDate(doc.created_at || doc.upload_time) }} · {{ formatSize(doc.file_size || (doc.file && doc.file.file_size)) }}
      </span>
    </div>

    <!-- Col 2: Stats -->
    <div class="flex flex-col items-center justify-center border-x border-grid/10 h-full">
      <span class="font-mono text-[12px] text-primary/70 leading-none mb-1 font-medium">
        {{ chunkCount }} CHUNKS
      </span>
      <span class="font-mono text-[10px] text-primary/40 leading-none">
        {{ formatNumber(doc.char_length || 0) }} CHARS
      </span>
    </div>

    <!-- Col 3: Actions -->
    <div class="flex justify-end items-center gap-1.5">
      <button
        @click="$emit('preview')"
        class="w-8 h-8 flex items-center justify-center hover:bg-warm-gray border border-transparent hover:border-grid transition-all"
        title="预览"
      >
        <Icon icon="lucide:eye" class="text-[16px] text-primary" />
      </button>
      <button
        @click="$emit('download')"
        class="w-8 h-8 flex items-center justify-center hover:bg-warm-gray border border-transparent hover:border-grid transition-all"
        title="下载"
      >
        <Icon icon="lucide:download" class="text-[16px] text-primary/60" />
      </button>
      <button
        @click="$emit('delete')"
        class="w-8 h-8 flex items-center justify-center hover:bg-red-50 border border-transparent hover:border-red-200 transition-all group/del"
        title="删除"
      >
        <Icon icon="lucide:trash-2" class="text-[16px] text-accent-orange opacity-60 group-hover/del:opacity-100" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  doc: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  even: { type: Boolean, default: false },
})

defineEmits(['toggle', 'preview', 'delete', 'download'])

// File type icon & color
const FILE_TYPES = {
  pdf: { icon: 'lucide:file-text', color: '#EA580C' },
  docx: { icon: 'lucide:file-text', color: '#2563EB' },
  doc: { icon: 'lucide:file-text', color: '#2563EB' },
  txt: { icon: 'lucide:file-type', color: '#64748B' },
  md: { icon: 'lucide:file-code', color: '#7C3AED' },
}

const fileExt = computed(() => {
  const name = (props.doc.name || props.doc.filename || '').toLowerCase()
  if (name.endsWith('.pdf')) return 'pdf'
  if (name.endsWith('.docx')) return 'docx'
  if (name.endsWith('.doc')) return 'doc'
  if (name.endsWith('.txt')) return 'txt'
  if (name.endsWith('.md')) return 'md'
  return 'txt'
})

const fileIcon = computed(() => FILE_TYPES[fileExt.value]?.icon || 'lucide:file')
const fileColor = computed(() => FILE_TYPES[fileExt.value]?.color || '#64748B')

const chunkCount = computed(() => props.doc.chunk_count || props.doc.paragraph_count || 0)

// Status dot
const statusDotClass = computed(() => {
  const s = props.doc.status || ''
  if (s.startsWith('2') || s === 'ready' || s === 'indexed') return 'bg-accent-green'
  if (s.startsWith('1') || s.startsWith('0')) return 'bg-amber'
  if (s.startsWith('9')) return 'bg-red-500'
  return 'bg-grid'
})
const statusTitle = computed(() => {
  const s = props.doc.status || ''
  if (s.startsWith('2') || s === 'ready' || s === 'indexed') return '已完成'
  if (s.startsWith('1')) return '处理中'
  if (s.startsWith('0')) return '待处理'
  if (s.startsWith('9')) return '失败'
  return '未知'
})

function formatDate(d) {
  if (!d) return '--'
  return d.slice(0, 10)
}

function formatSize(bytes) {
  if (!bytes && bytes !== 0) return '--'
  bytes = Number(bytes)
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + 'MB'
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return bytes + 'B'
}

function formatNumber(n) {
  n = Number(n)
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}
</script>
