import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'

export const useAppStore = defineStore('app', () => {
  const route = useRoute()

  const currentPage = computed(() => {
    const name = route.name
    if (name === 'Chat') return 'chat'
    if (name === 'Knowledge' || name === 'KnowledgeDetail') return 'knowledge'
    if (name === 'Query') return 'query'
    if (name === 'Settings') return 'settings'
    if (name === 'PMStudio') return 'pm-studio'
    return 'chat'
  })

  const systemOnline = ref(true)
  const lastUpdated = ref('')

  function updateLastUpdated() {
    const now = new Date()
    lastUpdated.value = now.toISOString().slice(0, 16).replace('T', ' ')
  }

  return {
    currentPage,
    systemOnline,
    lastUpdated,
    updateLastUpdated,
  }
})
