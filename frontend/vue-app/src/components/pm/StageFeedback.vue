<template>
  <div v-if="visible" class="border border-grid bg-surface p-4 mt-4">
    <div class="flex items-center gap-2 mb-3">
      <Icon icon="lucide:star" class="text-[14px] text-accent-orange" />
      <span class="font-mono text-[11px] uppercase tracking-widest font-bold text-primary/60">
        评价本阶段
      </span>
      <span v-if="submitted" class="text-[10px] text-accent-green font-mono ml-2">已提交</span>
    </div>

    <div v-if="submitted" class="text-[12px] text-accent-green font-mono border border-accent-green/20 bg-accent-green/5 p-3">
      评价已提交，感谢反馈！
    </div>

    <div v-else class="space-y-3">
      <!-- Star rating -->
      <div class="flex items-center gap-1">
        <span class="text-[11px] text-primary/60 font-mono mr-2">评分</span>
        <button
          v-for="s in 5" :key="s"
          @click="rating = s"
          class="text-lg transition-colors"
          :class="s <= rating ? 'text-accent-orange' : 'text-grid'"
        >
          <Icon :icon="s <= rating ? 'lucide:star' : 'lucide:star'" />
        </button>
      </div>

      <!-- Satisfied toggle -->
      <div class="flex items-center justify-between">
        <span class="text-[11px] text-primary/60 font-mono">是否满足预期？</span>
        <button
          @click="satisfied = !satisfied"
          :class="satisfied ? 'bg-accent-green/10 text-accent-green border-accent-green/30' : 'bg-danger-soft text-danger border-danger/20'"
          class="px-3 py-1 text-[11px] font-mono border transition-colors"
        >{{ satisfied ? '是' : '否' }}</button>
      </div>

      <!-- Comment -->
      <textarea
        v-model="comment"
        placeholder="补充说明（哪里不满意？期望怎么改进？）"
        rows="2"
        class="w-full border border-grid p-2 text-[12px] font-mono text-primary/70 bg-warm-gray/30 resize-none focus:outline-none focus:border-accent-orange/40"
      ></textarea>

      <button
        @click="handleSubmit"
        :disabled="submitting"
        class="w-full h-9 border border-accent-orange/40 text-[12px] font-mono text-accent-orange hover:bg-accent-orange hover:text-white transition-colors disabled:opacity-40"
      >{{ submitting ? '提交中...' : '提交评价' }}</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Icon } from '@iconify/vue'
import pmSolutionApi from '../../api/pmSolution'

const props = defineProps({
  sessionId: { type: String, required: true },
  stage: { type: String, required: true },
  modifyCount: { type: Number, default: 1 },
  stageOutputSummary: { type: String, default: '' },
})

const visible = ref(true)
const rating = ref(3)
const satisfied = ref(true)
const comment = ref('')
const submitting = ref(false)
const submitted = ref(false)

async function handleSubmit() {
  submitting.value = true
  try {
    await pmSolutionApi.submitFeedback({
      session_id: props.sessionId,
      stage: props.stage,
      rating: rating.value,
      satisfied: satisfied.value,
      modify_count: props.modifyCount,
      stage_output_summary: props.stageOutputSummary,
      comment: comment.value,
    })
    submitted.value = true
  } catch (e) {
    console.error('Failed to submit PM feedback:', e)
  } finally {
    submitting.value = false
  }
}
</script>
