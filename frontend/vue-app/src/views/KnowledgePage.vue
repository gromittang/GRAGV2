<template>
  <div class="flex-1 flex flex-col bg-paper overflow-hidden">
    <!-- Header -->
    <header class="h-20 hairline-b flex items-center justify-between px-12 sticky top-0 bg-paper z-40">
      <div class="flex items-center gap-4">
        <router-link v-if="kbId" to="/knowledge" class="text-primary/40 hover:text-accent-orange transition-colors mr-2">
          <Icon icon="lucide:arrow-left" class="text-xl" />
        </router-link>
        <h1 class="font-display text-2xl font-bold text-primary tracking-tight">知识库</h1>
        <span class="w-1 h-1 bg-grid/60 rounded-full"></span>
        <span class="font-mono text-[12px] uppercase text-accent-orange tracking-widest font-bold">
          {{ kbId ? kbName : '标准作业程序 (SOP)' }}
        </span>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex flex-col items-end">
          <span class="font-mono text-[10px] uppercase text-primary/50 leading-none mb-0.5">LAST UPDATED</span>
          <span class="font-mono text-[11px] text-primary font-bold">{{ lastUpdated || '--' }}</span>
        </div>
      </div>
    </header>

    <!-- KB List View (no kbId) -->
    <div v-if="!kbId" class="flex-1 overflow-y-auto px-12 py-10">
      <StatsBento />
      <div class="mb-4 flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-primary/40">
        <span>KNOWLEDGE BASE</span>
        <span class="opacity-40">/</span>
        <span class="text-accent-orange font-bold">ALL</span>
      </div>
      <KBCardGrid
        :kb-list="kbList"
        @create="showKBForm = true"
        @edit="onKBEdit"
        @clear="confirmKBClear"
        @delete="confirmKBDelete"
      />
    </div>

    <!-- Document List View (has kbId) -->
    <div v-else class="flex-1 overflow-y-auto px-12 py-10">
      <div class="mb-4 flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-primary/40">
        <router-link to="/knowledge" class="hover:text-accent-orange transition-colors">KNOWLEDGE BASE</router-link>
        <span class="opacity-40">/</span>
        <span class="text-accent-orange font-bold">{{ kbName }}</span>
      </div>
      <UploadBar :kb-id="kbId" :kb-name="kbName" @uploaded="onUploaded" />
      <DocumentFilter :total="totalDocs" @filter="onFilter" />
      <DocumentTable
        :documents="documents"
        :selected-ids="selectedDocIds"
        @select-all="store.selectAll"
        @toggle-select="store.toggleSelectDoc"
        @clear-selection="store.selectedDocIds = []"
        @batch-delete="confirmBatchDelete"
        @batch-refresh="onBatchRefresh"
        @batch-tag="showTagManager = true"
        @preview="onPreview"
        @delete="confirmDelete"
        @download="onDownload"
      />
    </div>

    <!-- KB Form Modal -->
    <KBForm :visible="showKBForm" @close="showKBForm = false" @submit="handleCreateKB" />

    <!-- Tag Manager Modal -->
    <TagManager
      :visible="showTagManager"
      :tags="store.tags"
      @close="showTagManager = false"
      @create-tag="(t) => console.log('Create tag:', t)"
      @apply-tags="(ids) => console.log('Apply tags:', ids)"
    />

    <!-- Preview Modal -->
    <PreviewModal
      :visible="previewVisible"
      :doc="previewDoc"
      @close="previewVisible = false"
      @download="onDownload(previewDoc)"
    />

    <!-- Confirm Dialog — Single Delete -->
    <ConfirmDialog
      :visible="deleteConfirm.visible"
      :title="deleteConfirm.title"
      :message="deleteConfirm.message"
      confirm-text="删除"
      @confirm="executeDelete"
      @cancel="deleteConfirm.visible = false"
    />

    <!-- Confirm Dialog — Batch Delete -->
    <ConfirmDialog
      :visible="batchDeleteConfirm.visible"
      :title="batchDeleteConfirm.title"
      :message="batchDeleteConfirm.message"
      confirm-text="批量删除"
      @confirm="executeBatchDelete"
      @cancel="batchDeleteConfirm.visible = false"
    />

    <!-- Confirm Dialog — KB Clear -->
    <ConfirmDialog
      :visible="kbClearConfirm.visible"
      :title="kbClearConfirm.title"
      :message="kbClearConfirm.message"
      confirm-text="清空文档"
      @confirm="executeKBClear"
      @cancel="kbClearConfirm.visible = false"
    />

    <!-- Confirm Dialog — KB Delete -->
    <ConfirmDialog
      :visible="kbDeleteConfirm.visible"
      :title="kbDeleteConfirm.title"
      :message="kbDeleteConfirm.message"
      confirm-text="删除知识库"
      confirm-class="bg-danger hover:opacity-90"
      @confirm="executeKBDelete"
      @cancel="kbDeleteConfirm.visible = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useKnowledgeStore } from '../stores/knowledge'
import { useAppStore } from '../stores/app'
import StatsBento from '../components/knowledge/StatsBento.vue'
import KBCardGrid from '../components/knowledge/KBCardGrid.vue'
import KBForm from '../components/knowledge/KBForm.vue'
import UploadBar from '../components/knowledge/UploadBar.vue'
import DocumentFilter from '../components/knowledge/DocumentFilter.vue'
import DocumentTable from '../components/knowledge/DocumentTable.vue'
import TagManager from '../components/knowledge/TagManager.vue'
import PreviewModal from '../components/knowledge/PreviewModal.vue'
import ConfirmDialog from '../components/common/ConfirmDialog.vue'

const route = useRoute()
const store = useKnowledgeStore()
const appStore = useAppStore()

const kbId = computed(() => route.params.kbId)
const kbName = computed(() => {
  const kb = store.kbList.find(k => k.id === kbId.value)
  return kb?.name || '默认知识库'
})
const kbList = computed(() => store.kbList)
const lastUpdated = computed(() => appStore.lastUpdated)
const documents = computed(() => store.documents)
const totalDocs = computed(() => store.totalDocs)
const selectedDocIds = computed(() => store.selectedDocIds)
const showKBForm = ref(false)
const showTagManager = ref(false)
const previewVisible = ref(false)
const previewDoc = ref(null)

const deleteConfirm = reactive({ visible: false, title: '', message: '', docId: null })
const batchDeleteConfirm = reactive({ visible: false, title: '', message: '' })
const kbClearConfirm = reactive({ visible: false, title: '', message: '', kb: null })
const kbDeleteConfirm = reactive({ visible: false, title: '', message: '', kb: null })

onMounted(() => {
  store.fetchStats()
  store.fetchKBList()
  appStore.updateLastUpdated()
})

watch(kbId, (id) => {
  if (id) store.fetchDocuments(id)
}, { immediate: true })

async function handleCreateKB(form) {
  const result = await store.createKB(form.name, form.description)
  if (result.success) {
    showKBForm.value = false
  } else {
    console.error('创建失败:', result.error)
  }
}

function onUploaded(result) {
  if (kbId.value) store.fetchDocuments(kbId.value)
  store.fetchStats()
}

function onFilter(filters) {
  if (kbId.value) store.fetchDocuments(kbId.value, 1, filters)
}

function onPreview(doc) {
  previewDoc.value = doc
  previewVisible.value = true
}

function onDownload(doc) {
  if (!doc) return
  window.open(`/api/v1/docs/download-source/${doc.id}`, '_blank')
}

// Single delete with ConfirmDialog
function confirmDelete(doc) {
  deleteConfirm.docId = doc.id
  deleteConfirm.title = '删除文档'
  deleteConfirm.message = `确定要删除 "${doc.name || doc.filename}" 吗？此操作不可撤销。`
  deleteConfirm.visible = true
}

async function executeDelete() {
  if (deleteConfirm.docId) {
    await store.deleteDocument(deleteConfirm.docId)
    store.fetchStats()
  }
  deleteConfirm.visible = false
  deleteConfirm.docId = null
}

// Batch delete with ConfirmDialog
function confirmBatchDelete() {
  batchDeleteConfirm.title = '批量删除文档'
  batchDeleteConfirm.message = `确定要删除选中的 ${store.selectedDocIds.length} 个文档吗？此操作不可撤销。`
  batchDeleteConfirm.visible = true
}

async function executeBatchDelete() {
  await store.batchDelete(store.selectedDocIds)
  store.fetchStats()
  batchDeleteConfirm.visible = false
}

function onBatchRefresh() {
  store.batchDelete(store.selectedDocIds)
}

// KB Management
function onKBEdit(kb) {
  console.log('Edit KB:', kb)
  // TODO: open edit form
}

function confirmKBClear(kb) {
  kbClearConfirm.kb = kb
  kbClearConfirm.title = '清空知识库'
  kbClearConfirm.message = `确定要清空 "${kb.name}" 中的所有文档吗？此操作不可撤销。`
  kbClearConfirm.visible = true
}

async function executeKBClear() {
  if (kbClearConfirm.kb) {
    await store.clearKB(kbClearConfirm.kb.id)
    store.fetchKBList()
    store.fetchStats()
  }
  kbClearConfirm.visible = false
  kbClearConfirm.kb = null
}

function confirmKBDelete(kb) {
  kbDeleteConfirm.kb = kb
  kbDeleteConfirm.title = '删除知识库'
  kbDeleteConfirm.message = `确定要删除 "${kb.name}" 吗？知识库及其所有文档将被永久删除，此操作不可撤销。`
  kbDeleteConfirm.visible = true
}

async function executeKBDelete() {
  if (kbDeleteConfirm.kb) {
    await store.deleteKB(kbDeleteConfirm.kb.id)
    store.fetchKBList()
    store.fetchStats()
  }
  kbDeleteConfirm.visible = false
  kbDeleteConfirm.kb = null
}
</script>
