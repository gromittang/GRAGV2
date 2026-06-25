<template>
  <teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-[200] flex items-center justify-center animate-modal-in">
      <div class="absolute inset-0 bg-sidebar/40 backdrop-blur-[2px]" @click="$emit('cancel')"></div>
      <div class="relative bg-surface border border-grid w-full max-w-[360px] z-[210] p-6 rounded-md shadow-modal">
        <div class="flex items-start gap-3 mb-4">
          <div class="w-8 h-8 bg-danger-soft rounded flex items-center justify-center flex-shrink-0">
            <Icon icon="lucide:alert-triangle" class="text-danger text-lg" />
          </div>
          <div>
            <p class="font-display text-[14px] font-bold text-primary mb-1">{{ title }}</p>
            <p class="text-[12px] text-secondary leading-relaxed">{{ message }}</p>
          </div>
        </div>
        <div class="flex items-center justify-end gap-2">
          <button @click="$emit('cancel')" class="px-4 h-8 border border-grid rounded text-[12px] text-secondary hover:bg-warm-gray transition-all duration-150 ease-out-expo">取消</button>
          <button @click="$emit('confirm')" class="px-4 h-8 bg-danger text-white rounded text-[12px] font-semibold hover:opacity-90 transition-all duration-150 ease-spring active:scale-[0.98]">{{ confirmText }}</button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { Icon } from '@iconify/vue'

defineProps({
  visible: Boolean,
  title: { type: String, default: '确认操作' },
  message: { type: String, default: '此操作不可撤销，确定继续吗？' },
  confirmText: { type: String, default: '确定' },
})

defineEmits(['confirm', 'cancel'])
</script>
