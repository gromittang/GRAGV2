<template>
  <div class="ml-12 mr-2 mb-1 max-h-[200px] overflow-y-auto scrollbar-thin">
    <div
      v-for="session in store.sessions"
      :key="session.session_id"
      @click="store.loadSession(session.session_id)"
      class="flex items-center justify-between px-3 py-2 cursor-pointer group text-white/50 hover:text-white/70 hover:bg-white/5 transition-colors text-[13px]"
      :class="{ 'bg-white/10 text-white/80': store.currentSessionId === session.session_id }"
    >
      <span class="truncate flex-1">{{ session.title || '新对话' }}</span>
      <button
        @click.stop="store.deleteSession(session.session_id)"
        class="opacity-0 group-hover:opacity-100 text-white/30 hover:text-danger transition-all ml-1 flex-shrink-0"
        title="删除会话"
      >
        <Icon icon="lucide:x" class="text-[14px]" />
      </button>
    </div>
    <div v-if="store.sessions.length === 0" class="px-3 py-2 text-white/30 text-[12px]">
      暂无历史会话
    </div>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useChatStore } from '../../stores/chat'

const store = useChatStore()
</script>

<style scoped>
.scrollbar-thin::-webkit-scrollbar {
  width: 4px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}
.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>
