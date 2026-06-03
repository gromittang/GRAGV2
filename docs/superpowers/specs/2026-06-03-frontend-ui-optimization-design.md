# 前端UI优化设计方案

## 概述

基于superdesign设计草案，对WMS RAG V2前端进行UI优化改进。保留侧边栏布局，根据实际后端功能实现，后端配合改动同步进行。

## 设计决策记录

| 决策项 | 选择 | 日期 |
|--------|------|------|
| 侧边栏 | 保留 | 2026-06-03 |
| 实现策略 | 根据后端功能，不强求演示画面所有元素 | 2026-06-03 |
| 知识库卡片颜色 | 单色鲜明背景（B方案） | 2026-06-03 |
| PM时间轴样式 | 水平时间轴，圆点+连线（A方案） | 2026-06-03 |
| 悬浮窗位置 | 随机偏移，避免重叠（B方案） | 2026-06-03 |
| 悬浮窗尺寸 | 固定尺寸，后续根据字段调整 | 2026-06-03 |
| MD解析范围 | 完整支持，含表格/引用块/图片/任务列表（B方案） | 2026-06-03 |

---

## 一、总体改动

### 1.1 文本对比度提升

| 场景 | 当前颜色 | 改进颜色 |
|------|----------|----------|
| 灰色背景提示文本 | `text-primary/30` (#334155 30%透明) | `text-primary/60` (#334155 60%透明) |
| 灰色背景描述文本 | `text-primary/40` | `text-primary/70` 或 `text-slate-600` |
| 空状态提示 | `text-grid` (#E2E8F0) | `text-slate-500` (#64748B) |

### 1.2 全中文界面

| 文件 | 当前英文 | 改为中文 |
|------|----------|----------|
| `StatsBento.vue` | Total Documents, Indexed Docs, Total Chunks, Total Characters | 文档总计, 已索引文档, 累计片段, 累计字符 |
| `KBCard.vue` | DOCUMENTS, CHUNKS | 文档数, 片段数 |
| `ChatInput.vue` | Enter发送提示 | 保持中文（已中文） |
| `SchemaBrowser.vue` | Database Schema, Load Schema | 数据库结构, 加载结构 |

---

## 二、智能问答（ChatPage）

### 2.1 Markdown解析

**文件**: `src/components/chat/ChatMessage.vue`

**实现方案**:
```javascript
import { marked } from 'marked'
import { gfmHeadingId } from 'marked-gfm-heading-id'

// 配置marked支持GFM扩展（表格、任务列表等）
marked.use(gfmHeadingId())

// 安全配置：防止XSS
marked.setOptions({
  headerIds: false,
  mangle: false
})

// 解析并渲染
const renderedContent = computed(() => {
  return marked.parse(props.content || '')
})
```

**支持的MD元素**:
- 标题 (h1-h6)
- 列表（有序、无序）
- 粗体/斜体
- 代码块（带语法高亮建议）
- 链接
- 表格（GFM）
- 引用块
- 图片
- 任务列表（GFM checkbox）

**样式配置**:
```css
/* 添加到ChatMessage.vue的scoped style */
.message-md-content {
  line-height: 1.7;
}
.message-md-content h3 { font-size: 16px; font-weight: 600; }
.message-md-content code { background: #f3f4f6; padding: 2px 6px; }
.message-md-content pre { background: #1f2937; color: #e5e7eb; padding: 12px; }
.message-md-content table { width: 100%; border-collapse: collapse; }
.message-md-content th, .message-md-content td { border: 1px solid #d1d5db; padding: 8px; }
```

### 2.2 输入框与按钮对齐

**文件**: `src/components/chat/ChatInput.vue`

**当前问题**: 输入框textarea高度动态变化，发送按钮固定h-10，不对齐。

**改进方案**:
```html
<div class="flex items-end gap-3">
  <textarea class="flex-1 min-h-[44px] max-h-[160px]" ...></textarea>
  <button class="h-[44px] px-5 ...">发送</button>
</div>
```

统一高度为44px，textarea最小高度44px与按钮匹配。

### 2.3 聊天记录滚动

**当前状态**: `ChatView.vue`已有`scrollRef`和`scrollToBottom()`函数，已实现自动滚动。

**验证点**: 确认overflow-y-auto正确工作，无需额外改动。

---

## 三、知识库（KnowledgePage）

### 3.1 统计卡片颜色

**文件**: `src/components/knowledge/StatsBento.vue`

**颜色方案**（单色鲜明背景）:

| 卡片 | 背景色 | 文字色 | 原标签 | 新标签 |
|------|--------|--------|--------|--------|
| 知识库总数 | `#3B82F6` 蓝 | `#FFFFFF` 白 | - | 新增卡片 |
| 文档总计 | `#10B981` 绿 | `#FFFFFF` 白 | Total Documents | 文档总计 |
| 累计片段 | `#F59E0B` 橙 | `#FFFFFF` 白 | Total Chunks | 累计片段 |
| 累计字符 | `#8B5CF6` 紫 | `#FFFFFF` 白 | Total Characters | 累计字符 |

**布局调整**:
```html
<div class="grid grid-cols-2 md:grid-cols-4 gap-px">
  <div v-for="card in cards" :key="card.label"
    class="p-8 text-white"
    :style="{ backgroundColor: card.color }">
    <div class="text-4xl font-bold">{{ card.displayValue }}</div>
    <div class="text-sm opacity-90">{{ card.label }}</div>
  </div>
</div>
```

### 3.2 知识库卡片间距

**文件**: `src/components/knowledge/KBCardGrid.vue`

**改动**: `gap-4` → `gap-6`

```html
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
```

### 3.3 知识库卡片中文标签

**文件**: `src/components/knowledge/KBCard.vue`

```html
<!-- 改动 -->
<div class="flex items-center gap-6 font-mono text-[11px] text-white/80">
  <span>{{ kb.document_count || docCount }} 文档数</span>
  <span>{{ kb.paragraph_count || chunkCount }} 片段数</span>
</div>
```

---

## 四、PM方案工作室（PMStudioPage）

### 4.1 时间轴布局

**改动**: 将左侧流程卡片移至页面顶部，使用水平时间轴。

**新组件**: `src/components/pm/TimelineStepper.vue`

**布局结构**:
```
+--------------------------------------------------+
| [头部 Header]                                      |
+--------------------------------------------------+
| ○───────○───────○───────○                        |
| 问题定义  方案分析  方案细化  PRD生成               |
|   ✓        ✓       ●                            |
+--------------------------------------------------+
| [主内容区域 - 方案内容、输入框等]                    |
+--------------------------------------------------+
```

**时间轴组件设计**:

```html
<template>
  <div class="flex items-center justify-center py-6 px-8 bg-warm-gray/30 border-b border-grid">
    <div class="flex items-center gap-0">
      <template v-for="(phase, index) in phases" :key="phase.key">
        <!-- 阶段节点 -->
        <div class="flex flex-col items-center relative">
          <!-- 圆点 -->
          <div
            class="w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all"
            :class="getNodeClass(index)">
            <Icon v-if="isCompleted(index)" icon="lucide:check" class="text-lg" />
            <span v-else class="font-bold">{{ index + 1 }}</span>
          </div>
          <!-- 标签 -->
          <span class="mt-2 text-sm font-medium" :class="getLabelClass(index)">
            {{ phase.label }}
          </span>
          <!-- 状态描述 -->
          <span class="text-xs text-primary/50">{{ getStatusText(index) }}</span>
        </div>
        <!-- 连线 -->
        <div v-if="index < phases.length - 1"
          class="w-24 h-0.5 mx-2"
          :class="getLineColor(index)">
        </div>
      </template>
    </div>
  </div>
</template>
```

**样式配置**:

| 状态 | 圆点样式 | 连线样式 | 标签样式 |
|------|----------|----------|----------|
| 已完成 | `bg-green-500 border-green-500 text-white` | `bg-green-500` | `text-green-600` |
| 当前 | `bg-accent-orange border-accent-orange text-white ring-4 ring-accent-orange/20` | `bg-grid` | `text-accent-orange font-bold` |
| 未到达 | `bg-white border-grid text-primary/40` | `bg-grid` | `text-primary/40` |

**时间轴高度**: 80px（不影响主内容区空间）

### 4.2 状态同步

时间轴组件通过props接收状态，不直接修改：

```javascript
const props = defineProps({
  phases: Array,           // [{key, label}]
  currentPhase: String,    // 当前阶段key
  phaseStatuses: Object,   // {problem: 'confirmed', analysis: 'generated', ...}
})

const emit = defineEmits(['select-phase'])  // 点击历史阶段时触发回溯
```

---

## 五、数据查询（QueryPage）

### 5.1 Schema搜索功能

**前端**: `src/components/query/SchemaBrowser.vue`

**新增搜索框**:
```html
<div class="p-4 border-b border-grid">
  <input
    v-model="searchQuery"
    placeholder="搜索表名或注释..."
    class="w-full px-3 py-2 border border-grid rounded text-sm focus:border-accent-orange"
  />
</div>
```

**后端API**: `/query/schema/search`

**请求**:
```
GET /query/schema/search?q=库存&limit=10
```

**响应**:
```json
{
  "tables": [
    {
      "name": "tstock",
      "display_name": "库存表",
      "description": "库存明细数据",
      "match_type": "table_name"
    }
  ],
  "columns": [
    {
      "table_name": "tstock",
      "column_name": "stock_qty",
      "display_name": "库存数量",
      "match_type": "column_desc"
    }
  ]
}
```

### 5.2 表字段详情API

**后端API**: `/query/schema/table/{table_name}/fields`

**响应**:
```json
{
  "table_name": "tstock",
  "display_name": "库存表",
  "description": "库存明细数据",
  "columns": [
    {
      "column_name": "stock_qty",
      "display_name": "库存数量",
      "data_type": "DECIMAL",
      "data_length": 10,
      "description": "当前库存量，单位为件"
    }
  ]
}
```

**数据来源**: 复用现有 `db_mysql.get_schema_columns(table_name)` 方法。

### 5.3 悬浮窗组件

**新组件**: `src/components/query/FloatingWindow.vue`

**功能**:
- 可拖动（标题栏拖动）
- 可关闭（右上角X按钮）
- 固定尺寸 400×320px
- 随机偏移避免重叠

**Props**:
```javascript
{
  tableInfo: Object,    // 表信息
  columns: Array,       // 字段列表
  initialX: Number,     // 初始X位置
  initialY: Number,     // 初始Y位置
  zIndex: Number,       // 层级
}
```

**样式**:
```css
.floating-window {
  position: fixed;
  width: 400px;
  height: 320px;
  background: white;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.15);
  overflow: hidden;
}
.floating-window-header {
  height: 40px;
  background: #F1F5F9;
  cursor: move;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
}
```

**随机偏移逻辑**:
```javascript
// 在QueryPage.vue中管理多个悬浮窗
const floatingWindows = ref([])
const baseOffset = { x: 100, y: 150 }

function openTableWindow(tableName) {
  const windowCount = floatingWindows.value.length
  const offset = {
    x: baseOffset.x + windowCount * 30,
    y: baseOffset.y + windowCount * 30
  }
  floatingWindows.value.push({
    id: `${tableName}-${Date.now()}`,
    tableName,
    x: offset.x,
    y: offset.y,
    zIndex: 100 + windowCount
  })
}
```

**z-index管理**: 每次点击窗口时将其zIndex提升到最高。

---

## 六、后端改动清单

### 6.1 query.py 新增端点

```python
@router.get("/schema/search")
async def search_schema(
    q: str = QueryParam(default="", min_length=1),
    limit: int = QueryParam(default=10, ge=1, le=50)
):
    """搜索表名和字段注释"""
    service = get_query_service()
    result = await service.search_schema(q, limit)
    return result

@router.get("/schema/table/{table_name}/fields")
async def get_table_fields(table_name: str):
    """获取表字段详情"""
    service = get_query_service()
    result = await service.get_table_fields(table_name)
    return result
```

### 6.2 query_service.py 新增方法

```python
async def search_schema(self, query: str, limit: int = 10) -> Dict:
    """搜索Schema（表名/注释/字段）"""
    schema_manager = await get_schema_manager()
    results = schema_manager.search_schema(query, limit)
    return {
        "tables": results.get("tables", []),
        "columns": results.get("columns", []),
        "session_id": self._session_id
    }

async def get_table_fields(self, table_name: str) -> Dict:
    """获取表的完整字段信息"""
    mysql_manager = await get_mysql_manager()
    columns = await mysql_manager.get_schema_columns(table_name)
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

---

## 七、依赖确认

### 7.1 前端依赖（已安装）

| 依赖 | 版本 | 用途 | 状态 |
|------|------|------|------|
| `marked` | 15.0.12 | Markdown解析 | ✅ 已安装 |
| `tailwindcss` | 3.4.19 | CSS框架 | ✅ 已安装 |

### 7.2 后端依赖（已具备）

| 依赖 | 状态 |
|------|------|
| `aiomysql` | ✅ 已安装 |
| `get_schema_columns()` | ✅ 已有方法 |
| `get_schema_tables()` | ✅ 已有方法 |

---

## 八、实施顺序

```
Phase 1: 前端基础改动（无需后端配合）
├── 1.1 StatsBento.vue 颜色和中文
├── 1.2 KBCardGrid.vue 间距gap-6
├── 1.3 KBCard.vue 中文标签
├── 1.4 ChatMessage.vue MD解析
├── 1.5 ChatInput.vue 高度对齐
└── 1.6 文本对比度提升（各文件）

Phase 2: 前端新组件
├── 2.1 TimelineStepper.vue 时间轴组件
├── 2.2 PMStudioPage.vue 集成时间轴
├── 2.3 FloatingWindow.vue 悬浮窗组件
└── 2.4 SchemaBrowser.vue 搜索框

Phase 3: 后端API
├── 3.1 query.py 新增端点
├── 3.2 query_service.py 新增方法
└── 3.3 schema_manager.py 搜索方法

Phase 4: 集成与测试
├── 4.1 QueryPage.vue 集成悬浮窗
├── 4.2 测试各页面功能
└── 4.3 验证MD解析安全性
```

---

## 九、风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| MD内容XSS风险 | 使用marked安全配置，不渲染script标签 |
| 悬浮窗拖动性能 | 使用CSS transform，避免频繁重绘 |
| 时间轴响应式 | 小屏幕时缩减连线宽度或垂直布局 |
| 多悬浮窗内存 | 设置最大窗口数量限制（如5个） |

---

## 十、验收标准

| 功能 | 验收标准 |
|------|----------|
| MD解析 | 正确显示表格、代码块、列表、标题 |
| 输入框对齐 | 输入框与发送按钮高度一致(44px) |
| 统计卡片 | 4色鲜明背景，中文标签，白色文字 |
| 时间轴 | 4阶段水平排列，当前阶段高亮 |
| 悬浮窗 | 可拖动、可关闭、显示字段详情 |
| Schema搜索 | 输入关键词可搜索表名和注释 |