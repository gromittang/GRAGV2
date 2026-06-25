<template>
  <nav class="flex-1 flex flex-col gap-[2px] py-4 px-3 overflow-y-auto relative z-[1]">
    <!-- 第1段: 智能助手 — 独立置顶（编排/混合入口） -->
    <router-link
      to="/orchestrator"
      class="nav-item"
      :class="{ active: isActive('orchestrator') }"
    >
      <Icon icon="lucide:sparkles" width="18" height="18" />
      <span>智能助手</span>
    </router-link>

    <!-- 分隔 -->
    <div class="nav-section-label">功能模块</div>

    <router-link
      to="/query"
      class="nav-item"
      :class="{ active: isActive('query') }"
    >
      <Icon icon="lucide:search" width="18" height="18" />
      <span>数据查询</span>
    </router-link>

    <router-link
      to="/chat"
      class="nav-item"
      :class="{ active: isActive('chat') }"
    >
      <Icon icon="lucide:message-square" width="18" height="18" />
      <span>智能问答</span>
    </router-link>
    <!-- Session list under Chat -->
    <SessionList v-if="isActive('chat')" />

    <router-link
      to="/knowledge"
      class="nav-item"
      :class="{ active: isActive('knowledge') }"
    >
      <Icon icon="lucide:database" width="18" height="18" />
      <span>知识库</span>
    </router-link>

    <router-link
      to="/pm-studio"
      class="nav-item"
      :class="{ active: isActive('pm-studio') }"
    >
      <Icon icon="lucide:file-text" width="18" height="18" />
      <span>PM方案工作室</span>
    </router-link>

    <!-- 分隔 -->
    <div class="nav-section-label">系统</div>

    <router-link
      to="/logs"
      class="nav-item"
      :class="{ active: isActive('logs') }"
    >
      <Icon icon="lucide:scroll-text" width="18" height="18" />
      <span>系统日志</span>
    </router-link>

    <router-link
      to="/settings"
      class="nav-item"
      :class="{ active: isActive('settings') }"
    >
      <Icon icon="lucide:settings" width="18" height="18" />
      <span>系统设置</span>
    </router-link>
  </nav>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import { useAppStore } from '../../stores/app'
import SessionList from './SessionList.vue'

const store = useAppStore()

function isActive(id) {
  return store.currentPage === id
}
</script>

<style scoped>
.nav-section-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  color: rgba(255,255,255,0.22);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 16px 12px 8px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border-radius: var(--radius);
  color: rgba(255,255,255,0.50);
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  transition: all 150ms cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
}
.nav-item:hover {
  color: rgba(255,255,255,0.85);
  background: rgba(255,255,255,0.04);
}
.nav-item.active {
  color: #fff;
  background: rgba(255,255,255,0.07);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.06);
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: -11px;
  top: 6px;
  bottom: 6px;
  width: 3px;
  background: var(--color-accent);
  border-radius: 0 3px 3px 0;
}
.nav-item :deep(svg) { opacity: 0.7; }
.nav-item.active :deep(svg) { opacity: 1; }
</style>
