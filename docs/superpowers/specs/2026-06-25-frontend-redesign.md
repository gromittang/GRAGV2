# 前端重设计 Spec — WMS Knowledge 企业数据智能平台

> **日期**: 2026-06-25
> **状态**: 设计确认
> **原型**: `prototype/design-preview.html`
> **关联**: [[ADR-010 MCP Data Copilot]], [[Phase 2 架构]]

---

## 1. 背景与目标

### 1.1 为什么做

当前前端功能完整，但视觉呈现偏"内部工具"风格，在面试等正式场景下无法充分展现系统的专业感。本次重设计目标：

- **不破坏任何现有功能** — 仅修改样式层（CSS/Tailwind 配置），不碰 API 调用、路由、业务逻辑
- **统一设计语言** — 从散落的 Tailwind 原子类升级为有明确 tokens 的设计系统
- **面试场景可用** — 任何页面截图都能体现专业品质

### 1.2 设计原则

| 原则 | 含义 |
|------|------|
| 功能安全第一 | 所有改动限制在 `tailwind.config.js` + `style.css` + `.vue` `<style>` 块 |
| Token 驱动 | 颜色/字体/阴影/圆角/间距全部通过 CSS 变量定义，一处改全局生效 |
| 渐进落地 | 按 Phase 分步实施，每步可独立验证和回滚 |
| 信息层级优先 | 每个页面有明确的视觉重心，用户 3 秒内理解主功能 |

---

## 2. 设计 Tokens

### 2.1 颜色系统

```css
:root {
  /* 基底 */
  --color-paper:        #FAF9F7;   /* 页面背景 — 暖石色 */
  --color-sidebar:      #2C241E;   /* 侧边栏 — 深咖啡 (Deep Espresso) */
  --color-sidebar-hover:#3D342D;   /* 侧边栏悬停 */

  /* 文本 */
  --color-primary:      #2D2A26;   /* 主文字 — 暖深灰 */
  --color-secondary:    #6B6560;   /* 辅助文字 */
  --color-tertiary:     #9C9792;   /* 弱化文字/标签 */

  /* 表面 */
  --color-surface:      #FFFFFF;   /* 卡片/组件白底 */
  --color-warm-gray:    #F3F0EC;   /* 暖灰底色 */
  --color-grid:         #E8E4DD;   /* 边框/分割线 */

  /* 强调色 */
  --color-accent:       #C75B2A;   /* 琥珀金 — 主强调/CTA */
  --color-accent-hover: #A84A1F;   /* 琥珀金 hover */
  --color-accent-soft:  #FDF0E8;   /* 琥珀金浅底 */
  --color-accent-green: #3D7A6E;   /* 翡翠绿 — 成功/在线 */
  --color-accent-gold:  #B88A44;   /* 暖金 — 高亮/奖励 */
  --color-danger:       #C44D4D;   /* 柔和红 */
  --color-danger-soft:  #FDF0F0;   /* 柔和红浅底 */
}
```

### 2.2 字体系统

| 角色 | 字体 | 用途 |
|------|------|------|
| Display | `Space Grotesk` 700 | 页面标题 (22-36px), letter-spacing: -0.02em |
| Body | `Plus Jakarta Sans`, `Noto Sans SC` 400-600 | 正文/标签/按钮 (10-15px) |
| Mono | `JetBrains Mono` 400-500 | 代码/SQL/数据/标签 (10-13px) |

**Google Fonts CDN**:
```
Plus Jakarta Sans:400,500,600,700
Space Grotesk:600,700
Noto Sans SC:400,500,700
JetBrains Mono:400,500
```

### 2.3 阴影层级

```css
--shadow-sm:    0 1px 2px rgba(26,29,35,0.03);
--shadow-card:  0 1px 3px rgba(26,29,35,0.04), 0 1px 2px rgba(26,29,35,0.02);
--shadow-raised:0 4px 16px rgba(26,29,35,0.05), 0 1px 4px rgba(26,29,35,0.03);
--shadow-modal: 0 16px 48px rgba(26,29,35,0.10), 0 4px 12px rgba(26,29,35,0.05);
--shadow-glow:  0 0 0 3px rgba(199,91,42,0.12);  /* focus ring */
```

### 2.4 圆角系统

```css
--radius-none:  0px;
--radius-sm:    3px;    /* 按钮/标签/输入框 */
--radius:       5px;    /* 卡片/容器 */
--radius-md:    8px;    /* 模态框 */
--radius-lg:    14px;   /* 大卡片外层 */
--radius-full:  9999px; /* 药丸/圆点 */
```

### 2.5 动效曲线

```css
--ease-spring: cubic-bezier(0.32, 0.72, 0, 1);    /* 弹性交互 */
--ease-out:    cubic-bezier(0.16, 1, 0.3, 1);      /* 默认过渡 */
--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);     /* 模态进出 */
--duration-fast:   150ms;
--duration-base:   250ms;
--duration-slow:   500ms;
--duration-glacial:800ms;  /* 入场动画 */
```

### 2.6 间距 (8px 基准)

```css
--space-1: 4px;  --space-2: 8px;  --space-3: 12px;
--space-4: 16px; --space-5: 20px; --space-6: 24px;
--space-8: 32px; --space-10:40px; --space-12:48px;
--space-16:64px; --space-20:80px;
```

---

## 3. 导航结构

### 3.1 侧边栏布局 (240px, Deep Espresso #2C241E)

```
┌─────────────────────┐
│ Logo + Brand        │  品牌区
├─────────────────────┤
│ ⚡ 智能助手          │  ← 独立首模块 (编排/混合入口)
├─────────────────────┤
│ 功能模块            │  ← section label
│ 🔍 数据查询          │
│ 💬 智能问答          │
│ 📦 知识库            │
│ 📄 PM方案工作室      │
├─────────────────────┤
│ 系统                │  ← section label
│ 📜 系统日志          │
│ ⚙ 系统设置          │
├─────────────────────┤
│ ● 系统在线·MySQL v8 │  状态栏
└─────────────────────┘
```

### 3.2 设计决策

- **智能助手单独置顶**：它是编排入口，混合了 NL2SQL + RAG + PM 能力，与其他单一功能页面定位不同
- **数据查询排在功能模块第一**：这是面试展示的核心页面，功能最完整
- **系统功能沉底**：日志和设置是低频操作，不与业务功能混排

---

## 4. 布局系统

### 4.1 页面通用模板

每个页面遵循统一的三段式结构：

```
┌──────────────────────────────────────────┐
│ Page Header (h-20, hairline-b)           │
│ ├ h1 (Space Grotesk 22px bold)           │
│ ├ badge (mono 10px, accent, pill)        │
│ └ metrics (可选, display font)            │
├──────────────────────────────────────────┤
│ Content Area (flex-1, overflow-y-auto)   │
│ └ 页面特有内容，padding: 32-48px         │
└──────────────────────────────────────────┘
```

### 4.2 Bento 非对称网格

对于需要"主内容 + 辅助信息"并排的页面，使用 asymmetrical bento：

```css
.bento-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: var(--space-4);
}
```

**适用场景**：
- 数据查询页：主列(SQL+结果表) + 副列(AI洞察+历史)
- PM方案工作室：主列(阶段内容) + 副列(进度+来源)
- 知识库：主列(文档表格) + 副列(统计卡片)

### 4.3 卡片 Double-Bezel 模式

高端卡片使用嵌套结构（外层壳 + 内层核）：

```html
<div class="card-outer">  <!-- bg-warm-gray, border-grid, rounded-lg, p-[1.5px], shadow-card -->
  <div class="card-inner"> <!-- bg-surface, rounded-[calc-lg-1.5px)], shadow-inset -->
    ...content...
  </div>
</div>
```

普通卡片可直接用单层（`border-grid rounded shadow-card bg-surface`）。

### 4.4 按钮层级

| 变体 | 样式 |
|------|------|
| Primary | `bg-accent text-white rounded px-4 py-2 font-semibold` + Button-in-Button icon nest |
| Secondary | `border-grid text-secondary rounded px-4 py-2` hover→`bg-warm-gray` |
| Ghost | `text-tertiary` hover→`text-accent` |

### 4.5 响应式断点

| 断点 | 行为 |
|------|------|
| > 1024px | 完整布局：侧边栏 + schema面板 + 内容 |
| 768-1024px | 收起 schema 面板 |
| < 768px | 收起侧边栏，单列布局 |
| < 768px 所有 bento | `grid-template-columns: 1fr` |

---

## 5. 组件规范

### 5.1 通用组件

| 组件 | 文件 | 改动 |
|------|------|------|
| ConfirmDialog | `components/common/ConfirmDialog.vue` | 升级为 double-bezel 壳 + 新阴影 + 淡入动画 |
| EmptyState | `components/common/EmptyState.vue` | 新调色板色值 |
| StatusBadge | `components/common/StatusBadge.vue` | 翡翠绿 + 暖金替代原生色 |

### 5.2 侧边栏组件

| 组件 | 文件 | 改动 |
|------|------|------|
| AppSidebar | `components/sidebar/AppSidebar.vue` | 背景→`var(--color-sidebar)`, 纹理保留 |
| SidebarLogo | `components/sidebar/SidebarLogo.vue` | 图标琥珀金渐变, 字体 Space Grotesk |
| SidebarNav | `components/sidebar/SidebarNav.vue` | 重组为 3 段, active 指示器琥珀金 |
| SidebarStatus | `components/sidebar/SidebarStatus.vue` | 翡翠绿脉冲点 |
| SessionList | `components/sidebar/SessionList.vue` | 新色板适配 |

### 5.3 业务组件

| 模块 | 组件 | 关键改动 |
|------|------|---------|
| Chat | `ChatView`, `ChatMessage`, `ChatInput` | 消息气泡→新阴影+微圆角, AI 消息左边框→翡翠绿 |
| Query | `QueryInput`, `SqlDisplay`, `ResultTable` | 查询区 hero card + focus glow, SQL 暗色代码块, 表格斑马纹 |
| Query | `SchemaBrowser`, `FloatingWindow` | 暖灰底 schema 面板, 选中态高亮→琥珀金左边框 |
| Query | `InsightCard`, `QueryHistory`, `ExportButton` | Insight card→琥珀金渐变 header, 历史列表→hover 卡片 |
| PM | `TimelineStepper`, `StageFeedback` | 阶段节点→翡翠绿/琥珀金状态色, 加载→暖调渐变 |
| Knowledge | `KBCard`, `StatsBento`, `DocumentTable` | Bento 统计卡数字动画保留, 表格→新色板 |
| Logs | `TraceSpanNode` | 树节点→新色板, 级别色→新功能色 |

---

## 6. 页面改造清单

### 6.1 改造顺序（按面试展示优先级）

| # | 页面 | 路由 | 复杂度 | 核心展示价值 |
|---|------|------|--------|------------|
| 1 | **数据查询** | `/query` | ⭐⭐⭐⭐⭐ | NL2SQL 全流程, bento 布局, 结果表格+洞察 |
| 2 | **智能助手** | `/orchestrator` | ⭐⭐⭐ | 意图路由, 多结果类型渲染 |
| 3 | **智能问答** | `/chat` | ⭐⭐⭐ | 聊天 UI, SSE 流式, 来源引用 |
| 4 | **PM方案工作室** | `/pm-studio` | ⭐⭐⭐⭐⭐ | 4 阶段工作流, Timeline, SSE |
| 5 | **知识库** | `/knowledge` | ⭐⭐⭐⭐ | KB 卡片网格, 文档表格, 上传 |
| 6 | **系统日志** | `/logs` | ⭐⭐ | 查询追踪, Trace 树 |
| 7 | **系统设置** | `/settings` | ⭐ | 配置表单 |

### 6.2 每页面改动模式

以 QueryPage 为例（其他页面同理）：

```
改动范围（不碰的部分）:
  ✅ store: stores/query.js — 不动
  ✅ API: api/query.js, api/schema.js — 不动
  ✅ 业务逻辑: executeQuery(), fetchSchema() — 不动

改动范围（只改样式）:
  🔧 QueryPage.vue — 模板结构调整 (bento 网格)
  🔧 QueryInput.vue — hero card 样式
  🔧 SqlDisplay.vue — 暗色代码块样式
  🔧 ResultTable.vue — 表格新色板
  🔧 SchemaBrowser.vue — 面板色板
  🔧 InsightCard.vue — header 渐变+布局
  🔧 QueryHistory.vue — 列表 hover 样式
```

---

## 7. 功能-API 映射表（安全基线）

> **用途**: 每完成一个页面的改造后，对照此表逐项验证功能不缺失。
> **原则**: 只改 `<style>` / class / 模板布局，不碰任何 API 调用代码。

### 7.1 数据查询 `/query`

| 功能 | API 端点 | 页面触发点 | 验证方法 |
|------|---------|-----------|---------|
| 自然语言查询 | `POST /api/v1/query/` | QueryInput 输入+发送 | 输入问题→返回SQL+结果 |
| 直接SQL执行 | `POST /api/v1/query/execute` | SqlDisplay 编辑+执行 | 修改SQL→执行→返回结果 |
| Schema 加载 | `GET /api/v1/query/schema` | 页面挂载 | SchemaBrowser 显示表列表 |
| 连接测试 | `GET /api/v1/query/test-connection` | 页面挂载 | 侧边栏状态在线 |
| 表格预览 | `GET /api/v1/query/preview/{table}` | SchemaBrowser 点击表名 | FloatingWindow 显示字段+数据 |
| AI 洞察 | `POST /api/v1/query/insight` | 查询完成后 | InsightCard 显示分析 |
| 查询历史 | `GET /api/v1/query/history/all` | 页面挂载/查询完成 | QueryHistory 显示列表 |
| 清除历史 | `DELETE /api/v1/query/history/{id}` | 清除按钮 | 历史列表刷新 |
| 提交反馈 | `POST /api/v1/query/feedback` | FeedbackForm | 提交→确认提示 |
| 导出 Excel | `POST /api/v1/reports/generate-from-query` | ExportButton | 下载文件 |
| Schema 搜索 | `GET /api/v1/query/schema/search?q=` | 搜索输入 | 搜索结果列表 |
| 字段详情 | `GET /api/v1/query/schema/table/{t}/fields` | FloatingWindow | 显示字段列表 |

### 7.2 智能问答 `/chat`

| 功能 | API 端点 | 验证方法 |
|------|---------|---------|
| 发送消息（流式） | `POST /api/v1/chat/stream` | 输入问题→SSE 流式返回 |
| 发送消息（非流式） | `POST /api/v1/chat/` | 关闭流式→普通返回 |
| 加载会话列表 | `GET /api/v1/chat/sessions` | 页面挂载→SessionList |
| 加载会话详情 | `GET /api/v1/chat/sessions/{id}` | 点击会话→加载历史 |
| 删除会话 | `DELETE /api/v1/chat/sessions/{id}` | 删除→列表刷新 |
| 提交反馈 | `POST /api/v1/chat/feedback` | 赞/踩→提交 |

### 7.3 智能助手 `/orchestrator`

| 功能 | API 端点 | 验证方法 |
|------|---------|---------|
| 混合查询 | `POST /api/v1/orchestrator/chat` | 输入问题→意图路由→结果渲染 |

### 7.4 PM方案工作室 `/pm-studio`

| 功能 | API 端点 | 验证方法 |
|------|---------|---------|
| 创建会话 | `POST /api/v1/pm-solution/sessions` | 创建→显示 Timeline |
| 列表会话 | `GET /api/v1/pm-solution/sessions` | 加载→列表 |
| 获取会话 | `GET /api/v1/pm-solution/sessions/{id}` | 加载详情 |
| 阶段聊天(SSE) | `POST /api/v1/pm-solution/sessions/{id}/chat` | 发送→流式返回 |
| 确认阶段(SSE) | `POST /api/v1/pm-solution/sessions/{id}/confirm` | 确认→推进阶段 |
| 回退 | `POST /api/v1/pm-solution/sessions/{id}/rollback` | 回退→重放 |
| 切换阶段 | `PATCH /api/v1/pm-solution/sessions/{id}/current-stage` | 点击→切换 |
| 导出PRD | `POST /api/v1/pm-solution/sessions/{id}/export` | 导出→下载 md |
| 删除会话 | `DELETE /api/v1/pm-solution/sessions/{id}` | 删除→列表刷新 |
| 提交反馈 | `POST /api/v1/pm-solution/feedback` | 评分→提交 |

### 7.5 知识库 `/knowledge`

| 功能 | API 端点 | 验证方法 |
|------|---------|---------|
| 文档上传 | `POST /api/v1/docs/upload` | 选择文件→上传→进度 |
| 文档列表 | `GET /api/v1/docs/list/{p}/{s}` | 页面挂载→分页列表 |
| 删除文档 | `DELETE /api/v1/docs/{id}` | 删除→列表刷新 |
| 批量删除 | `PUT /api/v1/docs/batch-delete` | 多选→批量删除 |
| KB CRUD | `POST/GET/DELETE /api/v1/docs/knowledge*` | KB 创建/列表/删除 |
| 文档详情 | `GET /api/v1/docs/detail/{id}` | 预览 Modal |
| 下载源文件 | `GET /api/v1/docs/download-source/{id}` | 下载 |
| 统计信息 | `GET /api/v1/stats` | StatsBento 显示 |

### 7.6 系统日志 `/logs`

| 功能 | API 端点 | 验证方法 |
|------|---------|---------|
| 查询记录 | `GET /api/v1/logs/recent?type=queries` | 查询追踪 Tab 列表 |
| 日志 | `GET /api/v1/logs/recent?type=logs` | 日志 Tab 列表 |
| 追踪 | `GET /api/v1/logs/recent?type=traces` | 追踪 Tab TraceSpanNode |

### 7.7 系统设置 `/settings`

| 功能 | API 端点 | 验证方法 |
|------|---------|---------|
| 系统状态 | `GET /api/v1/chat/status` | BM25/向量 DB 状态 |
| MySQL 连接测试 | `GET /api/v1/query/test-connection` | 测试按钮 |
| 清除向量库 | `POST /api/v1/chat/clear` | 确认→清除 |

---

## 8. 实施 Phase 计划

```
Phase 1: 设计系统升级 (3 files)
  ├── tailwind.config.js — 颜色/字体/阴影/圆角 token 更新
  ├── src/style.css — CSS 变量层 + 全局动效 + 滚动条
  └── index.html (前端根目录) — Google Fonts CDN 更新
  验证: npm run dev → 全局色板生效，无编译错误

Phase 2: 根布局 + 侧边栏 (6 files)
  ├── App.vue — 根背景色
  ├── AppSidebar.vue — 侧边栏色值+纹理
  ├── SidebarLogo.vue — 品牌区样式
  ├── SidebarNav.vue — 重组 3 段结构 + 样式
  ├── SidebarStatus.vue — 状态样式
  └── SessionList.vue — 会话列表适配
  验证: 所有页面侧边栏统一，导航切换正常

Phase 3: 通用组件 (3 files)
  ├── ConfirmDialog.vue — double-bezel + 新动画
  ├── EmptyState.vue — 新色板
  └── StatusBadge.vue — 新功能色
  验证: 各页面弹窗/空状态/徽章显示正确

Phase 4: 核心页面 (3 pages)
  ├── QueryPage + 8 子组件 — hero card + bento + 暗色SQL + 表格
  ├── OrchestratorPage — 结果渲染区样式
  └── ChatPage + 3 子组件 — 消息气泡 + 流式
  验证: 对照功能-API 映射表逐项检查 3 页面

Phase 5: 其余页面 (4 pages)
  ├── PMStudioPage + 2 子组件 — Timeline + SSE 加载
  ├── KnowledgePage + 11 子组件 — 卡片网格 + 表格 + 上传
  ├── LogsPage + 1 子组件 — Tab + Trace 树
  └── SettingsPage — 配置区块
  验证: 对照功能-API 映射表逐项检查 4 页面

Phase 6: 收尾验证
  ├── npm run build (编译通过)
  ├── start.bat start (完整启动)
  └── 7 页面功能完整性走查
```

---

## 9. 验证清单

### 9.1 技术验证

- [ ] `npm run build` 无编译错误
- [ ] `npm run dev` 热更新正常
- [ ] 前端 `baseURL` 代理到后端 `:8912` 正确
- [ ] Google Fonts CDN 加载正常
- [ ] 所有页面路由跳转正常
- [ ] SSE 流式响应正常（Chat / PM Studio）
- [ ] SSE 流式输出时页面切换/关闭不报错（`ReadableStream` 取消）

### 9.2 数据查询 QueryPage `/query`

#### 主流程
- [ ] 输入自然语言问题后可以触发查询
- [ ] 查询中有 loading 状态（按钮禁用 + 文字变化）
- [ ] 返回 SQL 后能显示 SQL 区域（暗色代码块 + 语法高亮）
- [ ] 返回结果后能显示结果表格（列头 + 数据行 + 斑马纹）
- [ ] 结果为空时能显示 EmptyState，不显示空表格
- [ ] 查询失败时有错误提示（Toast / inline error），不会整页崩溃

#### 辅助交互
- [ ] 示例问题 / 推荐问题点击可填入输入框
- [ ] 清空输入 / 重新查询可用
- [ ] SQL 展示区可复制（如有复制按钮）
- [ ] 结果表格横向滚动/分页正常（如有）
- [ ] ExportButton 导出 Excel 正常下载

#### Schema 浏览器
- [ ] Schema 面板加载后显示表列表
- [ ] 点击表名 → FloatingWindow 弹出显示字段详情
- [ ] Schema 搜索可筛选表/字段

#### AI 洞察 & 历史
- [ ] 查询完成后 InsightCard 渲染 AI 洞察，不遮挡结果表格
- [ ] QueryHistory 显示最近查询记录，点击可回填
- [ ] FeedbackForm 提交评价正常

#### UI 回归
- [ ] 输入区是主视觉焦点（hero card 最大视觉权重）
- [ ] SQL 区和结果区层级合理（bento 网格左右分明）
- [ ] 小屏宽度（<1024px）下 Schema 面板收起，无严重错位

### 9.3 智能助手 OrchestratorPage `/orchestrator`

#### 主流程
- [ ] 输入问题 → 正确路由到后端（NL2SQL / RAG / PM / 直接回答）
- [ ] 结果显示意图标签（data_query / knowledge_search / solution_design / hybrid / direct_answer）
- [ ] 显示置信度分数和路由来源（rule / LLM / fallback）
- [ ] NL2SQL 结果：显示 SQL + 数据表 + 洞察
- [ ] RAG 结果：显示回答 + 来源引用
- [ ] Hybrid 结果：显示执行步骤 + 综合结论
- [ ] 输入为空时显示澄清提示

#### 异常处理
- [ ] 查询失败时有错误提示，不会整页崩溃

### 9.4 智能问答 ChatPage `/chat`

#### 主流程
- [ ] 输入问题可发送（Enter 发送 / 按钮发送）
- [ ] 消息列表正常显示（用户消息 + AI 消息）
- [ ] 流式响应时有 typing 动画 / 逐字输出
- [ ] 引用资料区 / 来源区正常渲染（来源标题 + 缩略图）
- [ ] 长回答不会把布局撑坏（`word-break` / `overflow-wrap` 生效）

#### 会话管理
- [ ] SessionList 显示会话列表
- [ ] 新建会话可用
- [ ] 切换会话 → 加载历史消息
- [ ] 删除会话 → 列表刷新，不报错
- [ ] 清空会话 / 切换知识库不报错

#### 反馈
- [ ] 消息旁赞/踩按钮可用
- [ ] 提交反馈（来源准确性 + 完整性 + 评论）正常

#### 异常处理
- [ ] SSE 流式输出时切换到其他页面不报错
- [ ] 网络断开时显示错误提示

### 9.5 PM 方案工作室 PMStudioPage `/pm-studio`

#### 会话管理
- [ ] 创建工作区 → 显示 Timeline 阶段条
- [ ] 历史记录 / 卡片 / 草稿区能正常展示
- [ ] 新建、编辑（标题）、删除、打开详情交互正常
- [ ] 空状态（无会话时）正常显示
- [ ] 异常状态（加载失败等）正常显示

#### 4 阶段流程
- [ ] 4 阶段 × 3 状态（active / generated / confirmed）UI 表现各不相同
- [ ] 当前阶段有视觉高亮（琥珀金呼吸光圈）
- [ ] 阶段内聊天（SSE）：发送消息 → 流式返回
- [ ] 确认阶段：点击确认 → SSE 流式生成下一阶段内容
- [ ] 阶段推进后 Timeline 状态更新正确
- [ ] 阶段回退：从阶段 N 回退到阶段 M → 内容正确恢复
- [ ] 切换显示阶段（纯导航）：点击 Timeline 节点 → 内容切换

#### 导出
- [ ] 导出 PRD：点击导出 → 下载 .md 文件成功

#### 知识库集成
- [ ] 知识库选择器可用，切换知识库后阶段内容引用正确

#### 反馈
- [ ] StageFeedback 星级评分 + 满意度 + 评论提交正常

### 9.6 知识库 KnowledgePage `/knowledge`

#### KB 列表视图
- [ ] StatsBento 统计卡片显示（文档数 + 段落数 + 字符数）
- [ ] KBCardGrid 显示知识库卡片列表
- [ ] 创建知识库 Modal → 输入名称+描述 → 创建成功
- [ ] 删除知识库 → 确认弹窗 → 删除成功
- [ ] 点击 KB 卡片 → 进入文档列表视图

#### 文档列表视图
- [ ] UploadBar 上传文档 → 进度轮询（ProgressPoll 2s 间隔）
- [ ] DocumentTable 显示文档列表（名称、状态、大小、时间）
- [ ] DocumentFilter 筛选可用
- [ ] 文档预览 Modal（段落内容展示）
- [ ] 下载源文件（触发浏览器下载）
- [ ] 单条删除 + 批量删除（BatchActions）
- [ ] TagManager 标签管理可用
- [ ] 空状态（无文档时）正常显示

#### 异常处理
- [ ] 上传失败有错误提示
- [ ] 文档处理失败（status=3）时可重试（reprocess）

### 9.7 系统日志 LogsPage `/logs`

- [ ] 3 个 Tab 切换正常（查询追踪 / 日志 / 追踪）
- [ ] 查询追踪 Tab：列表显示，展开行显示详情（概览/运维/开发）
- [ ] 日志 Tab：级别筛选（DEBUG/INFO/WARNING/ERROR）正常
- [ ] 追踪 Tab：TraceSpanNode 树形折叠/展开正常
- [ ] 自动刷新开关可用（10s 间隔）

### 9.8 系统设置 SettingsPage `/settings`

- [ ] LLM 配置信息正确显示
- [ ] MySQL 连接测试按钮可用（点击→状态更新）
- [ ] 系统版本信息显示
- [ ] 清除向量库 → 确认弹窗 → 执行成功

### 9.9 跨页面一致性（关键！）

改造设计 tokens 后最容易出现页面间不一致：

- [ ] 侧边栏在所有 7 页面一致（背景色 `#2C241E`、选中态、hover 态、3 段结构）
- [ ] 页面 Header 在所有页面结构一致（标题 Space Grotesk + 标签 mono pill）
- [ ] 按钮/输入框/卡片在各页面风格统一（Primary/Secondary/Ghost 层级）
- [ ] 无页面独有的硬编码颜色（`grep -r "bg-\[#" frontend/vue-app/src/` 应返回空）
- [ ] 字体加载正常（无 Inter 残余，Plus Jakarta Sans 作为正文字体生效）
- [ ] 7 页面切换时无颜色跳动（背景/文字/边框色值一致）

---

## 10. 回滚方案

```
# 回到改造前的存档点
git checkout v1.0-frontend-baseline

# 或者只回滚前端目录
git checkout v1.0-frontend-baseline -- frontend/

# 如果改动在独立分支
git checkout main
git branch -D feat/frontend-redesign
```

---

## 附录 A：原型文件

- `prototype/design-preview.html` — 可浏览器打开的静态原型
- 展示了数据查询页面的最终预期效果

## 附录 B：参考 Skill

| Skill | 用途 |
|-------|------|
| `high-end-visual-design` | 设计原则（Double-Bezel, 动效曲线, 禁止模式） |
| `redesign-existing-projects` | 审计现有设计 + 升级（Phase 2+ 实施时使用） |
| `webapp-testing` | Phase 6 功能验证时使用 |
