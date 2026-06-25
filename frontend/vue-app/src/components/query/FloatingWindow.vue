<template>
  <div
    ref="windowRef"
    class="floating-window"
    :style="{ left: `${x}px`, top: `${y}px`, zIndex }"
    @mousedown="bringToFront"
  >
    <!-- 标题栏（可拖动） -->
    <div
      class="floating-window-header"
      @mousedown="startDrag"
    >
      <span class="font-medium text-primary">{{ tableInfo.display_name || tableInfo.name }}</span>
      <button
        @click.stop="$emit('close')"
        class="text-primary/40 hover:text-primary transition-colors"
      >
        <Icon icon="lucide:x" class="text-lg" />
      </button>
    </div>
    <!-- 内容区 -->
    <div class="floating-window-content">
      <div v-if="loading" class="flex items-center justify-center h-full">
        <span class="text-primary/40">加载中...</span>
      </div>
      <div v-else-if="error" class="text-danger text-sm p-4">{{ error }}</div>
      <div v-else class="overflow-auto">
        <!-- 表描述 -->
        <div v-if="tableInfo.description" class="px-4 py-2 bg-warm-gray text-xs text-primary/60">
          {{ tableInfo.description }}
        </div>
        <!-- 字段列表 -->
        <table class="w-full text-sm">
          <thead class="bg-warm-gray sticky top-0">
            <tr>
              <th class="px-4 py-2 text-left text-primary/70 font-medium">字段名</th>
              <th class="px-4 py-2 text-left text-primary/70 font-medium">类型</th>
              <th class="px-4 py-2 text-left text-primary/70 font-medium">长度</th>
              <th class="px-4 py-2 text-left text-primary/70 font-medium">注释</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="col in columns"
              :key="col.column_name"
              class="border-b border-grid hover:bg-warm-gray/50"
            >
              <td class="px-4 py-2 font-mono text-primary">{{ col.column_name }}</td>
              <td class="px-4 py-2 text-primary/70">{{ col.data_type }}</td>
              <td class="px-4 py-2 text-primary/50">{{ col.data_length || '-' }}</td>
              <td class="px-4 py-2 text-primary/60">{{ col.display_name || col.description || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import schemaApi from '../../api/schema'

const props = defineProps({
  tableInfo: { type: Object, required: true },
  initialX: { type: Number, default: 100 },
  initialY: { type: Number, default: 150 },
  zIndex: { type: Number, default: 100 },
})

const emit = defineEmits(['close', 'focus'])

const windowRef = ref(null)
const x = ref(props.initialX)
const y = ref(props.initialY)
const isDragging = ref(false)
const dragOffset = ref({ x: 0, y: 0 })

const loading = ref(false)
const error = ref('')
const columns = ref([])

onMounted(async () => {
  await loadFields()
})

async function loadFields() {
  loading.value = true
  error.value = ''
  try {
    const res = await schemaApi.getTableFields(props.tableInfo.name)
    columns.value = res.columns || []
  } catch (e) {
    error.value = '获取字段失败'
    console.error('Load fields failed:', e)
  } finally {
    loading.value = false
  }
}

function startDrag(e) {
  isDragging.value = true
  dragOffset.value = {
    x: e.clientX - x.value,
    y: e.clientY - y.value
  }
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
}

function onDrag(e) {
  if (!isDragging.value) return
  x.value = e.clientX - dragOffset.value.x
  y.value = e.clientY - dragOffset.value.y
  // 限制在窗口范围内
  x.value = Math.max(0, Math.min(x.value, window.innerWidth - 400))
  y.value = Math.max(0, Math.min(y.value, window.innerHeight - 320))
}

function stopDrag() {
  isDragging.value = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
}

function bringToFront() {
  emit('focus')
}
</script>

<style scoped>
.floating-window {
  position: fixed;
  width: 400px;
  height: 320px;
  background: white;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.15);
  overflow: hidden;
  user-select: none;
}
.floating-window-header {
  height: 40px;
  background: #F1F5F9;
  cursor: move;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  border-bottom: 1px solid #E2E8F0;
}
.floating-window-content {
  height: 280px;
  overflow: hidden;
}
</style>