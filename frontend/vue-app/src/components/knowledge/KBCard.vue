<template>
  <div class="relative border border-grid bg-surface hover:-translate-y-0.5 hover:border-primary/30 transition-all duration-200">
    <!-- Card content (clickable) -->
    <router-link
      :to="`/knowledge/${kb.id}`"
      class="block p-8 no-underline"
    >
      <div class="flex items-start justify-between mb-4">
        <div class="w-10 h-10 bg-primary flex items-center justify-center flex-shrink-0">
          <Icon icon="lucide:folder" class="text-white text-xl" />
        </div>
      </div>
      <h3 class="font-space text-lg font-bold text-primary mb-1">{{ kb.name || '未命名知识库' }}</h3>
      <p class="text-[13px] text-primary/50 mb-4 leading-relaxed">
        {{ kb.description || 'WMS仓库操作手册与规范文档' }}
      </p>
      <div class="flex items-center gap-6 font-mono text-[11px] text-primary/40">
        <span>{{ kb.document_count || docCount }} 文档数</span>
        <span>{{ kb.paragraph_count || chunkCount }} 片段数</span>
      </div>
    </router-link>

    <!-- Management menu -->
    <div class="absolute top-4 right-4">
      <button
        @click.stop.prevent="showMenu = !showMenu"
        class="w-8 h-8 flex items-center justify-center text-primary/40 hover:text-primary hover:bg-warm-gray/50 transition-colors"
      >
        <Icon icon="lucide:more-vertical" class="text-lg" />
      </button>
      <!-- Dropdown menu -->
      <div
        v-if="showMenu"
        @click.stop
        class="absolute right-0 top-10 w-36 bg-surface border border-grid shadow-lg z-50"
      >
        <button
          @click.stop.prevent="onEdit"
          class="w-full px-4 py-3 text-left text-[13px] text-primary hover:bg-warm-gray/50 flex items-center gap-2"
        >
          <Icon icon="lucide:edit-3" class="text-base" />
          编辑信息
        </button>
        <button
          @click.stop.prevent="onClear"
          class="w-full px-4 py-3 text-left text-[13px] text-primary hover:bg-warm-gray/50 flex items-center gap-2"
        >
          <Icon icon="lucide:trash-2" class="text-base" />
          清空文档
        </button>
        <button
          @click.stop.prevent="onDelete"
          class="w-full px-4 py-3 text-left text-[13px] text-red-600 hover:bg-red-50 flex items-center gap-2"
        >
          <Icon icon="lucide:x-circle" class="text-base" />
          删除知识库
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  kb: { type: Object, required: true },
  docCount: { type: Number, default: 0 },
  chunkCount: { type: Number, default: 0 },
})

const emit = defineEmits(['edit', 'clear', 'delete'])

const showMenu = ref(false)

function onEdit() {
  showMenu.value = false
  emit('edit', props.kb)
}

function onClear() {
  showMenu.value = false
  emit('clear', props.kb)
}

function onDelete() {
  showMenu.value = false
  emit('delete', props.kb)
}

// Close menu when clicking outside
document.addEventListener('click', () => {
  showMenu.value = false
})
</script>
