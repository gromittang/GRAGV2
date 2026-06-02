<template>
  <div class="inline-flex items-center gap-1.5" :title="tooltip">
    <span
      v-for="(stage, i) in stages"
      :key="i"
      class="w-1.5 h-1.5 rounded-full"
      :class="stageColor(stage)"
    ></span>
    <span class="font-mono text-[10px] text-primary/50 ml-0.5">{{ label }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: '0000' },
})

const stages = computed(() => {
  const s = props.status || '0000'
  return [
    { code: s[0] || '0', name: '导入' },
    { code: s[1] || '0', name: '分割' },
    { code: s[2] || '0', name: '向量化' },
    { code: s[3] || '0', name: '分词' },
  ]
})

const label = computed(() => {
  const allDone = stages.value.every(s => s.code === '2')
  const anyFail = stages.value.some(s => s.code === '9')
  if (allDone) return '完成'
  if (anyFail) return '失败'
  const active = stages.value.find(s => s.code === '1')
  if (active) return `${active.name}中`
  return '待处理'
})

const tooltip = computed(() => stages.value.map(s => `${s.name}:${s.code}`).join(' '))

function stageColor(stage) {
  switch (stage.code) {
    case '2': return 'bg-accent-green'
    case '1': return 'bg-amber'
    case '9': return 'bg-red-500'
    default: return 'bg-grid'
  }
}
</script>
