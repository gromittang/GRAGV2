<template>
  <div class="bg-surface border border-grid overflow-hidden flex flex-col">
    <!-- Toolbar: Batch Actions -->
    <BatchActions
      v-if="selectedIds.length > 0"
      :selected-count="selectedIds.length"
      @delete="$emit('batchDelete')"
      @refresh="$emit('batchRefresh')"
      @tag="$emit('batchTag')"
      @clear="$emit('clearSelection')"
    />

    <!-- Table Header -->
    <div class="grid grid-cols-[40px_1fr_120px_100px] hairline-b bg-warm-gray px-4 h-[36px] items-center sticky top-0 z-10">
      <div class="flex items-center">
        <input
          type="checkbox"
          :checked="allSelected"
          @change="$emit('selectAll')"
          class="w-4 h-4 border-grid accent-accent-orange"
        />
      </div>
      <div class="font-mono text-[10px] uppercase tracking-widest text-primary/40">文件名 & 属性</div>
      <div class="font-mono text-[10px] uppercase tracking-widest text-primary/40 text-center">统计数据</div>
      <div class="font-mono text-[10px] uppercase tracking-widest text-primary/40 text-right px-2">操作</div>
    </div>

    <!-- Empty State -->
    <div v-if="documents.length === 0" class="py-8">
      <EmptyState
        icon="lucide:database"
        title="暂无文档"
        description="上传第一个文档开始构建知识库"
        color="primary/30"
      />
    </div>

    <!-- Document Rows -->
    <DocumentRow
      v-for="(doc, index) in documents"
      :key="doc.id"
      :doc="doc"
      :selected="selectedIds.includes(doc.id)"
      :even="index % 2 === 1"
      @toggle="$emit('toggleSelect', doc.id)"
      @preview="$emit('preview', doc)"
      @delete="$emit('delete', doc)"
      @download="$emit('download', doc)"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import DocumentRow from './DocumentRow.vue'
import BatchActions from './BatchActions.vue'
import EmptyState from '../common/EmptyState.vue'

const props = defineProps({
  documents: { type: Array, default: () => [] },
  selectedIds: { type: Array, default: () => [] },
})

defineEmits([
  'selectAll', 'toggleSelect', 'clearSelection',
  'batchDelete', 'batchRefresh', 'batchTag',
  'preview', 'delete', 'download',
])

const allSelected = computed(() =>
  props.documents.length > 0 && props.selectedIds.length === props.documents.length
)
</script>
