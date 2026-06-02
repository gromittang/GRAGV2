import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import documentsApi from '../api/documents'
import documentsV2Api from '../api/documentsV2'

export const useKnowledgeStore = defineStore('knowledge', () => {
  const stats = ref({
    uploaded_count: 0,
    indexed_count: 0,
    total_size_mb: 0,
  })
  const kbList = ref([])
  const documents = ref([])
  const totalDocs = ref(0)
  const totalCharLength = ref(0)
  const currentPage = ref(1)
  const pageSize = ref(50)
  const loading = ref(false)
  const selectedDocIds = ref([])
  const tags = ref([])

  const totalChunks = computed(() => {
    return documents.value.reduce((sum, d) => sum + (d.chunk_count || d.paragraph_count || 0), 0)
  })

  async function fetchStats() {
    try {
      const res = await documentsApi.stats()
      stats.value = res.data
    } catch (e) {
      console.error('Failed to fetch stats:', e)
    }
  }

  async function fetchKBList() {
    loading.value = true
    try {
      // Try V2 knowledge list API first
      const kbRes = await documentsV2Api.listKB()
      if (kbRes.data.success && kbRes.data.knowledge_list?.length > 0) {
        kbList.value = kbRes.data.knowledge_list
        loading.value = false
        return
      }
    } catch (e) {
      // V2 KB API failed, fall through to document-based approach
    }

    // Fallback: build KB list from V2 documents
    try {
      const res = await documentsV2Api.list(1, 50)
      const docs = res.data.documents || []
      if (docs.length > 0) {
        // Group V2 documents by knowledge_id to build KB cards
        const kbMap = new Map()
        for (const doc of docs) {
          const kid = doc.knowledge_id || 'default'
          if (!kbMap.has(kid)) {
            kbMap.set(kid, {
              id: kid,
              name: doc.knowledge_name || '默认知识库',
              description: doc.knowledge_description || '',
              document_count: 0,
              paragraph_count: 0,
              char_length: 0,
            })
          }
          const kb = kbMap.get(kid)
          kb.document_count++
          kb.paragraph_count += doc.chunk_count || doc.paragraph_count || 0
          kb.char_length += doc.char_length || 0
        }
        kbList.value = Array.from(kbMap.values())
      } else {
        // V2 empty — build default KB from V1 data
        await buildDefaultKBFromV1()
      }
    } catch (e) {
      // V2 unavailable — fallback to V1
      await buildDefaultKBFromV1()
    } finally {
      loading.value = false
    }
  }

  async function buildDefaultKBFromV1() {
    await fetchStats()
    try {
      const v1Res = await documentsApi.list()
      const v1Docs = v1Res.data.documents || []
      const uniqueFiles = new Set()
      let totalChars = 0
      let totalChunks = 0
      for (const d of v1Docs) {
        if (d.source === 'upload') uniqueFiles.add(d.id)
        totalChars += d.char_length || 0
        totalChunks += d.chunk_count || 1
      }
      kbList.value = [{
        id: 'default',
        name: '默认知识库',
        description: 'WMS仓库操作手册与规范文档',
        document_count: uniqueFiles.size || stats.value.uploaded_count || 0,
        paragraph_count: totalChunks || stats.value.indexed_count || 0,
        char_length: totalChars || 0,
        updated_at: v1Docs[0]?.upload_time || '',
      }]
    } catch (e) {
      kbList.value = [{
        id: 'default',
        name: '默认知识库',
        description: 'WMS仓库操作手册与规范文档',
        document_count: 0,
        paragraph_count: 0,
        char_length: 0,
      }]
    }
  }

  async function fetchDocuments(kbId, page = 1, filters = {}) {
    loading.value = true
    try {
      const params = { ...filters }
      if (kbId && kbId !== 'default') params.knowledge_id = kbId
      const res = await documentsV2Api.list(page, pageSize.value, params)
      const docs = res.data.documents || []
      if (docs.length > 0) {
        documents.value = docs
        totalDocs.value = res.data.total || docs.length
        totalCharLength.value = res.data.total_char_length || 0
        currentPage.value = page
        return
      }
    } catch (e) {
      // V2 failed, fall through to V1
    }

    // V1 fallback
    try {
      const res = await documentsApi.list()
      const allDocs = res.data.documents || []
      // Deduplicate: only show "upload" source docs
      const uploadDocs = allDocs.filter(d => d.source === 'upload')
      documents.value = uploadDocs
      totalDocs.value = uploadDocs.length
      totalCharLength.value = uploadDocs.reduce((s, d) => s + (d.char_length || 0), 0)
      currentPage.value = 1
    } catch (e2) {
      console.error('Failed to fetch documents:', e2)
      documents.value = []
      totalDocs.value = 0
    } finally {
      loading.value = false
    }
  }

  async function uploadDocument(file, kbId, kbName) {
    try {
      const res = await documentsV2Api.upload(file, kbId, kbName)
      return res.data
    } catch (e) {
      // V2 upload failed, try V1
      const res = await documentsApi.upload(file)
      return res.data
    }
  }

  async function deleteDocument(id) {
    try {
      await documentsV2Api.delete(id)
    } catch (e) {
      await documentsApi.delete(id)
    }
    documents.value = documents.value.filter(d => d.id !== id)
    totalDocs.value--
  }

  async function batchDelete(ids) {
    await documentsV2Api.batchDelete(ids)
    documents.value = documents.value.filter(d => !ids.includes(d.id))
    totalDocs.value -= ids.length
    selectedDocIds.value = []
  }

  function toggleSelectDoc(id) {
    const idx = selectedDocIds.value.indexOf(id)
    if (idx >= 0) {
      selectedDocIds.value.splice(idx, 1)
    } else {
      selectedDocIds.value.push(id)
    }
  }

  function selectAll() {
    if (selectedDocIds.value.length === documents.value.length) {
      selectedDocIds.value = []
    } else {
      selectedDocIds.value = documents.value.map(d => d.id)
    }
  }

  async function clearKB(kbId) {
    // Clear all documents in the KB
    try {
      await documentsV2Api.clearKB(kbId)
      documents.value = []
      totalDocs.value = 0
      // Update kbList counts
      const kb = kbList.value.find(k => k.id === kbId)
      if (kb) {
        kb.document_count = 0
        kb.paragraph_count = 0
        kb.char_length = 0
      }
    } catch (e) {
      // V2 failed, try V1
      await documentsApi.clearAll()
      documents.value = []
      totalDocs.value = 0
      kbList.value = []
    }
  }

  async function deleteKB(kbId) {
    // Delete KB and all its documents
    try {
      await documentsV2Api.deleteKB(kbId)
      kbList.value = kbList.value.filter(kb => kb.id !== kbId)
      documents.value = []
      totalDocs.value = 0
    } catch (e) {
      // V2 failed, try V1 clear-all
      await documentsApi.clearAll()
      kbList.value = []
      documents.value = []
      totalDocs.value = 0
    }
  }

  async function createKB(name, description = '') {
    try {
      const res = await documentsV2Api.createKB(name, description)
      const newKB = res.data
      kbList.value.push({
        id: newKB.id,
        name: newKB.name,
        description: newKB.description || '',
        document_count: 0,
        paragraph_count: 0,
        char_length: 0,
      })
      return { success: true, kb: newKB }
    } catch (e) {
      console.error('Failed to create KB:', e)
      return { success: false, error: e }
    }
  }

  return {
    stats, kbList, documents, totalDocs, totalCharLength,
    currentPage, pageSize, loading, selectedDocIds, tags,
    totalChunks,
    fetchStats, fetchKBList, fetchDocuments,
    uploadDocument, deleteDocument, batchDelete,
    toggleSelectDoc, selectAll,
    clearKB, deleteKB, createKB,
  }
})
