<template>
  <div class="flex items-center justify-center py-6 px-8 bg-warm-gray/30 border-b border-grid">
    <div class="flex items-center">
      <template v-for="(phase, index) in phases" :key="phase.key">
        <!-- 阶段节点 -->
        <div
          class="flex flex-col items-center cursor-pointer"
          :class="canSelect(index) ? 'hover:opacity-80' : ''"
          @click="canSelect(index) && $emit('select-phase', phase.key)"
        >
          <!-- 圆点 -->
          <div
            class="w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all duration-200"
            :class="getNodeClass(index)"
          >
            <Icon v-if="isCompleted(index)" icon="lucide:check" class="text-lg text-white" />
            <Icon v-else-if="isGenerated(index)" icon="lucide:file-text" class="text-base text-blue-600" />
            <span v-else class="font-bold" :class="isCurrent(index) ? 'text-white' : 'text-primary/40'">{{ index + 1 }}</span>
          </div>
          <!-- 标签 -->
          <span
            class="mt-2 text-sm font-medium transition-colors"
            :class="getLabelClass(index)"
          >
            {{ phase.label }}
          </span>
          <!-- 状态描述 -->
          <span class="text-xs mt-0.5" :class="getStatusClass(index)">
            {{ getStatusText(index) }}
          </span>
        </div>
        <!-- 连线 -->
        <div
          v-if="index < phases.length - 1"
          class="w-20 h-0.5 mx-3 transition-colors"
          :class="getLineColor(index)"
        ></div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  phases: { type: Array, default: () => [] },
  currentPhase: { type: String, default: '' },
  phaseStatuses: { type: Object, default: () => {} },
})

defineEmits(['select-phase'])

const currentPhaseIndex = computed(() => {
  return props.phases.findIndex(p => p.key === props.currentPhase)
})

function isCompleted(index) {
  const phaseKey = props.phases[index]?.key
  return props.phaseStatuses[phaseKey] === 'confirmed'
}

function isGenerated(index) {
  const phaseKey = props.phases[index]?.key
  return props.phaseStatuses[phaseKey] === 'generated'
}

function isCurrent(index) {
  return index === currentPhaseIndex.value
}

function canSelect(index) {
  // 已完成或已生成的阶段可以选择（回溯）
  const phaseKey = props.phases[index]?.key
  const status = props.phaseStatuses[phaseKey]
  return status === 'confirmed' || status === 'generated'
}

function getNodeClass(index) {
  if (isCompleted(index)) {
    return 'bg-green-500 border-green-500'
  }
  if (isGenerated(index)) {
    return 'bg-blue-100 border-blue-500'
  }
  if (isCurrent(index)) {
    return 'bg-accent-orange border-accent-orange ring-4 ring-accent-orange/20'
  }
  return 'bg-white border-grid'
}

function getLabelClass(index) {
  if (isCompleted(index)) return 'text-green-600'
  if (isGenerated(index)) return 'text-blue-600'
  if (isCurrent(index)) return 'text-accent-orange font-bold'
  return 'text-primary/40'
}

function getStatusClass(index) {
  if (isCompleted(index)) return 'text-green-500/70'
  if (isGenerated(index)) return 'text-blue-500/70'
  if (isCurrent(index)) return 'text-accent-orange/70'
  return 'text-primary/30'
}

function getLineColor(index) {
  // 当前阶段之前的连线为绿色（已完成）
  if (isCompleted(index)) return 'bg-green-500'
  return 'bg-grid'
}

function getStatusText(index) {
  if (isCompleted(index)) return '已完成'
  if (isGenerated(index)) return '已生成'
  if (isCurrent(index)) return '进行中'
  return ''
}
</script>