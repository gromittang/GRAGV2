<template>
  <nav class="flex-1">
    <ul class="space-y-px">
      <li v-for="item in navItems" :key="item.id">
        <router-link
          :to="item.to"
          class="flex items-center gap-3 px-8 py-5 border-l-[3px] transition-all group no-underline"
          :class="isActive(item.id)
            ? 'border-accent-orange bg-white/10'
            : 'border-transparent hover:bg-white/5'"
        >
          <Icon
            :icon="item.icon"
            class="text-[18px] transition-colors flex-shrink-0"
            :class="isActive(item.id) ? 'text-white' : 'text-white/50 group-hover:text-white/80'"
          />
          <span
            class="text-[15px] font-medium transition-colors"
            :class="isActive(item.id) ? 'text-white' : 'text-white/50 group-hover:text-white/80'"
          >{{ item.label }}</span>
        </router-link>
        <!-- Session list under Chat -->
        <SessionList v-if="item.id === 'chat' && isActive('chat')" />
      </li>
    </ul>
  </nav>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useAppStore } from '../../stores/app'
import SessionList from './SessionList.vue'

const store = useAppStore()

const navItems = [
  { id: 'orchestrator', label: '智能助手', icon: 'lucide:sparkles', to: '/orchestrator' },
  { id: 'chat', label: '智能问答', icon: 'lucide:message-square', to: '/chat' },
  { id: 'knowledge', label: '知识库', icon: 'lucide:database', to: '/knowledge' },
  { id: 'pm-studio', label: 'PM方案工作室', icon: 'lucide:file-text', to: '/pm-studio' },
  { id: 'query', label: '数据查询', icon: 'lucide:search', to: '/query' },
  { id: 'logs', label: '系统日志', icon: 'lucide:scroll-text', to: '/logs' },
  { id: 'settings', label: '系统设置', icon: 'lucide:settings', to: '/settings' },
]

function isActive(id) {
  return store.currentPage === id
}
</script>
