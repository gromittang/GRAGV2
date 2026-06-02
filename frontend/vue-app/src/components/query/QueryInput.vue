<template>
  <div class="border border-grid bg-surface p-4">
    <div class="flex items-end gap-3">
      <div class="flex-1">
        <label class="block font-mono text-[10px] uppercase text-primary/40 mb-2 tracking-wider">自然语言查询</label>
        <textarea
          ref="textareaRef"
          v-model="text"
          class="w-full resize-none bg-warm-gray border border-grid px-4 py-3 text-[14px] text-primary placeholder:text-primary/30 focus:outline-none focus:border-accent-orange/40 transition-colors"
          rows="2"
          placeholder="例如：查询库存最多的商品"
          :disabled="loading"
          @keydown.enter.exact.prevent="handleSubmit"
        ></textarea>
      </div>
      <button
        @click="handleSubmit"
        :disabled="!text.trim() || loading"
        class="h-10 px-6 bg-accent-orange text-white text-[13px] font-medium hover:bg-accent-orange/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <span v-if="!loading">执行查询</span>
        <span v-else class="inline-flex items-center gap-1.5">
          <span class="w-2 h-2 bg-white animate-pulse-dot"></span>
          查询中
        </span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  loading: Boolean,
})

const emit = defineEmits(['query'])

const text = ref('')
const textareaRef = ref(null)

function handleSubmit() {
  const val = text.value.trim()
  if (!val) return
  emit('query', val)
}
</script>
