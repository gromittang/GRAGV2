<template>
  <teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-[100] flex items-center justify-center animate-modal-in">
      <div class="absolute inset-0 bg-sidebar/40 backdrop-blur-[2px]" @click="$emit('close')"></div>
      <div class="relative bg-surface border border-grid w-full max-w-[480px] z-[110]">
        <div class="h-14 hairline-b flex items-center justify-between px-6 bg-warm-gray">
          <span class="font-space text-[15px] font-bold text-primary">{{ isEdit ? '编辑知识库' : '创建新知识库' }}</span>
          <button @click="$emit('close')" class="w-8 h-8 flex items-center justify-center text-primary/40 hover:text-primary">
            <Icon icon="lucide:x" class="text-xl" />
          </button>
        </div>
        <div class="p-6 space-y-4">
          <div>
            <label class="block font-mono text-[11px] uppercase tracking-widest text-primary/50 mb-1">名称</label>
            <input v-model="form.name" class="w-full h-10 px-3 border border-grid text-[14px] text-primary bg-surface focus:outline-none focus:border-primary/50" placeholder="知识库名称" />
          </div>
          <div>
            <label class="block font-mono text-[11px] uppercase tracking-widest text-primary/50 mb-1">描述</label>
            <textarea v-model="form.description" rows="3" class="w-full px-3 py-2 border border-grid text-[14px] text-primary bg-surface focus:outline-none focus:border-primary/50 resize-none" placeholder="知识库描述（可选）"></textarea>
          </div>
          <div class="flex items-center justify-end gap-3 pt-4">
            <button @click="$emit('close')" class="px-6 h-10 border border-grid text-[13px] text-primary/60 hover:bg-warm-gray transition-colors">取消</button>
            <button @click="submit" class="px-6 h-10 bg-primary text-white text-[13px] font-medium hover:bg-primary/90 transition-colors">{{ isEdit ? '保存' : '创建' }}</button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  visible: Boolean,
  isEdit: { type: Boolean, default: false },
  kbData: { type: Object, default: null },
})

const emit = defineEmits(['close', 'submit'])

const form = reactive({
  name: props.kbData?.name || '',
  description: props.kbData?.description || '',
})

function submit() {
  if (!form.name.trim()) return
  emit('submit', { ...form })
  form.name = ''
  form.description = ''
}
</script>
