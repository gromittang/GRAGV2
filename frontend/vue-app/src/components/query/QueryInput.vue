<template>
  <div class="bg-surface border border-grid rounded-lg shadow-raised overflow-hidden transition-shadow duration-250 ease-out-expo"
       :class="{ 'border-accent-orange/25 shadow-glow': isFocused }">
    <!-- Header -->
    <div class="flex items-center gap-3 px-5 py-4 border-b border-grid bg-warm-gray">
      <div class="w-2 h-2 rounded-full bg-accent-orange"></div>
      <span class="font-mono text-[10px] font-semibold text-secondary uppercase tracking-wider">自然语言查询</span>
    </div>
    <!-- Body -->
    <div class="p-5">
      <textarea
        ref="textareaRef"
        v-model="text"
        class="w-full min-h-[56px] border-none outline-none resize-y text-[15px] text-primary bg-transparent leading-relaxed font-body placeholder:text-tertiary"
        rows="2"
        placeholder="用中文描述你想查询的数据，例如：查询最近一周各仓库的入库总量"
        :disabled="loading"
        @focus="isFocused = true"
        @blur="isFocused = false"
        @keydown.enter.exact.prevent="handleSubmit"
      ></textarea>
    </div>
    <!-- Footer -->
    <div class="flex items-center justify-between px-5 py-3 border-t border-grid bg-warm-gray">
      <div class="flex gap-2 flex-wrap">
        <button
          v-for="q in suggestions"
          :key="q"
          @click="text = q"
          class="text-[11px] px-[10px] py-1 rounded-full border border-grid bg-surface text-secondary hover:border-accent-orange hover:text-accent-orange hover:bg-accent-soft transition-all duration-150 ease-out-expo cursor-pointer whitespace-nowrap font-body"
        >{{ q }}</button>
      </div>
      <button
        @click="handleSubmit"
        :disabled="!text.trim() || loading"
        class="btn-primary"
      >
        <span v-if="!loading">执行查询</span>
        <span v-else class="inline-flex items-center gap-1.5">
          <span class="w-2 h-2 bg-white animate-pulse-dot"></span>
          查询中
        </span>
        <span class="icon-nest">
          <Icon icon="lucide:arrow-up" width="16" height="16" />
        </span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Icon } from '@iconify/vue'

defineProps({
  loading: Boolean,
})

const emit = defineEmits(['query'])

const text = ref('')
const textareaRef = ref(null)
const isFocused = ref(false)

const suggestions = [
  '查询本月出库量前10的SKU',
  '对比各仓库当前库存周转天数',
  '统计昨日各仓入库异常批次数量',
]

function handleSubmit() {
  const val = text.value.trim()
  if (!val) return
  emit('query', val)
}
</script>

<style scoped>
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 20px;
  background: var(--color-accent);
  color: #fff;
  border: none;
  border-radius: var(--radius);
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 150ms cubic-bezier(0.32, 0.72, 0, 1);
  letter-spacing: 0.01em;
}
.btn-primary:hover:not(:disabled) {
  background: var(--color-accent-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(199,91,42,0.25);
}
.btn-primary:active:not(:disabled) { transform: scale(0.98); }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.icon-nest {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px; height: 24px;
  border-radius: 9999px;
  background: rgba(255,255,255,0.15);
  transition: all 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.btn-primary:hover:not(:disabled) .icon-nest {
  transform: translateX(2px) translateY(-1px);
  background: rgba(255,255,255,0.22);
}
</style>
