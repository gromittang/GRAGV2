# 前端UI优化 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 对WMS RAG V2前端进行UI优化，包括MD解析、统计卡片颜色、时间轴布局、悬浮窗等改进。

**架构：** 前端Vue组件修改为主，后端新增两个API端点配合。保留现有侧边栏，改动集中在主内容区。

**技术栈：** Vue 3 + Tailwind CSS + marked (MD解析) + FastAPI (后端)

---

## 文件结构

### 创建文件
| 文件 | 职责 |
|------|------|
| `frontend/vue-app/src/components/pm/TimelineStepper.vue` | PM工作室顶部时间轴组件 |
| `frontend/vue-app/src/components/query/FloatingWindow.vue` | 数据查询悬浮窗组件 |
| `frontend/vue-app/src/api/schema.js` | Schema搜索和字段详情API调用 |

### 修改文件
| 文件 | 改动内容 |
|------|----------|
| `frontend/vue-app/src/components/knowledge/StatsBento.vue` | 统计卡片颜色方案、中文标签 |
| `frontend/vue-app/src/components/knowledge/KBCardGrid.vue` | 卡片间距gap-6 |
| `frontend/vue-app/src/components/knowledge/KBCard.vue` | 中文标签 |
| `frontend/vue-app/src/components/chat/ChatMessage.vue` | MD解析渲染 |
| `frontend/vue-app/src/components/chat/ChatInput.vue` | 输入框与按钮高度对齐 |
| `frontend/vue-app/src/components/query/SchemaBrowser.vue` | 搜索框、点击表名触发悬浮窗 |
| `frontend/vue-app/src/views/PMStudioPage.vue` | 集成时间轴组件 |
| `frontend/vue-app/src/views/QueryPage.vue` | 悬浮窗状态管理 |
| `backend/app/api/query.py` | 新增schema搜索和字段详情端点 |
| `backend/app/services/query_service.py` | 新增search_schema和get_table_fields方法 |
| `backend/app/core/schema_manager.py` | 新增search_schema方法 |

---

## Phase 1: 前端基础改动

### 任务 1：StatsBento.vue 统计卡片颜色和中文

**文件：**
- 修改：`frontend/vue-app/src/components/knowledge/StatsBento.vue`

- [ ] **步骤 1：修改卡片颜色方案**

将现有的左边框颜色改为背景色，添加白色文字。

```vue
<template>
  <div class="grid grid-cols-2 md:grid-cols-4 mb-10">
    <div
      v-for="(card, i) in cards"
      :key="i"
      class="p-8 text-white"
      :style="{ backgroundColor: card.color }"
    >
      <div class="font-space text-4xl font-bold mb-1 count-up">
        {{ card.displayValue }}
      </div>
      <div class="text-sm opacity-90">
        {{ card.label }}
      </div>
    </div>
  </div>
</template>
```

- [ ] **步骤 2：修改cards数据，更新颜色和中文标签**

```javascript
const cards = computed(() => [
  {
    label: '知识库总数',
    displayValue: displayValues.value.kb_count || '0',
    color: '#3B82F6',  // 蓝色
  },
  {
    label: '文档总计',
    displayValue: displayValues.value.uploaded || '0',
    color: '#10B981',  // 绿色
  },
  {
    label: '累计片段',
    displayValue: displayValues.value.chunks || '0',
    color: '#F59E0B',  // 橙色
  },
  {
    label: '累计字符',
    displayValue: displayValues.value.chars || '0',
    color: '#8B5CF6',  // 紫色
  },
])
```

- [ ] **步骤 3：添加kb_count统计**

```javascript
const computedStats = computed(() => {
  const kbList = store.kbList || []
  return {
    kb_count: kbList.length,  // 新增知识库数量
    uploaded_count: kbList.reduce((sum, kb) => sum + (kb.document_count || 0), 0),
    indexed_count: kbList.reduce((sum, kb) => sum + (kb.document_count || 0), 0),
    chunks: kbList.reduce((sum, kb) => sum + (kb.paragraph_count || 0), 0),
    chars: kbList.reduce((sum, kb) => sum + (kb.char_length || 0), 0),
  }
})

// 添加animateValue调用
watch(() => computedStats.value, (s) => {
  animateValue('kb_count', s.kb_count || 0)  // 新增
  animateValue('uploaded', s.uploaded_count || 0)
  animateValue('indexed', s.indexed_count || 0)
  animateValue('chunks', s.chunks || 0)
  animateValue('chars', s.chars || 0)
}, { immediate: true, deep: true })
```

- [ ] **步骤 4：Commit**

```bash
git add frontend/vue-app/src/components/knowledge/StatsBento.vue
git commit -m "feat(knowledge): 统计卡片使用鲜艳单色背景和中文标签"
```

---

### 任务 2：KBCardGrid.vue 卡片间距

**文件：**
- 修改：`frontend/vue-app/src/components/knowledge/KBCardGrid.vue`

- [ ] **步骤 1：修改gap值**

找到grid容器，将`gap-4`改为`gap-6`。

```vue
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
```

- [ ] **步骤 2：Commit**

```bash
git add frontend/vue-app/src/components/knowledge/KBCardGrid.vue
git commit -m "feat(knowledge): 知识库卡片间距调整为gap-6"
```

---

### 任务 3：KBCard.vue 中文标签

**文件：**
- 修改：`frontend/vue-app/src/components/knowledge/KBCard.vue`

- [ ] **步骤 1：修改底部统计标签为中文**

找到显示DOCUMENTS和CHUNKS的部分，改为中文。

```vue
<div class="flex items-center gap-6 font-mono text-[11px] text-primary/40">
  <span>{{ kb.document_count || docCount }} 文档数</span>
  <span>{{ kb.paragraph_count || chunkCount }} 片段数</span>
</div>
```

- [ ] **步骤 2：Commit**

```bash
git add frontend/vue-app/src/components/knowledge/KBCard.vue
git commit -m "feat(knowledge): 知识库卡片标签改为中文"
```

---

### 任务 4：ChatMessage.vue Markdown解析

**文件：**
- 修改：`frontend/vue-app/src/components/chat/ChatMessage.vue`

- [ ] **步骤 1：导入marked库**

```javascript
import { marked } from 'marked'
```

- [ ] **步骤 2：配置marked安全选项**

```javascript
// 配置marked，禁用headerIds和mangle防止XSS
marked.setOptions({
  headerIds: false,
  mangle: false
})
```

- [ ] **步骤 3：添加renderedContent计算属性**

```javascript
const renderedContent = computed(() => {
  if (!props.content) return ''
  // 只对assistant角色的消息进行MD解析
  if (props.role === 'user') return props.content
  return marked.parse(props.content)
})
```

- [ ] **步骤 4：修改模板使用v-html渲染**

```vue
<!-- Bubble内容区 -->
<div
  class="px-4 py-3 text-[14px] leading-relaxed"
  :class="role === 'user'
    ? 'bg-warm-gray text-primary'
    : 'bg-surface border border-grid border-l-[3px] border-l-accent-green'"
>
  <!-- 用户消息保持纯文本 -->
  <div v-if="role === 'user'" class="whitespace-pre-wrap break-words">{{ content }}</div>
  <!-- AI消息使用MD解析 -->
  <div v-else class="message-md-content prose prose-sm max-w-none" v-html="renderedContent"></div>
</div>
```

- [ ] **步骤 5：添加MD内容样式**

```css
<style scoped>
/* MD解析内容样式 */
.message-md-content {
  line-height: 1.7;
}
.message-md-content h1,
.message-md-content h2,
.message-md-content h3 {
  font-weight: 600;
  margin-top: 1em;
  margin-bottom: 0.5em;
}
.message-md-content h3 {
  font-size: 16px;
}
.message-md-content p {
  margin-bottom: 0.8em;
}
.message-md-content ul,
.message-md-content ol {
  margin-left: 1.5em;
  margin-bottom: 0.8em;
}
.message-md-content li {
  margin-bottom: 0.3em;
}
.message-md-content code {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 13px;
}
.message-md-content pre {
  background: #1f2937;
  color: #e5e7eb;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}
.message-md-content pre code {
  background: none;
  padding: 0;
}
.message-md-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.8em 0;
}
.message-md-content th,
.message-md-content td {
  border: 1px solid #d1d5db;
  padding: 8px 12px;
}
.message-md-content th {
  background: #f3f4f6;
  font-weight: 600;
}
.message-md-content blockquote {
  border-left: 3px solid #d1d5db;
  padding-left: 1em;
  color: #64748b;
}
.message-md-content a {
  color: #EA580C;
  text-decoration: underline;
}
.message-md-content img {
  max-width: 100%;
  border-radius: 4px;
}
</style>
```

- [ ] **步骤 6：Commit**

```bash
git add frontend/vue-app/src/components/chat/ChatMessage.vue
git commit -m "feat(chat): AI回复支持Markdown格式解析"
```

---

### 任务 5：ChatInput.vue 高度对齐

**文件：**
- 修改：`frontend/vue-app/src/components/chat/ChatInput.vue`

- [ ] **步骤 1：统一输入框和按钮高度为44px**

```vue
<div class="max-w-3xl mx-auto flex items-end gap-3">
  <textarea
    ref="textareaRef"
    v-model="text"
    class="flex-1 resize-none bg-warm-gray border border-grid px-4 py-3 text-[14px] text-primary placeholder:text-primary/30 focus:outline-none focus:border-accent-orange/40 transition-colors min-h-[44px] max-h-[160px]"
    rows="1"
    :placeholder="placeholder"
    :disabled="disabled"
    @keydown.enter.exact.prevent="handleSend"
    @input="autoResize"
  ></textarea>
  <button
    @click="handleSend"
    :disabled="!text.trim() || disabled"
    class="h-[44px] px-5 bg-accent-orange text-white text-[13px] font-medium hover:bg-accent-orange/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center"
  >
    <span v-if="!loading">发送</span>
    <span v-else class="inline-flex items-center gap-1.5">
      <span class="w-2 h-2 bg-white animate-pulse-dot"></span>
      处理中
    </span>
  </button>
</div>
```

- [ ] **步骤 2：调整autoResize函数**

```javascript
function autoResize() {
  nextTick(() => {
    const el = textareaRef.value
    if (el) {
      el.style.height = 'auto'
      // 最小44px，最大160px
      el.style.height = Math.max(44, Math.min(el.scrollHeight, 160)) + 'px'
    }
  })
}
```

- [ ] **步骤 3：Commit**

```bash
git add frontend/vue-app/src/components/chat/ChatInput.vue
git commit -m "feat(chat): 输入框与发送按钮高度统一为44px"
```

---

## Phase 2: 前端新组件

### 任务 6：创建TimelineStepper.vue时间轴组件

**文件：**
- 创建：`frontend/vue-app/src/components/pm/TimelineStepper.vue`

- [ ] **步骤 1：创建组件目录**

```bash
mkdir -p frontend/vue-app/src/components/pm
```

- [ ] **步骤 2：编写TimelineStepper.vue完整代码**

```vue
<template>
  <div class="flex items-center justify-center py-6 px-8 bg-warm-gray/30 border-b border-grid">
    <div class="flex items-center">
      <template v-for="(phase, index) in phases" :key="phase.key">
        <!-- 阶段节点 -->
        <div
          class="flex flex-col items-center cursor-pointer"
          :class="canSelect(index) ? 'hover:opacity-80' : ''"
          @click="canSelect(index) && $emit('select-phase', phase.key)"
        >
          <!-- 圆点 -->
          <div
            class="w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all duration-200"
            :class="getNodeClass(index)"
          >
            <Icon v-if="isCompleted(index)" icon="lucide:check" class="text-lg text-white" />
            <Icon v-else-if="isGenerated(index)" icon="lucide:file-text" class="text-base text-blue-600" />
            <span v-else class="font-bold" :class="isCurrent(index) ? 'text-white' : 'text-primary/40'">{{ index + 1 }}</span>
          </div>
          <!-- 标签 -->
          <span
            class="mt-2 text-sm font-medium transition-colors"
            :class="getLabelClass(index)"
          >
            {{ phase.label }}
          </span>
          <!-- 状态描述 -->
          <span class="text-xs mt-0.5" :class="getStatusClass(index)">
            {{ getStatusText(index) }}
          </span>
        </div>
        <!-- 连线 -->
        <div
          v-if="index < phases.length - 1"
          class="w-20 h-0.5 mx-3 transition-colors"
          :class="getLineColor(index)"
        ></div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  phases: { type: Array, default: () => [] },
  currentPhase: { type: String, default: '' },
  phaseStatuses: { type: Object, default: () => {} },
})

defineEmits(['select-phase'])

const currentPhaseIndex = computed(() => {
  return props.phases.findIndex(p => p.key === props.currentPhase)
})

function isCompleted(index) {
  const phaseKey = props.phases[index]?.key
  return props.phaseStatuses[phaseKey] === 'confirmed'
}

function isGenerated(index) {
  const phaseKey = props.phases[index]?.key
  return props.phaseStatuses[phaseKey] === 'generated'
}

function isCurrent(index) {
  return index === currentPhaseIndex.value
}

function canSelect(index) {
  // 已完成或已生成的阶段可以选择（回溯）
  const phaseKey = props.phases[index]?.key
  const status = props.phaseStatuses[phaseKey]
  return status === 'confirmed' || status === 'generated'
}

function getNodeClass(index) {
  if (isCompleted(index)) {
    return 'bg-green-500 border-green-500'
  }
  if (isGenerated(index)) {
    return 'bg-blue-100 border-blue-500'
  }
  if (isCurrent(index)) {
    return 'bg-accent-orange border-accent-orange ring-4 ring-accent-orange/20'
  }
  return 'bg-white border-grid'
}

function getLabelClass(index) {
  if (isCompleted(index)) return 'text-green-600'
  if (isGenerated(index)) return 'text-blue-600'
  if (isCurrent(index)) return 'text-accent-orange font-bold'
  return 'text-primary/40'
}

function getStatusClass(index) {
  if (isCompleted(index)) return 'text-green-500/70'
  if (isGenerated(index)) return 'text-blue-500/70'
  if (isCurrent(index)) return 'text-accent-orange/70'
  return 'text-primary/30'
}

function getLineColor(index) {
  // 当前阶段之前的连线为绿色（已完成）
  if (isCompleted(index)) return 'bg-green-500'
  return 'bg-grid'
}

function getStatusText(index) {
  if (isCompleted(index)) return '已完成'
  if (isGenerated(index)) return '已生成'
  if (isCurrent(index)) return '进行中'
  return ''
}
</script>
```

- [ ] **步骤 3：Commit**

```bash
git add frontend/vue-app/src/components/pm/TimelineStepper.vue
git commit -m "feat(pm): 创建TimelineStepper时间轴组件"
```

---

### 任务 7：PMStudioPage.vue集成时间轴

**文件：**
- 修改：`frontend/vue-app/src/views/PMStudioPage.vue`

- [ ] **步骤 1：导入TimelineStepper组件**

```javascript
import TimelineStepper from '../components/pm/TimelineStepper.vue'
```

- [ ] **步骤 2：替换左侧流程卡片为顶部时间轴**

找到`<!-- Progress Sidebar - Card Style -->`部分，删除整个`<aside>`标签（约第31-98行）。

在header之后添加时间轴：

```vue
<!-- Header -->
<header class="h-20 ...">
  ...
</header>

<!-- Timeline Stepper -->
<TimelineStepper
  :phases="phases"
  :current-phase="currentPhase"
  :phase-statuses="phaseStatuses"
  @select-phase="rollbackTo"
/>

<!-- Main Content -->
<div class="flex-1 flex overflow-hidden">
  <!-- 删除原有的左侧aside -->
  <!-- Main Panel保持不变 -->
  <main class="flex-1 flex flex-col overflow-hidden p-8">
    ...
  </main>
</div>
```

- [ ] **步骤 3：调整main布局**

移除左侧sidebar后，main需要占满宽度：

```vue
<main class="flex-1 flex flex-col overflow-hidden p-8 max-w-5xl mx-auto">
```

- [ ] **步骤 4：Commit**

```bash
git add frontend/vue-app/src/views/PMStudioPage.vue
git commit -m "feat(pm-studio): 集成顶部时间轴替换左侧流程卡片"
```

---

### 任务 8：创建FloatingWindow.vue悬浮窗组件

**文件：**
- 创建：`frontend/vue-app/src/components/query/FloatingWindow.vue`

- [ ] **步骤 1：编写FloatingWindow.vue完整代码**

```vue
<template>
  <div
    ref="windowRef"
    class="floating-window"
    :style="{ left: `${x}px`, top: `${y}px`, zIndex }"
    @mousedown="bringToFront"
  >
    <!-- 标题栏（可拖动） -->
    <div
      class="floating-window-header"
      @mousedown="startDrag"
    >
      <span class="font-medium text-primary">{{ tableInfo.display_name || tableInfo.name }}</span>
      <button
        @click.stop="$emit('close')"
        class="text-primary/40 hover:text-primary transition-colors"
      >
        <Icon icon="lucide:x" class="text-lg" />
      </button>
    </div>
    <!-- 内容区 -->
    <div class="floating-window-content">
      <div v-if="loading" class="flex items-center justify-center h-full">
        <span class="text-primary/40">加载中...</span>
      </div>
      <div v-else-if="error" class="text-red-500 text-sm p-4">{{ error }}</div>
      <div v-else class="overflow-auto">
        <!-- 表描述 -->
        <div v-if="tableInfo.description" class="px-4 py-2 bg-warm-gray text-xs text-primary/60">
          {{ tableInfo.description }}
        </div>
        <!-- 字段列表 -->
        <table class="w-full text-sm">
          <thead class="bg-warm-gray sticky top-0">
            <tr>
              <th class="px-4 py-2 text-left text-primary/70 font-medium">字段名</th>
              <th class="px-4 py-2 text-left text-primary/70 font-medium">类型</th>
              <th class="px-4 py-2 text-left text-primary/70 font-medium">长度</th>
              <th class="px-4 py-2 text-left text-primary/70 font-medium">注释</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="col in columns"
              :key="col.column_name"
              class="border-b border-grid hover:bg-warm-gray/50"
            >
              <td class="px-4 py-2 font-mono text-primary">{{ col.column_name }}</td>
              <td class="px-4 py-2 text-primary/70">{{ col.data_type }}</td>
              <td class="px-4 py-2 text-primary/50">{{ col.data_length || '-' }}</td>
              <td class="px-4 py-2 text-primary/60">{{ col.display_name || col.description || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Icon } from '@iconify/vue'
import schemaApi from '../../api/schema'

const props = defineProps({
  tableInfo: { type: Object, required: true },
  initialX: { type: Number, default: 100 },
  initialY: { type: Number, default: 150 },
  zIndex: { type: Number, default: 100 },
})

const emit = defineEmits(['close', 'focus'])

const windowRef = ref(null)
const x = ref(props.initialX)
const y = ref(props.initialY)
const isDragging = ref(false)
const dragOffset = ref({ x: 0, y: 0 })

const loading = ref(false)
const error = ref('')
const columns = ref([])

onMounted(async () => {
  await loadFields()
})

async function loadFields() {
  loading.value = true
  error.value = ''
  try {
    const res = await schemaApi.getTableFields(props.tableInfo.name)
    columns.value = res.columns || []
  } catch (e) {
    error.value = '获取字段失败'
    console.error('Load fields failed:', e)
  } finally {
    loading.value = false
  }
}

function startDrag(e) {
  isDragging.value = true
  dragOffset.value = {
    x: e.clientX - x.value,
    y: e.clientY - y.value
  }
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
}

function onDrag(e) {
  if (!isDragging.value) return
  x.value = e.clientX - dragOffset.value.x
  y.value = e.clientY - dragOffset.value.y
  // 限制在窗口范围内
  x.value = Math.max(0, Math.min(x.value, window.innerWidth - 400))
  y.value = Math.max(0, Math.min(y.value, window.innerHeight - 320))
}

function stopDrag() {
  isDragging.value = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
}

function bringToFront() {
  emit('focus')
}
</script>

<style scoped>
.floating-window {
  position: fixed;
  width: 400px;
  height: 320px;
  background: white;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.15);
  overflow: hidden;
  user-select: none;
}
.floating-window-header {
  height: 40px;
  background: #F1F5F9;
  cursor: move;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  border-bottom: 1px solid #E2E8F0;
}
.floating-window-content {
  height: 280px;
  overflow: hidden;
}
</style>
```

- [ ] **步骤 2：Commit**

```bash
git add frontend/vue-app/src/components/query/FloatingWindow.vue
git commit -m "feat(query): 创建FloatingWindow悬浮窗组件"
```

---

### 任务 9：创建schema.js API调用

**文件：**
- 创建：`frontend/vue-app/src/api/schema.js`

- [ ] **步骤 1：编写API调用代码**

```javascript
import http from './index'

const schemaApi = {
  /**
   * 搜索Schema（表名/字段注释）
   */
  searchSchema: (query, limit = 10) => {
    return http.get(`/query/schema/search`, { params: { q: query, limit } })
  },

  /**
   * 获取表字段详情
   */
  getTableFields: (tableName) => {
    return http.get(`/query/schema/table/${tableName}/fields`)
  },
}

export default schemaApi
```

- [ ] **步骤 2：Commit**

```bash
git add frontend/vue-app/src/api/schema.js
git commit -m "feat(api): 创建schema搜索和字段详情API调用"
```

---

### 任务 10：SchemaBrowser.vue搜索框和悬浮窗触发

**文件：**
- 修改：`frontend/vue-app/src/components/query/SchemaBrowser.vue`

- [ ] **步骤 1：添加搜索框**

在组件顶部添加搜索框：

```vue
<template>
  <div class="border border-grid bg-surface">
    <!-- 搜索框 -->
    <div class="p-3 border-b border-grid">
      <input
        v-model="searchQuery"
        placeholder="搜索表名或注释..."
        class="w-full px-3 py-2 border border-grid rounded text-sm focus:border-accent-orange focus:outline-none"
        @input="onSearch"
      />
    </div>
    <!-- Header -->
    <div class="h-10 hairline-b flex items-center justify-between px-4">
      <span class="font-mono text-[10px] uppercase text-primary/40 tracking-wider">数据库结构</span>
      ...
    </div>
    ...
  </div>
</template>
```

- [ ] **步骤 2：添加搜索逻辑和emit**

```javascript
import { ref, computed } from 'vue'

const searchQuery = ref('')

// 过滤后的表列表
const filteredTables = computed(() => {
  if (!searchQuery.value.trim()) return props.schema?.tables || []
  const query = searchQuery.value.toLowerCase()
  return (props.schema?.tables || []).filter(table => {
    const name = (table.name || table.table_name || '').toLowerCase()
    const displayName = (table.display_name || '').toLowerCase()
    return name.includes(query) || displayName.includes(query)
  })
})

function onSearch() {
  // 可选：调用后端API搜索
}

// 点击表名时触发open-window事件
function onTableClick(tableName) {
  $emit('open-window', tableName)
}
```

- [ ] **步骤 3：修改表名点击为触发悬浮窗**

```vue
<button
  @click="onTableClick(table.name || table.table_name)"
  class="w-full h-9 hairline-b flex items-center justify-between px-4 hover:bg-warm-gray transition-colors text-left"
>
  <span class="font-mono text-[12px] font-bold text-primary">{{ table.name || table.table_name }}</span>
  <Icon icon="lucide:external-link" class="text-xs text-primary/30" />
</button>
```

- [ ] **步骤 4：添加emit定义**

```javascript
defineEmits(['load-schema', 'preview', 'open-window'])
```

- [ ] **步骤 5：使用filteredTables替换原来的schema.tables**

```vue
<div v-if="filteredTables.length > 0">
  <div
    v-for="table in filteredTables"
    :key="table.name || table.table_name"
    class="border-b border-grid last:border-0"
  >
    ...
  </div>
</div>
<div v-else-if="searchQuery && filteredTables.length === 0" class="p-4 text-center text-primary/40">
  未找到匹配的表
</div>
```

- [ ] **步骤 6：Commit**

```bash
git add frontend/vue-app/src/components/query/SchemaBrowser.vue
git commit -m "feat(query): SchemaBrowser添加搜索框和悬浮窗触发"
```

---

## Phase 3: 后端API

### 任务 11：query.py新增API端点

**文件：**
- 修改：`backend/app/api/query.py`

- [ ] **步骤 1：添加schema搜索端点**

```python
@router.get("/schema/search")
async def search_schema(
    q: str = QueryParam(default="", min_length=1),
    limit: int = QueryParam(default=10, ge=1, le=50)
):
    """
    搜索Schema（表名/注释/字段）
    
    支持按表名、表注释、字段名、字段注释搜索
    """
    service = get_query_service()
    result = await service.search_schema(q, limit)
    return result
```

- [ ] **步骤 2：添加表字段详情端点**

```python
@router.get("/schema/table/{table_name}/fields")
async def get_table_fields(table_name: str):
    """
    获取表的完整字段信息
    
    返回字段名、类型、长度、注释
    """
    service = get_query_service()
    result = await service.get_table_fields(table_name)
    return result
```

- [ ] **步骤 3：Commit**

```bash
git add backend/app/api/query.py
git commit -m "feat(api): 新增schema搜索和表字段详情API端点"
```

---

### 任务 12：query_service.py新增方法

**文件：**
- 修改：`backend/app/services/query_service.py`

- [ ] **步骤 1：添加search_schema方法**

```python
async def search_schema(self, query: str, limit: int = 10) -> Dict:
    """
    搜索Schema（表名/注释/字段）
    
    Args:
        query: 搜索关键词
        limit: 返回数量限制
        
    Returns:
        匹配的表和字段列表
    """
    mysql_manager = await get_mysql_manager()
    
    # 搜索表
    tables = await mysql_manager.get_schema_tables()
    matched_tables = []
    for table in tables:
        name = table.get("table_name", "")
        display_name = table.get("display_name", "")
        desc = table.get("description", "")
        if query.lower() in name.lower() or query.lower() in display_name.lower() or query.lower() in desc.lower():
            matched_tables.append({
                "name": name,
                "display_name": display_name,
                "description": desc,
                "match_type": "table"
            })
    
    # 搜索字段（仅搜索前limit个表，避免性能问题）
    matched_columns = []
    for table in matched_tables[:limit]:
        columns = await mysql_manager.get_schema_columns(table["name"])
        for col in columns:
            col_name = col.get("column_name", "")
            col_display = col.get("display_name", "")
            col_desc = col.get("description", "")
            if query.lower() in col_name.lower() or query.lower() in col_display.lower() or query.lower() in col_desc.lower():
                matched_columns.append({
                    "table_name": table["name"],
                    "column_name": col_name,
                    "display_name": col_display,
                    "data_type": col.get("data_type", ""),
                    "match_type": "column"
                })
    
    return {
        "tables": matched_tables[:limit],
        "columns": matched_columns[:limit],
        "session_id": self._session_id
    }
```

- [ ] **步骤 2：添加get_table_fields方法**

```python
async def get_table_fields(self, table_name: str) -> Dict:
    """
    获取表的完整字段信息
    
    Args:
        table_name: 表名
        
    Returns:
        表信息和字段列表
    """
    mysql_manager = await get_mysql_manager()
    
    # 获取字段
    columns = await mysql_manager.get_schema_columns(table_name)
    
    # 获取表信息
    tables = await mysql_manager.get_schema_tables()
    table_info = next((t for t in tables if t["table_name"] == table_name), None)
    
    return {
        "table_name": table_name,
        "display_name": table_info.get("display_name", table_name) if table_info else table_name,
        "description": table_info.get("description", "") if table_info else "",
        "columns": columns,
        "session_id": self._session_id
    }
```

- [ ] **步骤 3：Commit**

```bash
git add backend/app/services/query_service.py
git commit -m "feat(service): query_service新增search_schema和get_table_fields方法"
```

---

## Phase 4: 集成与测试

### 任务 13：QueryPage.vue集成悬浮窗管理

**文件：**
- 修改：`frontend/vue-app/src/views/QueryPage.vue`

- [ ] **步骤 1：导入FloatingWindow组件**

```javascript
import FloatingWindow from '../components/query/FloatingWindow.vue'
import schemaApi from '../api/schema'
```

- [ ] **步骤 2：添加悬浮窗状态管理**

```javascript
const floatingWindows = ref([])
const maxWindows = 5  // 最大窗口数限制
const baseOffset = { x: 100, y: 150 }

function openTableWindow(tableName) {
  // 限制窗口数量
  if (floatingWindows.value.length >= maxWindows) {
    floatingWindows.value.shift()  // 移除最早的窗口
  }
  
  const windowCount = floatingWindows.value.length
  const offset = {
    x: baseOffset.x + windowCount * 30,
    y: baseOffset.y + windowCount * 30
  }
  
  // 获取表信息
  const tables = store.schema?.tables || []
  const tableInfo = tables.find(t => t.name === tableName || t.table_name === tableName) || { name: tableName }
  
  floatingWindows.value.push({
    id: `${tableName}-${Date.now()}`,
    tableName,
    tableInfo,
    x: offset.x,
    y: offset.y,
    zIndex: 100 + windowCount
  })
}

function closeWindow(windowId) {
  floatingWindows.value = floatingWindows.value.filter(w => w.id !== windowId)
}

function focusWindow(windowId) {
  // 提升zIndex到最高
  const maxZ = Math.max(...floatingWindows.value.map(w => w.zIndex))
  const window = floatingWindows.value.find(w => w.id === windowId)
  if (window) {
    window.zIndex = maxZ + 1
  }
}
```

- [ ] **步骤 3：在模板中渲染悬浮窗**

```vue
<!-- 悬浮窗列表 -->
<FloatingWindow
  v-for="win in floatingWindows"
  :key="win.id"
  :table-info="win.tableInfo"
  :initial-x="win.x"
  :initial-y="win.y"
  :z-index="win.zIndex"
  @close="closeWindow(win.id)"
  @focus="focusWindow(win.id)"
/>
```

- [ ] **步骤 4：修改SchemaBrowser事件处理**

```vue
<SchemaBrowser
  :schema="store.schema"
  :connection-ok="store.connectionOk"
  @load-schema="store.fetchSchema()"
  @preview="store.previewTable($event)"
  @open-window="openTableWindow($event)"
/>
```

- [ ] **步骤 5：Commit**

```bash
git add frontend/vue-app/src/views/QueryPage.vue
git commit -m "feat(query): QueryPage集成悬浮窗管理，支持多窗口"
```

---

### 任务 14：文本对比度提升（各文件）

**文件：**
- 修改：多个前端组件文件

- [ ] **步骤 1：修改EmptyState.vue**

找到`text-grid`改为`text-slate-500`：

```vue
<p class="text-[14px] text-slate-500">...</p>
<p class="text-[11px] text-slate-400 mt-1">...</p>
```

- [ ] **步骤 2：修改ChatView.vue空状态**

```vue
<p class="text-[15px] text-slate-600 font-medium mb-2">智能问答</p>
<p class="text-[13px] text-slate-500 leading-relaxed">...</p>
```

- [ ] **步骤 3：修改SchemaBrowser.vue**

```vue
<span class="font-mono text-[10px] uppercase text-slate-500 tracking-wider">数据库结构</span>
```

- [ ] **步骤 4：修改QueryPage.vue空状态**

```vue
<p class="text-[14px] text-slate-500">使用自然语言查询 WMS 数据库</p>
<p class="text-[11px] text-slate-400 mt-1">仅支持 SELECT 查询，确保数据安全</p>
```

- [ ] **步骤 5：Commit**

```bash
git add frontend/vue-app/src/components/common/EmptyState.vue \
        frontend/vue-app/src/components/chat/ChatView.vue \
        frontend/vue-app/src/components/query/SchemaBrowser.vue \
        frontend/vue-app/src/views/QueryPage.vue
git commit -m "feat: 提升各组件文本对比度，改善可读性"
```

---

### 任务 15：最终验证与提交

- [ ] **步骤 1：启动前端开发服务器验证**

```bash
cd frontend/vue-app && npm run dev
```

验证点：
- 知识库页面统计卡片颜色是否正确（蓝/绿/橙/紫）
- 知识库卡片间距是否增加
- 智能问答MD解析是否正常（表格、代码块、列表）
- PM工作室时间轴是否显示在顶部
- 数据查询搜索框是否工作
- 数据查询悬浮窗是否可拖动、可关闭

- [ ] **步骤 2：启动后端验证API**

```bash
cd backend && python -m uvicorn app.main:app --reload
```

测试API：
```bash
curl http://localhost:8812/query/schema/search?q=库存
curl http://localhost:8812/query/schema/table/tstock/fields
```

- [ ] **步骤 3：最终commit汇总**

```bash
git add -A
git commit -m "feat: 前端UI优化完成

- 知识库统计卡片鲜艳单色背景和中文标签
- 知识库卡片间距gap-6
- 智能问答AI回复Markdown解析支持
- 智能问答输入框与按钮高度对齐44px
- PM工作室顶部水平时间轴布局
- 数据查询Schema搜索框
- 数据查询悬浮窗组件（可拖动/关闭）
- 后端schema搜索和字段详情API
- 各组件文本对比度提升

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
git push
```

---

## 验收清单

| 功能 | 验收标准 | 验证方式 |
|------|----------|----------|
| MD解析 | 表格、代码块、列表正确显示 | 发送含MD的测试消息 |
| 输入框对齐 | 高度44px一致 | 视觉检查 |
| 统计卡片 | 蓝/绿/橙/紫背景，白色文字 | 视觉检查 |
| 时间轴 | 4阶段水平排列，当前高亮 | 进入PM页面检查 |
| 悬浮窗 | 可拖动、可关闭、多窗口 | 点击表名测试 |
| Schema搜索 | 输入关键词有结果 | 输入测试 |
| 文本对比度 | 灰色背景文本清晰可读 | 视觉检查 |