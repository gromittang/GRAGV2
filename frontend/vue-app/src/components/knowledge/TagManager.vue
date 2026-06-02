<template>
  <teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-[100] flex items-center justify-center animate-modal-in">
      <div class="absolute inset-0 bg-sidebar/40 backdrop-blur-[2px]" @click="$emit('close')"></div>
      <div class="relative bg-surface border border-grid w-full max-w-[400px] z-[110]">
        <div class="h-12 hairline-b flex items-center justify-between px-4 bg-warm-gray">
          <span class="font-space text-[14px] font-bold text-primary">标签管理</span>
          <button @click="$emit('close')" class="w-6 h-6 flex items-center justify-center text-primary/40 hover:text-primary">
            <Icon icon="lucide:x" class="text-lg" />
          </button>
        </div>
        <div class="p-4 space-y-3">
          <!-- Create tag -->
          <div class="flex gap-2">
            <input v-model="newTagKey" placeholder="标签键" class="flex-1 h-8 px-2 border border-grid text-[12px] focus:outline-none focus:border-primary/30" />
            <input v-model="newTagValue" placeholder="标签值" class="flex-1 h-8 px-2 border border-grid text-[12px] focus:outline-none focus:border-primary/30" />
            <button @click="createTag" class="px-3 h-8 bg-primary text-white text-[11px] font-medium hover:bg-primary/90" :disabled="!newTagKey || !newTagValue">添加</button>
          </div>
          <!-- Tag list -->
          <div class="flex flex-wrap gap-2">
            <span
              v-for="tag in tags"
              :key="tag.id"
              @click="toggleTag(tag.id)"
              class="px-2 py-1 text-[11px] font-medium cursor-pointer border transition-colors"
              :class="selectedTags.includes(tag.id)
                ? 'bg-primary text-white border-primary'
                : 'bg-warm-gray text-primary/60 border-grid hover:border-primary/30'"
              :style="selectedTags.includes(tag.id) ? {} : { borderLeftColor: tag.color || '#3B82F6', borderLeftWidth: '2px' }"
            >
              {{ tag.key }}:{{ tag.value }}
            </span>
          </div>
          <div v-if="tags.length === 0" class="text-center py-4 text-primary/30 text-[12px]">
            暂无标签
          </div>
        </div>
        <div class="h-10 hairline-t flex items-center justify-end px-4 gap-2">
          <button @click="$emit('close')" class="px-4 h-7 text-[11px] text-primary/40 hover:text-primary">取消</button>
          <button @click="applyTags" class="px-4 h-7 bg-accent-orange text-white text-[11px] font-medium hover:bg-accent-orange/90" :disabled="selectedTags.length === 0">应用标签</button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref } from 'vue'
import { Icon } from '@iconify/vue'

defineProps({
  visible: Boolean,
  tags: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'create-tag', 'apply-tags'])

const newTagKey = ref('')
const newTagValue = ref('')
const selectedTags = ref([])

function createTag() {
  if (!newTagKey.value || !newTagValue.value) return
  emit('create-tag', { key: newTagKey.value, value: newTagValue.value })
  newTagKey.value = ''
  newTagValue.value = ''
}

function toggleTag(id) {
  const idx = selectedTags.value.indexOf(id)
  if (idx >= 0) selectedTags.value.splice(idx, 1)
  else selectedTags.value.push(id)
}

function applyTags() {
  emit('apply-tags', [...selectedTags.value])
  selectedTags.value = []
  emit('close')
}
</script>
