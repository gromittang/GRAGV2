## Summary
Phase 2 侧边栏升级完成。Deep Espresso 深咖啡背景 + 琥珀金品牌标识 +
3 段式导航重组（智能助手独立置顶 → 功能模块 → 系统沉底）+
翡翠绿脉冲状态指示器 + SessionList 色板适配。

## Modified Files
1. `frontend/vue-app/src/components/sidebar/SidebarLogo.vue` — 琥珀金渐变图标 + Space Grotesk 字体 + 副标题
2. `frontend/vue-app/src/components/sidebar/SidebarNav.vue` — 重组为 3 段结构 + 全新 scoped 样式
3. `frontend/vue-app/src/components/sidebar/SidebarStatus.vue` — 翡翠绿发光阴影
4. `frontend/vue-app/src/components/sidebar/SessionList.vue` — 文字透明度从 40% 调至 50%
5. `frontend/vue-app/src/components/sidebar/AppSidebar.vue` — 无需改动（Phase 1 已适配）

## Design Notes
- 导航分隔标签使用 JetBrains Mono 10px，22% 白色透明度，大写宽字间距
- Active 状态：纯白文字 + 7% 白色背景 + inset box-shadow + 左侧 3px 琥珀金指示条
- 状态点添加翡翠绿发光 shadow，在线时 pulse-dot 动画持续
- 智能助手独立置顶因为它是混合编排入口，与其他单一功能页面定位不同

## Tests
- [x] npm run build — 通过 (1.17s, 150 modules)
- [ ] 7 页面导航视觉验证 — 待 Phase 6 统一走查
- [ ] 侧边栏 3 段结构路由跳转 — 待 dev 启动验证

## Risks
- SidebarNav 从 v-for 循环改为硬编码 router-link，如果未来新增导航项需要手动加
- 旧 `font-space` 类引用已全部清除

## Tech Debt
无
