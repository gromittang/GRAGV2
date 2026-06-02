<template>
  <div class="flex-1 flex flex-col bg-paper overflow-hidden">
    <!-- Header -->
    <header class="h-20 hairline-b flex items-center justify-between px-12 sticky top-0 bg-paper z-40">
      <div class="flex items-center gap-4">
        <h1 class="font-space text-2xl font-bold text-primary tracking-tight">智能问答</h1>
        <span class="w-1 h-1 bg-grid/60 rounded-full"></span>
        <span class="font-mono text-[12px] uppercase text-accent-orange tracking-widest font-bold">Agent</span>
      </div>
      <button
        @click="store.newChat()"
        class="px-4 py-2 border border-grid text-[13px] font-medium text-primary hover:bg-warm-gray transition-colors inline-flex items-center gap-2"
      >
        <Icon icon="lucide:plus" class="text-sm" />
        新对话
      </button>
    </header>

    <!-- Chat Area -->
    <ChatView
      :messages="store.messages"
      :loading="store.loading"
      :streaming="store.streaming"
      :streaming-content="store.streamingContent"
      :tools="store.tools"
      @send="store.sendMessage"
    />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import { useChatStore } from '../stores/chat'
import ChatView from '../components/chat/ChatView.vue'

const store = useChatStore()

onMounted(() => {
  store.fetchSessions()
  store.fetchTools()
})
</script>
