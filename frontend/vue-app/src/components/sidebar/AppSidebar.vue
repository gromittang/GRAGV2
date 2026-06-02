<template>
  <aside class="w-[240px] flex-shrink-0 bg-sidebar border-r border-white/10 flex flex-col sidebar-texture">
    <SidebarLogo />
    <SidebarNav />
    <div class="flex-1"></div>
    <SidebarStatus />
  </aside>
</template>

<script setup>
import SidebarLogo from './SidebarLogo.vue'
import SidebarNav from './SidebarNav.vue'
import SidebarStatus from './SidebarStatus.vue'
</script>
