<template>
  <div class="flex-1 flex flex-col bg-paper overflow-hidden">
    <!-- Header -->
    <header class="h-20 hairline-b flex items-center px-12 sticky top-0 bg-paper z-40">
      <div class="flex items-center gap-4">
        <h1 class="font-space text-2xl font-bold text-primary tracking-tight">系统设置</h1>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto px-12 py-10">
      <div class="max-w-2xl space-y-6">

        <!-- LLM Config -->
        <section class="border border-grid bg-surface">
          <div class="h-12 hairline-b flex items-center px-6 bg-warm-gray">
            <div class="flex items-center gap-3">
              <Icon icon="lucide:brain" class="text-accent-orange text-lg" />
              <span class="font-space text-[14px] font-bold text-primary">LLM 配置</span>
            </div>
          </div>
          <div class="p-6 space-y-4">
            <div>
              <label class="block font-mono text-[10px] uppercase text-primary/40 mb-1.5 tracking-wider">API Base URL</label>
              <input
                v-model="llm.baseUrl"
                class="w-full h-9 bg-warm-gray border border-grid px-3 text-[13px] text-primary focus:outline-none focus:border-accent-orange/40 transition-colors font-mono"
                placeholder="https://api.deepseek.com/v1"
              />
            </div>
            <div>
              <label class="block font-mono text-[10px] uppercase text-primary/40 mb-1.5 tracking-wider">API Key</label>
              <input
                v-model="llm.apiKey"
                type="password"
                class="w-full h-9 bg-warm-gray border border-grid px-3 text-[13px] text-primary focus:outline-none focus:border-accent-orange/40 transition-colors font-mono"
                placeholder="sk-..."
              />
            </div>
            <div>
              <label class="block font-mono text-[10px] uppercase text-primary/40 mb-1.5 tracking-wider">Model Name</label>
              <input
                v-model="llm.model"
                class="w-full h-9 bg-warm-gray border border-grid px-3 text-[13px] text-primary focus:outline-none focus:border-accent-orange/40 transition-colors"
                placeholder="deepseek-chat"
              />
            </div>
          </div>
        </section>

        <!-- Database Status -->
        <section class="border border-grid bg-surface">
          <div class="h-12 hairline-b flex items-center px-6 bg-warm-gray">
            <div class="flex items-center gap-3">
              <Icon icon="lucide:database" class="text-accent-green text-lg" />
              <span class="font-space text-[14px] font-bold text-primary">知识库状态</span>
            </div>
          </div>
          <div class="p-6 space-y-4">
            <div class="flex items-center justify-between">
              <span class="text-[13px] text-primary/70">SQLite 数据库</span>
              <span class="flex items-center gap-2 font-mono text-[12px] font-bold text-accent-green">
                <span class="w-2 h-2 bg-accent-green"></span>
                正常运行
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-[13px] text-primary/70">BM25 索引</span>
              <span class="flex items-center gap-2 font-mono text-[12px] font-bold" :class="bm25Available ? 'text-accent-green' : 'text-red-500'">
                <span class="w-2 h-2" :class="bm25Available ? 'bg-accent-green' : 'bg-red-500'"></span>
                {{ bm25Available ? `已索引 (${bm25Docs} 条)` : '未初始化' }}
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-[13px] text-primary/70">检索模式</span>
              <span class="font-mono text-[12px] text-accent-orange">BM25 关键词检索</span>
            </div>
          </div>
        </section>

        <!-- MySQL Config -->
        <section class="border border-grid bg-surface">
          <div class="h-12 hairline-b flex items-center px-6 bg-warm-gray">
            <div class="flex items-center gap-3">
              <Icon icon="lucide:server" class="text-teal text-lg" />
              <span class="font-space text-[14px] font-bold text-primary">MySQL 配置</span>
            </div>
          </div>
          <div class="p-6 space-y-4">
            <div class="flex items-center justify-between">
              <span class="text-[13px] text-primary/70">数据库连接状态</span>
              <button
                @click="testMysql"
                class="px-3 h-7 border border-grid text-[11px] text-primary/40 hover:text-accent-orange transition-colors font-mono"
              >
                {{ mysqlTesting ? '测试中...' : (mysqlOk === null ? '测试连接' : (mysqlOk ? '已连接' : '连接失败')) }}
              </button>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block font-mono text-[10px] uppercase text-primary/40 mb-1.5 tracking-wider">Host</label>
                <input
                  v-model="mysql.host"
                  class="w-full h-9 bg-warm-gray border border-grid px-3 text-[13px] text-primary focus:outline-none focus:border-accent-orange/40 transition-colors"
                  placeholder="localhost"
                />
              </div>
              <div>
                <label class="block font-mono text-[10px] uppercase text-primary/40 mb-1.5 tracking-wider">Port</label>
                <input
                  v-model="mysql.port"
                  class="w-full h-9 bg-warm-gray border border-grid px-3 text-[13px] text-primary focus:outline-none focus:border-accent-orange/40 transition-colors"
                  placeholder="3306"
                />
              </div>
            </div>
          </div>
        </section>

        <!-- System Version -->
        <section class="border border-grid bg-surface">
          <div class="h-12 hairline-b flex items-center px-6 bg-warm-gray">
            <div class="flex items-center gap-3">
              <Icon icon="lucide:info" class="text-primary/40 text-lg" />
              <span class="font-space text-[14px] font-bold text-primary">系统信息</span>
            </div>
          </div>
          <div class="p-6 space-y-3">
            <div class="flex items-center justify-between">
              <span class="text-[13px] text-primary/70">系统版本</span>
              <span class="font-mono text-[12px] text-primary/40">WMS Knowledge Base v1.0</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-[13px] text-primary/70">LLM 提供商</span>
              <span class="font-mono text-[12px] text-primary/40">DeepSeek</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-[13px] text-primary/70">前端框架</span>
              <span class="font-mono text-[12px] text-primary/40">Vue 3 + Vite</span>
            </div>
          </div>
        </section>

        <!-- Dangerous zone -->
        <section class="border border-red-200 bg-red-50/30">
          <div class="h-12 hairline-b flex items-center px-6 bg-red-50/50">
            <div class="flex items-center gap-3">
              <Icon icon="lucide:alert-triangle" class="text-red-600 text-lg" />
              <span class="font-space text-[14px] font-bold text-red-700">危险操作</span>
            </div>
          </div>
          <div class="p-6">
            <p class="text-[12px] text-red-600/70 mb-4">以下操作不可撤销，请谨慎操作。</p>
            <button
              @click="showClearConfirm = true"
              class="px-4 h-9 border border-red-300 text-red-600 text-[13px] font-medium hover:bg-red-100 transition-colors"
            >
              清空向量库
            </button>
          </div>
        </section>

      </div>
    </div>

    <!-- Confirm Dialog -->
    <ConfirmDialog
      :visible="showClearConfirm"
      title="清空向量库"
      message="此操作将删除所有向量数据和文档索引，已上传的源文件不受影响。确定要继续吗？"
      confirm-text="清空"
      @confirm="handleClearVectorDB"
      @cancel="showClearConfirm = false"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import chatApi from '../api/chat'
import queryApi from '../api/query'
import ConfirmDialog from '../components/common/ConfirmDialog.vue'

const showClearConfirm = ref(false)
const chromaOnline = ref(null)
const mysqlOk = ref(null)
const mysqlTesting = ref(false)
const bm25Available = ref(false)
const bm25Docs = ref(0)

const llm = ref({
  baseUrl: '',
  apiKey: '',
  model: '',
})

const mysql = ref({
  host: 'localhost',
  port: '3306',
})

onMounted(async () => {
  // 获取知识库状态
  try {
    const res = await chatApi.status()
    const info = res.data
    // 从info中提取BM25状态
    if (info.bm25_stats) {
      bm25Available.value = info.bm25_stats.initialized || false
      bm25Docs.value = info.bm25_stats.total_docs || 0
    }
    chromaOnline.value = info.status === 'ready'
  } catch (e) {
    console.error('Failed to fetch status:', e)
  }
})

async function testMysql() {
  mysqlTesting.value = true
  try {
    const res = await queryApi.testConnection()
    mysqlOk.value = res.data.ok || res.data.connected || true
  } catch (e) {
    mysqlOk.value = false
  } finally {
    mysqlTesting.value = false
  }
}

async function handleClearVectorDB() {
  try {
    await chatApi.clear()
    showClearConfirm.value = false
    // 刷新状态
    bm25Available.value = false
    bm25Docs.value = 0
  } catch (e) {
    console.error('Clear failed:', e)
  }
}
</script>
