<template>
  <div class="h-[36px] border border-grid bg-surface flex items-center justify-between px-3 mb-2">
    <div class="flex items-center gap-2">
      <Icon icon="lucide:file-plus" class="text-accent-orange text-[16px]" />
      <span class="font-mono text-[11px] uppercase tracking-widest text-primary">上传新文档 (PDF, DOCX, TXT, MD)</span>
    </div>
    <label class="cursor-pointer">
      <input
        type="file"
        accept=".pdf,.docx,.txt,.md"
        class="hidden"
        @change="handleFile"
        :disabled="uploading"
        ref="fileInput"
      />
      <span class="font-mono text-[10px] uppercase font-bold text-accent-orange hover:underline">
        {{ uploading ? '处理中...' : 'SELECT FILE' }}
      </span>
    </label>
  </div>
  <!-- Always show progress when uploading -->
  <div v-if="uploading" class="mb-2">
    <ProgressPoll
      v-if="taskId"
      :task-id="taskId"
      @complete="onTaskComplete"
    />
    <!-- Show simple status if no task ID yet -->
    <div v-else class="bg-warm-gray border border-grid p-3">
      <div class="flex items-center gap-2">
        <div class="w-3 h-3 rounded-full bg-amber animate-pulse"></div>
        <span class="font-mono text-[10px] uppercase tracking-widest text-primary/60">上传中...</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Icon } from '@iconify/vue'
import ProgressPoll from './ProgressPoll.vue'

const props = defineProps({
  kbId: { type: String, default: null },
  kbName: { type: String, default: '默认知识库' },
})

const emit = defineEmits(['uploaded'])

const uploading = ref(false)
const taskId = ref('')
const fileInput = ref(null)

async function handleFile(e) {
  const file = e.target.files[0]
  if (!file) return

  // Reset state
  uploading.value = true
  taskId.value = ''

  try {
    const { useKnowledgeStore } = await import('../../stores/knowledge')
    const store = useKnowledgeStore()
    const result = await store.uploadDocument(file, props.kbId, props.kbName)

    // Set task ID for progress polling
    taskId.value = result.task_id || result.data?.task_id || ''

    // If no task ID or already completed, finish immediately
    if (!taskId.value || result.success && !result.task_id) {
      // Wait a short delay then refresh (backend may still be processing)
      setTimeout(() => {
        emit('uploaded', result)
        uploading.value = false
        taskId.value = ''
      }, 500)
    }
  } catch (err) {
    console.error('Upload failed:', err)
    uploading.value = false
    taskId.value = ''
  }

  // Reset file input for next upload
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

function onTaskComplete() {
  emit('uploaded', { task_id: taskId.value })
  uploading.value = false
  taskId.value = ''
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}
</script>
