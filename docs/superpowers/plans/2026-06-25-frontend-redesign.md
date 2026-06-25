# 前端重设计实施计划 — WMS Knowledge

> **For agentic workers:** 按 Phase 顺序执行，每个 Phase 内的 Task 按序号递进。每个 Phase 完成后必须输出 § 规定的 6 段式报告。

**Goal:** 将 WMSRAGV2 前端从"内部工具风格"升级为"现代企业高端风格"（暖石色板 + Deep Espresso 侧边栏 + Bento 布局），零功能影响。

**Architecture:** 设计 Token 驱动——所有颜色/字体/阴影/圆角/动效通过 CSS 变量和 Tailwind config 集中定义。改动仅限 `<style>` / class / 模板布局，不碰 API 调用、路由、Store、业务逻辑。

**Tech Stack:** Vue 3 (Composition API), Tailwind CSS 3.4, Vite, Google Fonts (Plus Jakarta Sans + Space Grotesk + JetBrains Mono + Noto Sans SC)

**Spec:** `docs/superpowers/specs/2026-06-25-frontend-redesign.md`
**原型:** `prototype/design-preview.html`

---

## Global Constraints

- 只改前端样式层（CSS / Tailwind 配置 / 模板 class / 布局结构），禁止修改 API 调用、路由守卫、Store actions、后端代码
- 所有颜色/阴影/圆角/间距/动效必须通过 CSS 变量或 Tailwind theme.extend 定义，禁止组件内硬编码色值
- 每个 Phase 完成后必须对照 spec §7 功能-API 映射表 + §9 测试清单逐项验证
- 改造在独立分支 `feat/frontend-redesign` 上进行
- `npm run build` 必须在每个 Phase 结束后通过
- 所有用户可见文本保持中文

---

## Task 0: Git 存档基线

**Files:**
- 全局 git 操作，不改文件

- [ ] **Step 1: 暂存当前所有改动**

```bash
cd D:\WMSRAGV2
git add -A
git status
```
Expected: 显示即将提交的文件列表（modified + deleted + new/untracked）

- [ ] **Step 2: 提交基线**

```bash
git commit -m "chore: baseline before frontend redesign

Includes all current WIP changes as safety checkpoint."

Co-Authored-By: Claude <noreply@anthropic.com>
```
Expected: 提交成功，无错误

- [ ] **Step 3: 打 tag 并创建分支**

```bash
git tag v1.0-frontend-baseline
git checkout -b feat/frontend-redesign
git branch
```
Expected: 当前分支显示 `* feat/frontend-redesign`

- [ ] **Step 4: 验证 tag 可回滚**

```bash
git checkout v1.0-frontend-baseline
git checkout feat/frontend-redesign
```
Expected: 切换无错误，确认 tag 可用

- [ ] **Step 5: Commit baseline**

```bash
git add -A
git commit -m "chore: establish git baseline v1.0-frontend-baseline"
```

---

## Phase 1: 设计 Token 升级

### Task 1.1: 更新 Google Fonts CDN

**Files:**
- Modify: `frontend/vue-app/index.html`

**Interfaces:**
- Produces: 浏览器加载 Plus Jakarta Sans, Space Grotesk, JetBrains Mono, Noto Sans SC

- [ ] **Step 1: 替换字体加载**

在 `index.html` 的 `<head>` 中找到现有的 Google Fonts `<link>` 标签，替换为：

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@600;700&family=Noto+Sans+SC:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

> 注意：如果原有 `<link>` 标签结构不同，先删除旧的再加新的。确保 `preconnect` 提示也在。

- [ ] **Step 2: 启动前端验证字体加载**

```bash
cd frontend/vue-app
npm run dev
```
在浏览器 DevTools Network 面板确认 Google Fonts 请求成功（200 OK），无 404。

- [ ] **Step 3: Commit**

```bash
git add frontend/vue-app/index.html
git commit -m "feat(design): update Google Fonts CDN — Plus Jakarta Sans replaces Inter"
```

---

### Task 1.2: 更新 Tailwind 配置

**Files:**
- Modify: `frontend/vue-app/tailwind.config.js`

**Interfaces:**
- Consumes: 新字体 family、新色值
- Produces: 全局 Tailwind class 更新后的色板/字体/阴影/圆角

- [ ] **Step 1: 读取当前配置**

```bash
cat frontend/vue-app/tailwind.config.js
```
记下当前的 `colors` / `fontFamily` / `borderRadius` / `extend` 结构。

- [ ] **Step 2: 替换 tailwind.config.js**

用以下完整配置替换（保留原有的 `content` 和 `plugins` 部分不变）：

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 基底
        paper:        '#FAF9F7',
        sidebar:      '#2C241E',
        'sidebar-hover': '#3D342D',
        // 文本
        primary:      '#2D2A26',
        secondary:    '#6B6560',
        tertiary:     '#9C9792',
        // 表面
        surface:      '#FFFFFF',
        'warm-gray':  '#F3F0EC',
        grid:         '#E8E4DD',
        // 强调色
        'accent-orange': '#C75B2A',
        'accent-orange-hover': '#A84A1F',
        'accent-soft':    '#FDF0E8',
        'accent-green':   '#3D7A6E',
        'accent-gold':    '#B88A44',
        'danger':         '#C44D4D',
        'danger-soft':    '#FDF0F0',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        body:    ['"Plus Jakarta Sans"', '"Noto Sans SC"', 'sans-serif'],
        mono:    ['"JetBrains Mono"', '"SF Mono"', 'monospace'],
      },
      borderRadius: {
        sm:   '3px',
        DEFAULT: '5px',
        md:   '8px',
        lg:   '14px',
        xl:   '20px',
        full: '9999px',
      },
      boxShadow: {
        'sm':    '0 1px 2px rgba(26,29,35,0.03)',
        'card':  '0 1px 3px rgba(26,29,35,0.04), 0 1px 2px rgba(26,29,35,0.02)',
        'raised':'0 4px 16px rgba(26,29,35,0.05), 0 1px 4px rgba(26,29,35,0.03)',
        'modal': '0 16px 48px rgba(26,29,35,0.10), 0 4px 12px rgba(26,29,35,0.05)',
        'glow':  '0 0 0 3px rgba(199,91,42,0.12)',
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      },
      transitionTimingFunction: {
        'spring':  'cubic-bezier(0.32, 0.72, 0, 1)',
        'out-expo':'cubic-bezier(0.16, 1, 0.3, 1)',
        'in-out':  'cubic-bezier(0.65, 0, 0.35, 1)',
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 3: 验证构建**

```bash
cd frontend/vue-app
npm run build
```
Expected: 无编译错误。

- [ ] **Step 4: Commit**

```bash
git add frontend/vue-app/tailwind.config.js
git commit -m "feat(design): update Tailwind tokens — warm stone palette, new fonts, shadow system, micro-radius"
```

---

### Task 1.3: 更新全局 CSS — CSS 变量 + 动效 + 滚动条

**Files:**
- Modify: `frontend/vue-app/src/style.css`

**Interfaces:**
- Consumes: Tailwind 新配置
- Produces: CSS 自定义属性层、统一动效、自定义滚动条、全局基础样式

- [ ] **Step 1: 替换 style.css**

用以下完整内容替换 `frontend/vue-app/src/style.css`：

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* ============================================================
   CSS Custom Properties (Design Tokens)
   ============================================================ */
:root {
  --color-paper:        #FAF9F7;
  --color-sidebar:      #2C241E;
  --color-sidebar-hover:#3D342D;
  --color-primary:      #2D2A26;
  --color-secondary:    #6B6560;
  --color-tertiary:     #9C9792;
  --color-surface:      #FFFFFF;
  --color-warm-gray:    #F3F0EC;
  --color-grid:         #E8E4DD;
  --color-accent:       #C75B2A;
  --color-accent-hover: #A84A1F;
  --color-accent-soft:  #FDF0E8;
  --color-accent-green: #3D7A6E;
  --color-accent-gold:  #B88A44;
  --color-danger:       #C44D4D;
  --color-danger-soft:  #FDF0F0;

  --shadow-sm:    0 1px 2px rgba(26,29,35,0.03);
  --shadow-card:  0 1px 3px rgba(26,29,35,0.04), 0 1px 2px rgba(26,29,35,0.02);
  --shadow-raised:0 4px 16px rgba(26,29,35,0.05), 0 1px 4px rgba(26,29,35,0.03);
  --shadow-modal: 0 16px 48px rgba(26,29,35,0.10), 0 4px 12px rgba(26,29,35,0.05);
  --shadow-glow:  0 0 0 3px rgba(199,91,42,0.12);

  --radius-sm: 3px;
  --radius:    5px;
  --radius-md: 8px;

  --ease-spring: cubic-bezier(0.32, 0.72, 0, 1);
  --ease-out:    cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
}

/* ============================================================
   Global Reset & Base
   ============================================================ */
*, *::before, *::after {
  box-sizing: border-box;
}
body {
  margin: 0;
  padding: 0;
  background-color: var(--color-paper);
  color: var(--color-primary);
  font-family: 'Plus Jakarta Sans', 'Noto Sans SC', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ============================================================
   Custom Scrollbar
   ============================================================ */
::-webkit-scrollbar {
  width: 5px;
  height: 5px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #D5D0C8;
  border-radius: 9999px;
}
::-webkit-scrollbar-thumb:hover {
  background: #B5B0A8;
}

/* ============================================================
   Animations
   ============================================================ */
@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%      { opacity: 0.5; transform: scale(1.3); }
}
@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
@keyframes fade-up {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes shimmer {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

/* ============================================================
   Utility Classes
   ============================================================ */
.hairline-b { border-bottom: 1px solid var(--color-grid); }
.hairline-t { border-top: 1px solid var(--color-grid); }
.hairline-r { border-right: 1px solid var(--color-grid); }

.sidebar-texture {
  position: relative;
}
.sidebar-texture::after {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0.025;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  pointer-events: none;
}
```

- [ ] **Step 2: 验证构建**

```bash
cd frontend/vue-app
npm run build
```
Expected: 无编译错误。CSS 文件生成成功。

- [ ] **Step 3: 验证全局色板生效**

```bash
npm run dev
```
浏览器打开 `http://localhost:5173`，检查：
- 页面背景变为暖石色 `#FAF9F7`
- 文字颜色变为暖深灰 `#2D2A26`
- 滚动条变为新的细滚动条样式

- [ ] **Step 4: Commit**

```bash
git add frontend/vue-app/src/style.css
git commit -m "feat(design): add CSS custom properties layer + unified animations + custom scrollbar"
```

---

### Task 1.4: 更新 App.vue 根布局

**Files:**
- Modify: `frontend/vue-app/src/App.vue`

**Interfaces:**
- Consumes: 新 Tailwind class、CSS 变量
- Produces: 更新后的根背景色、深咖啡侧边栏

- [ ] **Step 1: 更新 App.vue 根元素背景色**

找到 `<div class="flex h-screen overflow-hidden">` 或其等效根元素。如果根元素上有 `bg-` 类引用旧色值，替换为 `bg-paper`（利用新 Tailwind config 的 `paper` color）。

如果原来有 `bg-[#F8FAFC]` 这类硬编码，统一替换为 `bg-paper`。

- [ ] **Step 2: 确保侧边栏背景引用新色值**

如果 `AppSidebar` 组件内部已有背景色硬编码（如 `bg-[#1E293B]`），暂时不动（在 Phase 2 统一改）。此处只改 App.vue 的 content 区域背景。

- [ ] **Step 3: 验证**

```bash
npm run dev
```
确认页面主内容区背景为暖石色。侧边栏暂时可能还是旧色（Phase 2 修复）。

- [ ] **Step 4: Commit**

```bash
git add frontend/vue-app/src/App.vue
git commit -m "refactor(design): update App.vue root background to warm paper tone"
```

---

### Phase 1 完成报告模板

```
## Summary
Phase 1 设计 Token 升级完成。更新了 Google Fonts CDN（Plus Jakarta Sans 替代 Inter）、
Tailwind 全量配置（15 色值 + 4 字体 + 5 级阴影 + 5 级圆角 + 3 条缓动曲线）、
全局 CSS 变量层、自定义滚动条、基础动画 keyframes。

## Modified Files
- frontend/vue-app/index.html — Google Fonts CDN 替换
- frontend/vue-app/tailwind.config.js — 全量 token 更新
- frontend/vue-app/src/style.css — CSS 变量 + 动效 + 滚动条
- frontend/vue-app/src/App.vue — 根背景色

## Design Notes
- 字体回退链：Plus Jakarta Sans → Noto Sans SC → sans-serif
- 所有色值同时存在于 Tailwind config（用于 class）和 CSS 变量（用于内联 style）
- 阴影使用暖黑 tint (rgba(26,29,35,...)) 而非纯黑，更柔和
- 自定义缓动曲线替代 Tailwind 默认 ease，模拟物理质感

## Tests
- [x] npm run build — 通过
- [x] npm run dev — 热更新正常
- [x] 页面背景色正确（暖石 #FAF9F7）
- [x] Google Fonts 加载成功（Network 200 OK）
- [ ] （视觉回归测试将在 Phase 6 统一执行）

## Risks
- 字体加载可能受 CDN 网络影响。回退链已配置，降级体验可接受。
- 当前组件中可能还有旧色值引用（如 bg-[#1E293B]），在后续 Phase 逐步替换。

## Tech Debt
无
```

---

## Phase 2: 根布局 + 侧边栏

### Task 2.1: AppSidebar — 深咖啡背景 + 纹理

**Files:**
- Modify: `frontend/vue-app/src/components/sidebar/AppSidebar.vue`

**Interfaces:**
- Consumes: 新 CSS 变量 `--color-sidebar`
- Produces: 深咖啡侧边栏容器

- [ ] **Step 1: 替换侧边栏背景色**

找到 `AppSidebar.vue` 中的根 `<aside>` 或 `<div>` 元素。将背景色从 `bg-[#1E293B]` 或 `bg-sidebar`(旧) 替换为：

```html
<aside class="w-[240px] flex-shrink-0 bg-sidebar sidebar-texture border-r border-white/10 flex flex-col overflow-hidden relative">
```

关键变更：
- `bg-sidebar` → 利用新 Tailwind config 自动解析到 `#2C241E`
- 添加 `sidebar-texture` class（噪点纹理覆盖层）
- `border-white/10` 保留作为右侧分割线

- [ ] **Step 2: 验证**

```bash
npm run dev
```
浏览器检查侧边栏颜色为深咖啡 `#2C241E`，纹理覆盖层存在但不突兀（3% 透明度）。

- [ ] **Step 3: Commit**

```bash
git add frontend/vue-app/src/components/sidebar/AppSidebar.vue
git commit -m "feat(design): AppSidebar — deep espresso background with noise texture"
```

---

### Task 2.2: SidebarLogo — 琥珀金品牌标识

**Files:**
- Modify: `frontend/vue-app/src/components/sidebar/SidebarLogo.vue`

**Interfaces:**
- Consumes: `--color-accent` CSS 变量
- Produces: 带琥珀金渐变的品牌 logo + Space Grotesk 字体标题

- [ ] **Step 1: 更新品牌区样式**

找到 `SidebarLogo.vue`。检查当前标题字体和图标颜色：

- 图标/logo 容器背景：改为琥珀金渐变
  ```html
  <div class="w-[34px] h-[34px] rounded bg-accent-orange flex items-center justify-center flex-shrink-0"
       style="background: linear-gradient(135deg, #C75B2A 0%, #E07B3A 100%); box-shadow: 0 2px 8px rgba(199,91,42,0.3);">
  ```
- 标题文本字体：`font-display` (Space Grotesk)
- 副标题：`font-mono text-[10px] text-white/35 uppercase tracking-wider`

- [ ] **Step 2: 验证视觉**

`npm run dev`，确认侧边栏顶部品牌图标有琥珀金渐变 + 发光阴影。

- [ ] **Step 3: Commit**

```bash
git add frontend/vue-app/src/components/sidebar/SidebarLogo.vue
git commit -m "feat(design): SidebarLogo — amber-gold gradient icon + Space Grotesk typography"
```

---

### Task 2.3: SidebarNav — 重组 3 段结构 + 样式升级

**Files:**
- Modify: `frontend/vue-app/src/components/sidebar/SidebarNav.vue`

**Interfaces:**
- Consumes: 新 Tailwind color/font tokens
- Produces: 3 段式导航（智能助手 → 功能模块 → 系统）

- [ ] **Step 1: 重写导航结构**

将原有的 2 段导航（"AI 工作台" + "数据 & 方案" + "系统"）重组为 3 段：

```html
<template>
  <nav class="flex-1 flex flex-col gap-[2px] py-4 px-3 overflow-y-auto relative z-[1]">
    <!-- 智能助手 — 独立首模块 -->
    <router-link to="/orchestrator" class="nav-item" :class="{ active: isActive('/orchestrator') }">
      <Icon icon="lucide:sparkles" width="18" height="18" />
      <span>智能助手</span>
    </router-link>

    <!-- 分隔 -->
    <div class="nav-section-label">功能模块</div>

    <router-link to="/query" class="nav-item" :class="{ active: isActive('/query') }">
      <Icon icon="lucide:search" width="18" height="18" />
      <span>数据查询</span>
    </router-link>
    <router-link to="/chat" class="nav-item" :class="{ active: isActive('/chat') }">
      <Icon icon="lucide:message-square" width="18" height="18" />
      <span>智能问答</span>
    </router-link>
    <router-link to="/knowledge" class="nav-item" :class="{ active: isActive('/knowledge') }">
      <Icon icon="lucide:database" width="18" height="18" />
      <span>知识库</span>
    </router-link>
    <router-link to="/pm-studio" class="nav-item" :class="{ active: isActive('/pm-studio') }">
      <Icon icon="lucide:file-text" width="18" height="18" />
      <span>PM方案工作室</span>
    </router-link>

    <!-- 分隔 -->
    <div class="nav-section-label">系统</div>

    <router-link to="/logs" class="nav-item" :class="{ active: isActive('/logs') }">
      <Icon icon="lucide:scroll-text" width="18" height="18" />
      <span>系统日志</span>
    </router-link>
    <router-link to="/settings" class="nav-item" :class="{ active: isActive('/settings') }">
      <Icon icon="lucide:settings" width="18" height="18" />
      <span>系统设置</span>
    </router-link>
  </nav>
</template>
```

- [ ] **Step 2: 更新导航项样式（使用新 tokens）**

替换 `<style scoped>` 中的 nav-item 样式：

```css
.nav-section-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  color: rgba(255,255,255,0.22);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 16px 12px 8px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border-radius: var(--radius);
  color: rgba(255,255,255,0.50);
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  transition: all 150ms cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
}
.nav-item:hover {
  color: rgba(255,255,255,0.85);
  background: rgba(255,255,255,0.04);
}
.nav-item.active {
  color: #fff;
  background: rgba(255,255,255,0.07);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.06);
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: -11px;
  top: 6px;
  bottom: 6px;
  width: 3px;
  background: var(--color-accent);
  border-radius: 0 3px 3px 0;
}
.nav-item svg { opacity: 0.7; }
.nav-item.active svg { opacity: 1; }
```

- [ ] **Step 3: 验证导航切换**

```bash
npm run dev
```
逐一点击 7 个导航项，确认：
- 路由跳转正常
- Active 状态有琥珀金左边框 + 高亮背景
- 3 段分隔标签正确显示

- [ ] **Step 4: Commit**

```bash
git add frontend/vue-app/src/components/sidebar/SidebarNav.vue
git commit -m "feat(design): SidebarNav — reorganize into 3-section layout with new visual style"
```

---

### Task 2.4: SidebarStatus — 状态指示器

**Files:**
- Modify: `frontend/vue-app/src/components/sidebar/SidebarStatus.vue`

**Interfaces:**
- Consumes: `--color-accent-green` CSS 变量
- Produces: 翡翠绿脉冲状态点 + 在线文字

- [ ] **Step 1: 更新状态样式**

将状态点颜色改为翡翠绿，添加脉冲动画：

```html
<div class="sidebar-status">
  <div class="status-dot"></div>
  <span class="status-text">系统在线 · <strong>MySQL v8.0</strong></span>
</div>
```

```css
.status-dot {
  width: 7px; height: 7px;
  border-radius: 9999px;
  background: var(--color-accent-green);
  box-shadow: 0 0 6px rgba(61,122,110,0.5);
  animation: pulse-dot 2.5s ease-in-out infinite;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/vue-app/src/components/sidebar/SidebarStatus.vue
git commit -m "feat(design): SidebarStatus — emerald green pulse dot indicator"
```

---

### Task 2.5: SessionList — 会话列表适配

**Files:**
- Modify: `frontend/vue-app/src/components/sidebar/SessionList.vue`

**Interfaces:**
- Consumes: 新色板
- Produces: 适配深色侧边栏的会话列表

- [ ] **Step 1: 适配会话列表色值**

检查 `SessionList.vue` 中的颜色引用，将白色透明度调整为与新版一致：
- 文字：`text-white/60` → `text-white/50`
- hover：`hover:bg-white/5`
- 选中：`bg-white/10`

- [ ] **Step 2: 验证**

切换到 Chat 页面，确认 SessionList 在深咖啡侧边栏中显示正常。

- [ ] **Step 3: Commit**

```bash
git add frontend/vue-app/src/components/sidebar/SessionList.vue
git commit -m "refactor(design): SessionList — adapt to new deep espresso sidebar tone"
```

---

### Phase 2 完成报告模板

```
## Summary
Phase 2 根布局 + 侧边栏升级完成。深咖啡色侧边栏、琥珀金品牌图标、
3 段式导航重组（智能助手独立置顶 → 功能模块 → 系统沉底）、
翡翠绿脉冲状态指示器、会话列表色板适配。

## Modified Files
- frontend/vue-app/src/components/sidebar/AppSidebar.vue — 深咖啡背景 + 噪点纹理
- frontend/vue-app/src/components/sidebar/SidebarLogo.vue — 琥珀金渐变图标 + Space Grotesk
- frontend/vue-app/src/components/sidebar/SidebarNav.vue — 重组 3 段结构 + 全新样式
- frontend/vue-app/src/components/sidebar/SidebarStatus.vue — 翡翠绿脉冲点
- frontend/vue-app/src/components/sidebar/SessionList.vue — 色板适配

## Design Notes
- 侧边栏纹理保留（SVG noise 3% 透明度），增加物理质感
- 导航 active 指示器使用琥珀金左边框 3px + inset box-shadow，层次分明
- 导航分隔标签使用 JetBrains Mono 10px，大写 + 宽字间距，弱化到 22% 不透明度

## Tests
- [x] 7 个导航项路由跳转正常
- [x] Active 状态视觉正确（琥珀金左边框 + 高亮）
- [x] 3 段分隔标签显示正确
- [x] 侧边栏在 7 页面间切换颜色一致
- [x] SessionList 在 Chat 页面正常显示

## Risks
- 如果 SessionList 原本有硬编码色值，可能在新深色背景下对比度不足。已适配但需后续检查。

## Tech Debt
无
```

---

## Phase 3: 通用组件

### Task 3.1: ConfirmDialog — Double-Bezel + 新动画

**Files:**
- Modify: `frontend/vue-app/src/components/common/ConfirmDialog.vue`

**Interfaces:**
- Consumes: 新阴影/圆角/动画 tokens
- Produces: 升级后的确认弹窗

- [ ] **Step 1: 读取当前 ConfirmDialog**

```bash
cat frontend/vue-app/src/components/common/ConfirmDialog.vue
```

- [ ] **Step 2: 重构弹窗结构为 Double-Bezel**

将遮罩层和内容框改为：

```html
<template>
  <div v-if="visible" class="fixed inset-0 z-[200] flex items-center justify-center" @click.self="$emit('cancel')">
    <!-- 遮罩 -->
    <div class="absolute inset-0 bg-sidebar/40 backdrop-blur-[2px] animate-fade-in"></div>

    <!-- 外层壳 (Outer Shell) -->
    <div class="relative z-[210] bg-warm-gray border border-grid rounded-lg p-[1.5px] shadow-modal">
      <!-- 内层核 (Inner Core) -->
      <div class="bg-surface rounded-[calc(0.875rem-1.5px)] p-6 max-w-[360px] w-full shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
        <!-- 图标 -->
        <div class="w-10 h-10 rounded-full bg-danger-soft flex items-center justify-center mb-4">
          <Icon icon="lucide:alert-triangle" class="text-danger" width="20" height="20" />
        </div>

        <h3 class="font-display text-[15px] font-bold text-primary mb-1">
          <slot name="title">确认操作</slot>
        </h3>
        <p class="text-[13px] text-secondary leading-relaxed mb-6">
          <slot name="message" />
        </p>

        <div class="flex gap-3 justify-end">
          <button @click="$emit('cancel')"
            class="px-4 py-2 border border-grid rounded text-[13px] font-medium text-secondary hover:bg-warm-gray transition-all duration-150 ease-out-expo">
            取消
          </button>
          <button @click="$emit('confirm')"
            class="px-4 py-2 bg-danger text-white rounded text-[13px] font-semibold hover:opacity-90 transition-all duration-150 ease-spring active:scale-[0.98]">
            确认
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 3: 验证**

在各个页面中触发 ConfirmDialog（如删除知识库/KB/文档/会话），确认弹窗样式正确。

- [ ] **Step 4: Commit**

```bash
git add frontend/vue-app/src/components/common/ConfirmDialog.vue
git commit -m "feat(design): ConfirmDialog — double-bezel nested architecture + new animations"
```

---

### Task 3.2: EmptyState + StatusBadge — 新色板适配

**Files:**
- Modify: `frontend/vue-app/src/components/common/EmptyState.vue`
- Modify: `frontend/vue-app/src/components/common/StatusBadge.vue`

**Interfaces:**
- Consumes: 新色板
- Produces: 适配后的通用组件

- [ ] **Step 1: EmptyState — 更新色值**

将图标颜色从 `text-grid`（如果有硬编码色）替换为引用新色板：
- 图标 → `text-grid` (新 Tailwind config 自动解析到 `#E8E4DD`)
- 标题 → `text-primary` (新 Tailwind config `#2D2A26`)
- 描述 → `text-tertiary` (`#9C9792`)

- [ ] **Step 2: StatusBadge — 更新功能色**

将 4 阶段状态色更新为：
- 完成 (status=2) → `bg-accent-green/10 text-accent-green`
- 处理中 (status=1) → `bg-accent-soft text-accent-orange`
- 失败 (status=3) → `bg-danger-soft text-danger`
- 待处理 (status=0) → `bg-warm-gray text-tertiary`

- [ ] **Step 3: 验证**

在 KnowledgePage 检查文档状态徽章、空状态显示。

- [ ] **Step 4: Commit**

```bash
git add frontend/vue-app/src/components/common/EmptyState.vue frontend/vue-app/src/components/common/StatusBadge.vue
git commit -m "refactor(design): EmptyState + StatusBadge — adapt to new color tokens"
```

---

### Phase 3 完成报告模板

```
## Summary
Phase 3 通用组件升级完成。ConfirmDialog 重构为 Double-Bezel 嵌套结构
（外层暖灰壳 + 内层白核 + 内阴影），EmptyState 和 StatusBadge 适配新色板。

## Modified Files
- frontend/vue-app/src/components/common/ConfirmDialog.vue — Double-Bezel + 新动画
- frontend/vue-app/src/components/common/EmptyState.vue — 新色板
- frontend/vue-app/src/components/common/StatusBadge.vue — 新功能色

## Design Notes
- ConfirmDialog 采用 Doppelrand 架构：外层 `bg-warm-gray border-grid p-[1.5px] rounded-lg`，
  内层 `bg-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]`，模拟物理嵌套感
- 确认按钮使用 `active:scale-[0.98]` 模拟按压反馈
- 遮罩 `bg-sidebar/40 backdrop-blur-[2px]` 替代纯黑遮罩，更柔和

## Tests
- [x] ConfirmDialog 在各页面触发正常（删除 KB/文档/会话）
- [x] 弹窗动画流畅（fade-in 0.2s）
- [x] StatusBadge 4 种状态色正确
- [x] EmptyState 显示正常

## Risks
无

## Tech Debt
无
```

---

## Phase 4: 核心页面（QueryPage + OrchestratorPage + ChatPage）

### Task 4.1: QueryPage — Hero Query Input + 暗色 SQL + Bento 布局

**Files:**
- Modify: `frontend/vue-app/src/views/QueryPage.vue`
- Modify: `frontend/vue-app/src/components/query/QueryInput.vue`
- Modify: `frontend/vue-app/src/components/query/SqlDisplay.vue`
- Modify: `frontend/vue-app/src/components/query/ResultTable.vue`
- Modify: `frontend/vue-app/src/components/query/InsightCard.vue`
- Modify: `frontend/vue-app/src/components/query/SchemaBrowser.vue`
- Modify: `frontend/vue-app/src/components/query/QueryHistory.vue`
- Modify: `frontend/vue-app/src/components/query/FloatingWindow.vue`

**Interfaces:**
- Consumes: 新设计 tokens、queryStore（不动）、queryApi（不动）
- Produces: 完整升级后的数据查询页

- [ ] **Step 1: 检查每个子组件当前结构**

逐一读取 8 个子组件，记录当前模板结构和 class 引用：
```
QueryInput.vue — 输入框卡片
SqlDisplay.vue — SQL 展示区
ResultTable.vue — 结果表格
InsightCard.vue — AI 洞察
SchemaBrowser.vue — 表浏览器
QueryHistory.vue — 历史列表
FloatingWindow.vue — 字段浮窗
```

- [ ] **Step 2: QueryInput — Hero Card 升级**

参考原型 CSS 中的 `.query-hero` 样式，将输入区升级为 Hero Card：

```html
<!-- 查询输入 Hero Card -->
<div class="query-hero bg-surface border border-grid rounded-lg shadow-raised overflow-hidden transition-shadow duration-250 ease-out-expo"
     :class="{ 'border-accent-orange/25 shadow-glow': isFocused }">
  <!-- Header -->
  <div class="flex items-center gap-3 px-5 py-4 border-b border-grid bg-warm-gray">
    <div class="w-2 h-2 rounded-full bg-accent-orange"></div>
    <span class="font-mono text-[10px] font-semibold text-secondary uppercase tracking-wider">自然语言查询</span>
  </div>
  <!-- Body -->
  <div class="p-5">
    <textarea v-model="question" @focus="isFocused = true" @blur="isFocused = false"
      class="w-full min-h-[56px] border-none outline-none text-[15px] text-primary bg-transparent resize-y leading-relaxed font-body"
      placeholder="用中文描述你想查询的数据，例如：查询最近一周各仓库的入库总量">
    </textarea>
  </div>
  <!-- Footer -->
  <div class="flex items-center justify-between px-5 py-3 border-t border-grid bg-warm-gray">
    <div class="flex gap-2 flex-wrap">
      <button v-for="q in suggestions" :key="q" @click="question = q"
        class="text-[11px] px-[10px] py-1 rounded-full border border-grid bg-surface text-secondary hover:border-accent-orange hover:text-accent-orange hover:bg-accent-soft transition-all duration-150 ease-out-expo cursor-pointer whitespace-nowrap font-body">
        {{ q }}
      </button>
    </div>
    <button @click="executeQuery"
      class="btn-primary">
      执行查询
      <span class="icon-nest">
        <Icon icon="lucide:arrow-up" width="16" />
      </span>
    </button>
  </div>
</div>
```

> 注意：保留原有的 `v-model` 绑定、`@keydown.enter`、`executeQuery()` 调用逻辑不变。

- [ ] **Step 3: SqlDisplay — 暗色代码块**

参考原型 CSS 中的 `.sql-card` 样式：

```html
<div v-if="sql" class="sql-card bg-[#1E2127] rounded shadow-sm overflow-hidden">
  <div class="flex items-center justify-between px-4 py-2 border-b border-white/6">
    <span class="font-mono text-[10px] font-medium text-white/35 uppercase tracking-wider">Generated SQL</span>
    <div class="flex gap-1">
      <button @click="copySql" class="px-[10px] py-[3px] border border-white/8 bg-transparent text-white/50 rounded-sm text-[10px] hover:bg-white/6 hover:text-white/80 transition-all font-mono cursor-pointer">复制</button>
    </div>
  </div>
  <pre class="px-5 py-4 font-mono text-[12.5px] leading-relaxed text-[#C8CCD4] overflow-x-auto whitespace-pre"><code v-html="highlightedSql"></code></pre>
</div>
```

- [ ] **Step 4: ResultTable — 新色板表格**

更新表格样式：
- 表头：`bg-warm-gray font-mono text-[10.5px] text-tertiary`
- 斑马纹：`even:bg-warm-gray/50`
- hover：`hover:bg-accent-soft/50`
- 数字列：`font-mono text-right font-medium`
- 仓库名称加粗 + 彩色圆点

- [ ] **Step 5: QueryPage 主文件 — Bento 网格重组**

将 `QueryPage.vue` 的 content 区域结构调整为：

```html
<!-- Content: Schema Panel + Query Area -->
<div class="flex-1 flex overflow-hidden">
  <!-- Schema Browser (左面板) -->
  <SchemaBrowser ... class="w-[220px] flex-shrink-0" />

  <!-- Query Area (主区域) -->
  <div class="flex-1 overflow-y-auto p-8 flex flex-col gap-6">
    <!-- Hero Input -->
    <QueryInput ... class="animate-fade-up" />

    <!-- Bento Grid -->
    <div class="bento-grid">
      <!-- 左主列: SQL + 结果 -->
      <div class="bento-main flex flex-col gap-4">
        <SqlDisplay ... />
        <ResultTable ... />
      </div>
      <!-- 右副列: 洞察 + 历史 -->
      <div class="bento-side flex flex-col gap-4">
        <InsightCard ... />
        <QueryHistory ... />
      </div>
    </div>
  </div>
</div>
```

Bento grid CSS（在 `<style scoped>` 中）：
```css
.bento-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 16px;
}
@media (max-width: 1024px) {
  .bento-grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 6: SchemaBrowser — 暖灰面板**

更新 Schema 面板样式：
- 背景：`bg-warm-gray`
- 选中态：`bg-surface shadow-[inset_3px_0_0_var(--color-accent)]`
- hover：`hover:bg-accent-soft/50`

- [ ] **Step 7: InsightCard + QueryHistory — 适配新色板**

InsightCard header 使用琥珀金渐变：
```css
background: linear-gradient(135deg, rgba(199,91,42,0.03), rgba(184,138,68,0.04));
```

QueryHistory 列表项 hover 使用新色板。

- [ ] **Step 8: 验证**

```bash
npm run build  # 确认编译通过
npm run dev    # 启动
```

对照 spec §9.2 的 16 项 QueryPage 测试清单逐项检查：
- 主流程 6 项（查询 → loading → SQL → 结果 → empty → 错误）
- 辅助交互 5 项（建议/清空/复制/滚动/导出）
- Schema 3 项（表列表/浮动窗/搜索）
- UI 回归 3 项（焦点/SQL区层级/小屏）

- [ ] **Step 9: Commit**

```bash
git add frontend/vue-app/src/views/QueryPage.vue frontend/vue-app/src/components/query/
git commit -m "feat(design): QueryPage — hero query card + dark SQL + bento grid + full color overhaul"
```

---

### Task 4.2: OrchestratorPage — 结果渲染区风格升级

**Files:**
- Modify: `frontend/vue-app/src/views/OrchestratorPage.vue`

**Interfaces:**
- Consumes: 新设计 tokens、`orchestratorChat()` API（不动）
- Produces: 升级后的结果渲染样式

- [ ] **Step 1: 读取当前 OrchestratorPage**

理解当前模板结构：单输入 + 结果区（根据 `routed_to` 渲染不同内容）。

- [ ] **Step 2: 更新输入区和结果区**

- 输入框 + 按钮参考 QueryPage Hero Card 风格（简化版）
- 意图标签 (intent badge) 升级为药丸样式
- 置信度显示为灰色小字 + 路由来源标注
- 各 `routed_to` 结果区的卡片使用新色板（`bg-surface border-grid rounded shadow-card`）

- [ ] **Step 3: 验证**

对照 spec §9.3 的 8 项测试：
- 5 种 intent 结果类型渲染正确
- 路由来源（rule/LLM/fallback）显示正确
- 错误状态不崩溃

- [ ] **Step 4: Commit**

```bash
git add frontend/vue-app/src/views/OrchestratorPage.vue
git commit -m "feat(design): OrchestratorPage — unified result card styling for all intent types"
```

---

### Task 4.3: ChatPage — 消息气泡 + 流式 UI

**Files:**
- Modify: `frontend/vue-app/src/views/ChatPage.vue`
- Modify: `frontend/vue-app/src/components/chat/ChatView.vue`
- Modify: `frontend/vue-app/src/components/chat/ChatMessage.vue`
- Modify: `frontend/vue-app/src/components/chat/ChatInput.vue`

**Interfaces:**
- Consumes: 新 tokens、chatStore（不动）、chatApi（不动）
- Produces: 升级后的聊天 UI

- [ ] **Step 1: ChatMessage — 消息气泡升级**

关键改动：
- 用户消息气泡：`bg-warm-gray` 暖灰底，微圆角 `rounded`
- AI 消息气泡：`bg-surface border border-grid rounded` + 左边框 `border-l-[3px] border-l-accent-green`
- 头像容器：微圆角
- 来源引用：小药丸按钮样式 `text-[11px]`
- Markdown 内容区：保持 `message-md-content` scoped 样式

- [ ] **Step 2: ChatInput — 底栏样式**

- 输入框：`rounded bg-warm-gray border-grid` 聚焦时 `border-accent-orange/40`
- 发送按钮：`bg-accent-orange hover:bg-accent-orange-hover` + Button-in-Button icon nest

- [ ] **Step 3: ChatView — 容器样式**

消息列表容器保持 `flex-1 overflow-y-auto`，增加新色板背景。

- [ ] **Step 4: 验证 SSE 流式输出**

对照 spec §9.4 的 12 项测试：
- 消息发送/流式输出/来源引用
- 会话 CRUD
- SSE 流式时页面切换不报错
- 长文本不撑破布局

- [ ] **Step 5: Commit**

```bash
git add frontend/vue-app/src/views/ChatPage.vue frontend/vue-app/src/components/chat/
git commit -m "feat(design): ChatPage — message bubbles with emerald accents + streaming UI polish"
```

---

### Phase 4 完成报告模板

```
## Summary
Phase 4 核心页面升级完成。QueryPage 完全重构为 Hero Card 输入 + 暗色 SQL +
Bento 非对称网格布局，OrchestratorPage 统一结果渲染区样式，
ChatPage 消息气泡升级为暖色面板 + 翡翠绿 AI 标识。

## Modified Files
- frontend/vue-app/src/views/QueryPage.vue — Bento 网格重组
- frontend/vue-app/src/components/query/QueryInput.vue — Hero Card
- frontend/vue-app/src/components/query/SqlDisplay.vue — 暗色代码块
- frontend/vue-app/src/components/query/ResultTable.vue — 新色板表格
- frontend/vue-app/src/components/query/InsightCard.vue — 渐变 header
- frontend/vue-app/src/components/query/SchemaBrowser.vue — 暖灰面板
- frontend/vue-app/src/components/query/QueryHistory.vue — hover 卡片
- frontend/vue-app/src/components/query/FloatingWindow.vue — 色板适配
- frontend/vue-app/src/views/OrchestratorPage.vue — 结果区升级
- frontend/vue-app/src/views/ChatPage.vue — 容器适配
- frontend/vue-app/src/components/chat/ChatView.vue — 容器适配
- frontend/vue-app/src/components/chat/ChatMessage.vue — 气泡升级
- frontend/vue-app/src/components/chat/ChatInput.vue — 输入框升级

## Design Notes
- QueryPage Bento 网格: `grid-template-columns: 1.5fr 1fr`，
  左侧主列放 SQL + 结果表，右侧副列放 AI 洞察 + 历史
- 暗色 SQL 代码块: 背景 `#1E2127`，关键字琥珀色高亮，行高 1.7
- ChatMessage AI 消息左边框 3px 翡翠绿，用户消息暖灰底
- 所有改动不涉及 store/API 业务逻辑代码

## Tests
- [x] QueryPage §9.2 16 项测试 — [通过/未通过数量]
- [x] OrchestratorPage §9.3 8 项测试 — [通过/未通过数量]
- [x] ChatPage §9.4 12 项测试 — [通过/未通过数量]
- [x] npm run build 通过

## Risks
- QueryPage 改动文件最多（8 个子组件），需要重点关注回归
- Bento 网格在小屏 (<1024px) 自动退化为单列，已添加 media query

## Tech Debt
- QueryPage 子组件较多（8个），后续可考虑合并相关组件减少文件数（非本次范围）
```

---

## Phase 5: 其余页面

### Task 5.1: PMStudioPage — 4 阶段工作流升级

**Files:**
- Modify: `frontend/vue-app/src/views/PMStudioPage.vue`
- Modify: `frontend/vue-app/src/components/pm/TimelineStepper.vue`
- Modify: `frontend/vue-app/src/components/pm/StageFeedback.vue`

**Interfaces:**
- Consumes: 新 tokens、`pmSolutionApi`（不动）、SSE fetch（不动）
- Produces: 升级后的 PM 工作台

- [ ] **Step 1: TimelineStepper — 阶段指示器升级**

更新 4 阶段节点样式，使用新功能色：
- 当前阶段 (active)：琥珀金 `bg-accent-orange` + 呼吸光圈 `shadow-glow`
- 已完成 (confirmed)：翡翠绿 `bg-accent-green`
- 已生成未确认 (generated)：板岩蓝或其他中间色
- 待处理 (pending)：暖灰 `bg-warm-gray border-grid`

连接线颜色：`bg-grid`

- [ ] **Step 2: PMStudioPage — 内容区升级**

- 页面 Header 适配新色板
- 阶段内容区卡片：`bg-surface border-grid rounded shadow-card`
- SSE 加载覆盖层：保留暖调渐变 `from-accent-soft/80 via-white/60 to-accent-soft/80`
- 知识库选择器：适配新色板
- 聊天区域参考 ChatPage 气泡样式

- [ ] **Step 3: StageFeedback — 评分组件**

星级评分和满意度选择器适配新色板。

- [ ] **Step 4: 验证**

对照 spec §9.5 的 14 项测试：
- 会话 CRUD 5 项
- 4 阶段流程 7 项
- 导出 + KB 集成 + 反馈 3 项

⚠️ PMStudioPage 是 SSE 状态机，尤其关注：
- 流式输出时页面切换不报错
- 回退后内容正确恢复

- [ ] **Step 5: Commit**

```bash
git add frontend/vue-app/src/views/PMStudioPage.vue frontend/vue-app/src/components/pm/
git commit -m "feat(design): PMStudioPage — 4-phase timeline with amber/emerald status + content card overhaul"
```

---

### Task 5.2: KnowledgePage — KB 管理系统

**Files:**
- Modify: `frontend/vue-app/src/views/KnowledgePage.vue`
- Modify: `frontend/vue-app/src/components/knowledge/StatsBento.vue`
- Modify: `frontend/vue-app/src/components/knowledge/KBCard.vue`
- Modify: `frontend/vue-app/src/components/knowledge/KBCardGrid.vue`
- Modify: `frontend/vue-app/src/components/knowledge/UploadBar.vue`
- Modify: `frontend/vue-app/src/components/knowledge/DocumentTable.vue`
- Modify: `frontend/vue-app/src/components/knowledge/DocumentRow.vue`
- Modify: `frontend/vue-app/src/components/knowledge/DocumentFilter.vue`
- Modify: `frontend/vue-app/src/components/knowledge/PreviewModal.vue`
- Modify: `frontend/vue-app/src/components/knowledge/TagManager.vue`
- Modify: `frontend/vue-app/src/components/knowledge/ProgressPoll.vue`
- Modify: `frontend/vue-app/src/components/knowledge/BatchActions.vue`

**Interfaces:**
- Consumes: 新 tokens、knowledgeStore（不动）、documentsApi（不动）
- Produces: 升级后的知识库管理页

- [ ] **Step 1: 逐组件更新色板**

KnowledgePage 组件最多（11 个子组件），但改动模式统一——将硬编码色值替换为新 Tailwind class：

| 组件 | 关键改动 |
|------|---------|
| `StatsBento.vue` | 统计卡背景 `bg-surface rounded shadow-card`，数字动画保留 |
| `KBCard.vue` | KB 卡片 `bg-surface border-grid rounded shadow-card`，hover→`shadow-raised` |
| `KBCardGrid.vue` | 网格间距 `gap-4` |
| `UploadBar.vue` | 上传区 `bg-warm-gray border-grid rounded` |
| `DocumentTable.vue` | 表头 `bg-warm-gray`，斑马纹 `even:bg-warm-gray/40` |
| `DocumentRow.vue` | 行样式适配 |
| `DocumentFilter.vue` | 搜索框适配（参考 QueryInput 缩略版） |
| `PreviewModal.vue` | 参考 ConfirmDialog Double-Bezel 结构 |
| `TagManager.vue` | 标签药丸按钮新色板 |
| `ProgressPoll.vue` | 进度条颜色适配 |
| `BatchActions.vue` | 批量操作栏适配 |

- [ ] **Step 2: 验证**

对照 spec §9.6 的 12 项测试：
- KB CRUD 5 项
- 文档操作 5 项
- 异常处理 2 项

- [ ] **Step 3: Commit**

```bash
git add frontend/vue-app/src/views/KnowledgePage.vue frontend/vue-app/src/components/knowledge/
git commit -m "feat(design): KnowledgePage — 11 sub-components adapted to new color tokens"
```

---

### Task 5.3: LogsPage + SettingsPage — 辅助页面

**Files:**
- Modify: `frontend/vue-app/src/views/LogsPage.vue`
- Modify: `frontend/vue-app/src/components/logs/TraceSpanNode.vue`
- Modify: `frontend/vue-app/src/views/SettingsPage.vue`

**Interfaces:**
- Consumes: 新 tokens
- Produces: 升级后的日志和设置页

- [ ] **Step 1: LogsPage — 3 Tab 适配**

- Tab 切换指示器：琥珀金下划线替代默认蓝色
- 查询追踪展开详情：卡片 `bg-surface rounded shadow-card`
- TraceSpanNode 树形节点：新色板适配
- 日志级别筛选：新功能色（ERROR→danger, WARN→amber, INFO→primary, DEBUG→tertiary）

- [ ] **Step 2: SettingsPage — 配置区块**

- 配置区块卡片：`border-grid rounded shadow-card`
- 危险操作区：`border-danger/20 bg-danger-soft rounded`
- 连接测试按钮：新 Primary/Secondary 层级

- [ ] **Step 3: 验证**

对照 spec §9.7 (5 项) + §9.8 (4 项)。

- [ ] **Step 4: Commit**

```bash
git add frontend/vue-app/src/views/LogsPage.vue frontend/vue-app/src/components/logs/ frontend/vue-app/src/views/SettingsPage.vue
git commit -m "feat(design): LogsPage + SettingsPage — trace tree and config cards adapted to new design system"
```

---

### Phase 5 完成报告模板

```
## Summary
Phase 5 其余 4 页面升级完成。PMStudioPage 4 阶段 Timeline 使用琥珀金/翡翠绿状态色，
KnowledgePage 11 子组件批量色板适配，LogsPage Tab 和 Trace 树升级，
SettingsPage 配置区块重新设计。

## Modified Files
- PMStudioPage + TimelineStepper + StageFeedback (3 files)
- KnowledgePage + 11 子组件 (12 files)
- LogsPage + TraceSpanNode (2 files)
- SettingsPage (1 file)

## Design Notes
- TimelineStepper 4 阶段 3 状态使用语义色：active=amber, confirmed=emerald, generated=slate, pending=warm-gray
- KnowledgePage 组件多但改动统一：所有硬编码色值 → Tailwind class
- LogsPage Tab 指示器从 blue → amber accent
- SettingsPage 危险操作区使用 danger-soft 背景

## Tests
- [x] PMStudioPage §9.5 14 项测试 — [通过/未通过]
- [x] KnowledgePage §9.6 12 项测试 — [通过/未通过]
- [x] LogsPage §9.7 5 项测试 — [通过/未通过]
- [x] SettingsPage §9.8 4 项测试 — [通过/未通过]
- [x] npm run build 通过

## Risks
- KnowledgePage 涉及最多子组件（11个），逐个检查确保无遗漏

## Tech Debt
无
```

---

## Phase 6: 收尾验证

### Task 6.1: 编译验证 + 硬编码颜色扫描

- [ ] **Step 1: 全局构建验证**

```bash
cd frontend/vue-app
npm run build
```
Expected: 无编译错误，无 warning（或仅允许少量 pre-existing warnings）。

- [ ] **Step 2: 硬编码颜色扫描**

```bash
cd frontend/vue-app/src
grep -rn "bg-\[#" . | grep -v node_modules | grep -v "\.git"
grep -rn "text-\[#" . | grep -v node_modules | grep -v "\.git"
grep -rn "border-\[#" . | grep -v node_modules | grep -v "\.git"
```
Expected: 0 结果（全部通过 CSS 变量或 Tailwind class 引用颜色）。

如发现残留，逐一定位替换。

- [ ] **Step 3: 字体引用检查**

```bash
grep -rn "font-family" frontend/vue-app/src/ --include="*.vue" --include="*.css" | grep -i inter
```
Expected: 0 结果（无 Inter 残留）。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(design): final hardcoded color cleanup + font consistency check"
```

---

### Task 6.2: 跨页面视觉一致性 + 84 项测试清单

- [ ] **Step 1: 逐页切换视觉检查**

启动 `npm run dev`，在浏览器中从侧边栏逐一导航到 7 个页面，每页停留 3 秒：

| 页面 | 检查点 |
|------|--------|
| `/orchestrator` | Header + 输入区 + 侧边栏一致 |
| `/chat` | 消息气泡 + SessionList 正常 |
| `/query` | Hero Card + Bento + Schema 面板 |
| `/knowledge` | StatsBento + KB 卡片 + 文档表格 |
| `/pm-studio` | Timeline + 阶段内容 |
| `/logs` | 3 Tab + 展开详情 |
| `/settings` | 配置区块 |

- [ ] **Step 2: 聚焦检查 spec §9.9 跨页面一致性 6 项**

- [ ] 侧边栏在所有 7 页面一致
- [ ] 页面 Header 在所有页面结构一致
- [ ] 按钮/输入框/卡片风格统一
- [ ] 无硬编码色值
- [ ] 字体加载正常
- [ ] 7 页面切换无颜色跳动

- [ ] **Step 3: 完整启动验证**

```bash
start.bat start
```
等待前后端完全启动，在真实环境中执行 3 个核心页面的端到端流程：
1. QueryPage: 输入问题 → 查询 → 查看 SQL → 查看结果 → 查看洞察 → 导出
2. ChatPage: 发送消息 → 接收流式回复 → 查看来源 → 切换会话
3. PMStudioPage: 创建会话 → 阶段对话 → 确认推进 → 回退 → 导出

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(design): cross-page visual consistency verification complete"
```

---

### Phase 6 完成报告模板

```
## Summary
Phase 6 收尾验证完成。通过 npm run build 编译验证、硬编码颜色全局扫描（0 残留）、
字体一致性检查、跨 7 页面视觉一致性走查、start.bat 完整启动端到端验证。
对照 spec §9 全部 84 项测试清单逐项验证完毕。

## Modified Files
如有残留修正则列出；理想情况下 Phase 6 无新增文件修改。

## Design Notes
- 硬编码色值扫描确保设计 Token 驱动的完整性
- 跨页面走查验证了设计系统的一致性交付

## Tests
- [x] npm run build — 通过
- [x] 硬编码颜色扫描 — 0 残留
- [x] Inter 字体残留扫描 — 0 残留
- [x] §9.2 QueryPage 16 项 — 全部通过
- [x] §9.3 OrchestratorPage 8 项 — 全部通过
- [x] §9.4 ChatPage 12 项 — 全部通过
- [x] §9.5 PMStudioPage 14 项 — 全部通过
- [x] §9.6 KnowledgePage 12 项 — 全部通过
- [x] §9.7 LogsPage 5 项 — 全部通过
- [x] §9.8 SettingsPage 4 项 — 全部通过
- [x] §9.9 跨页面一致性 6 项 — 全部通过
- [x] 84/84 测试全部通过

## Risks
无

## Tech Debt
无。设计系统改造完成，所有改动在 feat/frontend-redesign 分支，
可通过 git checkout v1.0-frontend-baseline 一键回滚。
```

---

## 附录: 各 Phase 验证矩阵

| Phase | 任务数 | 修改文件数 | 验证项 |
|-------|--------|-----------|--------|
| 0 | 5 steps | 0 (git only) | tag 可回滚 |
| 1 | 4 tasks | 4 files | npm run build, 色板/字体生效 |
| 2 | 5 tasks | 5 files | 7 页导航, 侧边栏一致 |
| 3 | 2 tasks | 3 files | 弹窗/空状态/徽章 |
| 4 | 3 tasks | 13 files | §9.2-9.4 共 36 项测试 |
| 5 | 3 tasks | 18 files | §9.5-9.8 共 35 项测试 |
| 6 | 2 tasks | 0-5 files | §9.9 + 84 项完整测试 |
| **Total** | **19 tasks** | **~43 files** | **84 项测试** |
