<template>
  <div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <KBCard
        v-for="kb in kbList"
        :key="kb.id"
        :kb="kb"
        :doc-count="kb.document_count || 0"
        :chunk-count="kb.paragraph_count || 0"
        @edit="$emit('edit', $event)"
        @clear="$emit('clear', $event)"
        @delete="$emit('delete', $event)"
      />
      <!-- Create new KB placeholder -->
      <button
        @click="$emit('create')"
        class="block border border-dashed border-grid bg-transparent p-8 hover:border-accent-orange/40 hover:bg-warm-gray/50 transition-all duration-200 text-left cursor-pointer"
      >
        <div class="flex items-center gap-3 mb-4">
          <div class="w-10 h-10 border border-dashed border-grid flex items-center justify-center flex-shrink-0">
            <Icon icon="lucide:plus" class="text-grid text-xl" />
          </div>
        </div>
        <h3 class="font-space text-lg font-bold text-primary/40 mb-1">创建新知识库</h3>
        <p class="text-[13px] text-primary/30 leading-relaxed">上传文档并建立新的知识库</p>
      </button>
    </div>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'
import KBCard from './KBCard.vue'

defineProps({
  kbList: { type: Array, default: () => [] },
})
defineEmits(['create', 'edit', 'clear', 'delete'])
</script>
