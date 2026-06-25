<template>
  <div v-if="store.hasResults && store.sql" class="border border-grid bg-surface p-5">
    <!-- Toggle header -->
    <button
      @click="expanded = !expanded"
      class="flex items-center gap-2 w-full text-left"
    >
      <Icon
        :icon="expanded ? 'lucide:chevron-down' : 'lucide:chevron-right'"
        class="text-[14px] text-primary/40"
      />
      <span class="font-mono text-[11px] uppercase tracking-widest font-bold text-primary/60">
        评价本次查询
      </span>
      <span v-if="store.feedbackSubmitted" class="text-[10px] text-accent-green font-mono ml-2">
        已提交
      </span>
    </button>

    <!-- Form body -->
    <div v-if="expanded" class="mt-4 space-y-4">
      <div v-if="submitted" class="text-[12px] text-accent-green font-mono border border-accent-green/20 bg-accent-green/5 p-3">
        评价已提交，感谢反馈！
      </div>

      <div v-else class="space-y-4">
        <!-- 3 boolean toggles -->
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-[12px] text-primary/70">表选择正确？</span>
            <button
              @click="rating.tableCorrect = !rating.tableCorrect"
              :class="rating.tableCorrect ? 'bg-accent-green/10 text-accent-green border-accent-green/30' : 'bg-red-50 text-red-500 border-red-200'"
              class="px-3 py-1 text-[11px] font-mono border transition-colors"
            >{{ rating.tableCorrect ? '是' : '否' }}</button>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-[12px] text-primary/70">字段使用正确？</span>
            <button
              @click="rating.fieldCorrect = !rating.fieldCorrect"
              :class="rating.fieldCorrect ? 'bg-accent-green/10 text-accent-green border-accent-green/30' : 'bg-red-50 text-red-500 border-red-200'"
              class="px-3 py-1 text-[11px] font-mono border transition-colors"
            >{{ rating.fieldCorrect ? '是' : '否' }}</button>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-[12px] text-primary/70">结果符合预期？</span>
            <button
              @click="rating.resultCorrect = !rating.resultCorrect"
              :class="rating.resultCorrect ? 'bg-accent-green/10 text-accent-green border-accent-green/30' : 'bg-red-50 text-red-500 border-red-200'"
              class="px-3 py-1 text-[11px] font-mono border transition-colors"
            >{{ rating.resultCorrect ? '是' : '否' }}</button>
          </div>
        </div>

        <!-- Comment -->
        <div>
          <textarea
            v-model="rating.comment"
            placeholder="备注（哪里不对？应该怎么改？）"
            rows="3"
            class="w-full border border-grid p-2 text-[12px] font-mono text-primary/70 bg-warm-gray/30 resize-none focus:outline-none focus:border-accent-orange/40"
          ></textarea>
        </div>

        <!-- Submit -->
        <button
          @click="handleSubmit"
          :disabled="submitting"
          class="w-full h-9 border border-accent-orange/40 text-[12px] font-mono text-accent-orange hover:bg-accent-orange hover:text-white transition-colors disabled:opacity-40"
        >{{ submitting ? '提交中...' : '提交评价' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { Icon } from '@iconify/vue'
import { useQueryStore } from '../../stores/query'

const store = useQueryStore()
const expanded = ref(false)
const submitting = ref(false)
const submitted = ref(false)

const rating = reactive({
  tableCorrect: true,
  fieldCorrect: true,
  resultCorrect: true,
  comment: '',
})

async function handleSubmit() {
  submitting.value = true
  const ok = await store.submitFeedback({
    tableCorrect: rating.tableCorrect,
    fieldCorrect: rating.fieldCorrect,
    resultCorrect: rating.resultCorrect,
    comment: rating.comment,
  })
  submitting.value = false
  if (ok) {
    submitted.value = true
  }
}
</script>
