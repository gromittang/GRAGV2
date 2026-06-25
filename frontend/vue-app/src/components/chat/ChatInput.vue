<template>
  <div class="border-t border-grid bg-surface px-6 py-4 flex-shrink-0">
    <div class="max-w-3xl mx-auto flex items-end gap-3">
      <textarea
        ref="textareaRef"
        v-model="text"
        class="flex-1 resize-none bg-warm-gray border border-grid px-4 py-3 text-[14px] text-primary placeholder:text-primary/30 focus:outline-none focus:border-accent-orange/40 transition-colors min-h-[44px] max-h-[160px]"
        rows="1"
        :placeholder="placeholder"
        :disabled="disabled"
        @keydown.enter.exact.prevent="handleSend"
        @input="autoResize"
      ></textarea>
      <button
        @click="handleSend"
        :disabled="!text.trim() || disabled"
        class="h-[44px] px-5 bg-accent-orange text-white text-[13px] font-medium hover:bg-accent-orange/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center"
      >
        <span v-if="!loading">发送</span>
        <span v-else class="inline-flex items-center gap-1.5">
          <span class="w-2 h-2 bg-white animate-pulse-dot"></span>
          处理中
        </span>
      </button>
    </div>
    <p class="mt-2 text-[10px] text-primary/25 font-mono">Enter 发送，Agent 将自动选择知识库检索或数据库查询</p>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  disabled: Boolean,
  loading: Boolean,
  placeholder: { type: String, default: '输入问题...' },
})

const emit = defineEmits(['send'])

const text = ref('')
const textareaRef = ref(null)

function autoResize() {
  nextTick(() => {
    const el = textareaRef.value
    if (el) {
      el.style.height = 'auto'
      // 最小44px，最大160px
      el.style.height = Math.max(44, Math.min(el.scrollHeight, 160)) + 'px'
    }
  })
}

function handleSend() {
  const val = text.value.trim()
  if (!val || props.disabled) return
  emit('send', val)
  text.value = ''
  nextTick(autoResize)
}

watch(() => props.disabled, (v) => {
  if (!v) {
    nextTick(() => textareaRef.value?.focus())
  }
})
</script>
