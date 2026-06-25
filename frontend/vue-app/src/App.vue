<template>
  <div class="flex h-screen overflow-hidden">
    <AppSidebar />
    <main class="flex-1 flex flex-col bg-paper overflow-hidden relative">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import AppSidebar from './components/sidebar/AppSidebar.vue'
</script>
