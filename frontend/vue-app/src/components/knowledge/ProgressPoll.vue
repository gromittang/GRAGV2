<template>
  <div class="bg-warm-gray border border-grid p-3">
    <div class="flex items-center gap-2 mb-2">
      <div class="w-3 h-3 rounded-full" :class="taskStatus === 'success' ? 'bg-accent-green' : 'bg-amber animate-pulse'"></div>
      <span class="font-mono text-[10px] uppercase tracking-widest text-primary/60">
        {{ taskStatus === 'success' ? '处理完成' : taskStatus === 'failure' ? '处理失败' : '处理中...' }}
      </span>
      <span v-if="taskStatus === 'started'" class="font-mono text-[10px] text-primary/40">{{ taskProgress }}%</span>
    </div>
    <!-- 4-stage progress -->
    <div class="grid grid-cols-4 gap-1">
      <div v-for="(stage, i) in stages" :key="i" class="flex flex-col items-center">
        <div
          class="w-full h-1 mb-1"
          :class="stage.done ? 'bg-accent-green' : stage.active ? 'bg-amber' : 'bg-grid'"
        ></div>
        <span class="font-mono text-[8px] uppercase text-primary/40">{{ stage.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import documentsV2Api from '../../api/documentsV2'

const props = defineProps({
  taskId: { type: String, default: '' },
})

const emit = defineEmits(['complete'])

const taskStatus = ref('pending')
const taskProgress = ref(0)
const taskError = ref('')
let pollTimer = null

const stages = computed(() => {
  const progress = taskProgress.value
  return [
    { label: '导入', done: progress >= 25, active: progress < 25 },
    { label: '分割', done: progress >= 50, active: progress >= 25 && progress < 50 },
    { label: '向量化', done: progress >= 75, active: progress >= 50 && progress < 75 },
    { label: '分词', done: progress >= 100, active: progress >= 75 && progress < 100 },
  ]
})

async function pollTaskStatus() {
  if (!props.taskId) return

  try {
    const res = await documentsV2Api.taskStatus(props.taskId)
    const task = res.data.status || res.data
    taskStatus.value = task.state || 'pending'
    taskProgress.value = task.progress || 0
    taskError.value = task.error || ''

    if (taskStatus.value === 'success' || taskStatus.value === '2') {
      taskStatus.value = 'success'
      taskProgress.value = 100
      stopPolling()
      emit('complete')
    } else if (taskStatus.value === 'failure' || taskStatus.value === '3') {
      taskStatus.value = 'failure'
      stopPolling()
    }
  } catch (e) {
    console.error('Failed to poll task status:', e)
  }
}

function startPolling() {
  stopPolling() // Clear any existing timer
  // Reset status
  taskStatus.value = 'pending'
  taskProgress.value = 0
  taskError.value = ''
  // Start polling immediately, then every 2 seconds
  pollTaskStatus()
  pollTimer = setInterval(pollTaskStatus, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// Watch taskId changes - restart polling when new task starts
watch(() => props.taskId, (newId, oldId) => {
  if (newId && newId !== oldId) {
    startPolling()
  } else if (!newId) {
    stopPolling()
  }
}, { immediate: true })

onMounted(() => {
  if (props.taskId) startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>
