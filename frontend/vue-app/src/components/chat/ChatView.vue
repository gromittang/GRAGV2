<template>
  <div class="flex-1 flex flex-col min-h-0">
    <!-- Message area -->
    <div ref="scrollRef" class="flex-1 overflow-y-auto px-6 py-6 space-y-5 min-h-0">
      <!-- Empty state -->
      <div v-if="!messages.length && !streaming" class="flex items-center justify-center h-full">
        <div class="text-center max-w-sm">
          <Icon icon="lucide:message-square" class="text-5xl text-grid mb-5 mx-auto" />
          <p class="text-[15px] text-slate-600 font-medium mb-2">智能问答</p>
          <p class="text-[13px] text-slate-500 leading-relaxed">
            输入问题，系统将自动检索知识库内容
          </p>
        </div>
      </div>

      <!-- Messages -->
      <template v-for="(msg, i) in messages" :key="i">
        <ChatMessage
          :role="msg.role"
          :content="msg.content"
          :sources="msg.sources"
          :message-index="msg.messageIndex ?? -1"
          :feedback-submitted="msg.feedbackSubmitted ?? false"
        />
      </template>

      <!-- Streaming message -->
      <ChatMessage
        v-if="streaming && streamingContent"
        role="assistant"
        :content="streamingContent"
      />

      <!-- Loading indicator -->
      <div v-if="loading && !streamingContent" class="flex items-center gap-2 px-1">
        <span class="w-2 h-2 bg-accent-green animate-pulse-dot"></span>
        <span class="font-mono text-[11px] text-primary/30">Agent 思考中...</span>
      </div>
    </div>

    <!-- Input -->
    <ChatInput
      :disabled="loading"
      :loading="loading"
      @send="$emit('send', $event)"
    />
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { Icon } from '@iconify/vue'
import ChatMessage from './ChatMessage.vue'
import ChatInput from './ChatInput.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: Boolean,
  streaming: Boolean,
  streamingContent: { type: String, default: '' },
  tools: { type: Array, default: () => [] },
})

defineEmits(['send'])

const scrollRef = ref(null)

function scrollToBottom() {
  nextTick(() => {
    const el = scrollRef.value
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  })
}

watch(() => props.messages.length, scrollToBottom)
watch(() => props.streamingContent, scrollToBottom)
</script>
