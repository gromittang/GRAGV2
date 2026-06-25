# 智能问答图片展示功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在智能问答对话中，当输出的参考片段包含图片标记 `[IMG]...[/IMG]` 时，将对应图片展示在对话输出中。

**Architecture:** 后端在 `_build_sources()` 中解析图片标记，提取图片URL列表作为新字段 `images` 返回；前端 `ChatMessage.vue` 在展示 sources 时，如果有图片则显示图片缩略图，点击可放大查看。

**Tech Stack:** Python (FastAPI), Vue 3, marked (Markdown解析)

---

## 文件结构

| 文件 | 负责内容 |
|------|----------|
| `backend/app/services/rag_service.py:105-135` | 修改 `_build_sources()` 提取图片信息 |
| `frontend/vue-app/src/components/chat/ChatMessage.vue` | 展示来源中的图片 |

---

## Task 1: 后端提取图片信息

**Files:**
- Modify: `backend/app/services/rag_service.py:105-135`

### Step 1: 修改 `_build_sources()` 方法添加图片提取逻辑

当前 `_build_sources()` 方法只返回片段文本的前200字符。需要增加解析 `[IMG]...[/IMG]` 标签的逻辑，提取图片URL列表。

- [ ] **Step 1.1: 添加图片解析辅助函数**

在 `_build_sources()` 方法之前添加一个辅助函数来解析图片标记：

```python
def _extract_images_from_text(text: str) -> List[Dict]:
    """
    从文本中提取图片信息
    格式: [IMG]{url}|图片{n}[/IMG]
    返回: [{"url": url, "label": label}, ...]
    """
    import re
    pattern = r'\[IMG\]([^|]+)\|([^[]+)\[/IMG\]'
    matches = re.findall(pattern, text)
    return [{"url": match[0], "label": match[1]} for match in matches]
```

- [ ] **Step 1.2: 修改 `_build_sources()` 方法**

修改 `_build_sources()` 方法，在构建 source 对象时增加 `images` 字段：

```python
def _build_sources(self, nodes: List) -> List[Dict]:
    """构建来源信息，包含文档名称和图片"""
    sources = []
    seen_doc_ids = set()

    for n in nodes:
        doc_id = n.metadata.get("document_id", "")
        doc_info = _get_document_info(doc_id)

        # 提取图片信息
        images = _extract_images_from_text(n.text)

        # 构建来源对象，增加 images 字段
        source = {
            "content": n.text[:200] + "..." if len(n.text) > 200 else n.text,
            "score": getattr(n, "score", 0),
            "images": images,  # 新增字段
            "metadata": {
                **n.metadata,
                "document_name": doc_info["name"],
                "document_id": doc_info["id"],
            }
        }

        if doc_id and doc_id in seen_doc_ids:
            continue
        if doc_id:
            seen_doc_ids.add(doc_id)

        sources.append(source)

    return sources[:5]
```

- [ ] **Step 3: 验证后端改动**

重启后端服务，测试 `/api/chat/stream` 接口返回的 sources 是否包含 `images` 字段。

---

## Task 2: 前端展示图片

**Files:**
- Modify: `frontend/vue-app/src/components/chat/ChatMessage.vue`

### Step 2.1: 修改 `ChatMessage.vue` 添加图片展示

在 sources 展示区域，如果有图片，显示图片缩略图。

- [ ] **修改模板，添加图片展示区域**

在 `<!-- Source citations -->` 部分后添加图片展示：

```vue
<!-- Source images -->
<div v-if="sourceImages && sourceImages.length" class="mt-3">
  <span class="font-mono text-[9px] text-primary/30 uppercase tracking-wider">相关图片</span>
  <div class="mt-1 flex flex-wrap gap-2">
    <div
      v-for="(img, i) in sourceImages"
      :key="i"
      class="relative cursor-pointer group"
      @click="openImagePreview(img.url)"
    >
      <img
        :src="getImageUrl(img.url)"
        :alt="img.label"
        class="w-24 h-24 object-cover rounded border border-grid/50 hover:border-accent-orange/50 transition-colors"
      />
      <div class="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors rounded flex items-center justify-center">
        <Icon
          icon="lucide:zoom-in"
          class="text-white opacity-0 group-hover:opacity-100 transition-opacity text-lg"
        />
      </div>
    </div>
  </div>
</div>

<!-- Image Preview Modal -->
<div
  v-if="imagePreviewVisible"
  class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center"
  @click="imagePreviewVisible = false"
>
  <img
    :src="imagePreviewUrl"
    class="max-w-[90vw] max-h-[90vh] rounded-lg shadow-2xl"
    @click.stop
  />
  <button
    @click="imagePreviewVisible = false"
    class="absolute top-4 right-4 text-white hover:text-gray-300"
  >
    <Icon icon="lucide:x" class="text-2xl" />
  </button>
</div>
```

- [ ] **修改 script，添加图片处理逻辑**

在 `<script setup>` 中添加：

```javascript
// 图片预览状态
const imagePreviewVisible = ref(false)
const imagePreviewUrl = ref('')

// 从所有sources中提取图片
const sourceImages = computed(() => {
  if (!props.sources) return []
  const allImages = []
  for (const s of props.sources) {
    if (s.images && Array.isArray(s.images)) {
      allImages.push(...s.images)
    }
  }
  return allImages.slice(0, 10) // 最多显示10张图片
})

// 获取图片完整URL（处理相对路径）
function getImageUrl(url) {
  if (url.startsWith('/')) {
    // 相对路径，需要拼接后端地址
    const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    return baseUrl + url
  }
  return url
}

// 打开图片预览
function openImagePreview(url) {
  imagePreviewUrl.value = getImageUrl(url)
  imagePreviewVisible.value = true
}
```

- [ ] **验证前端改动**

启动前端开发服务器，测试图片是否正确展示。

---

## Task 3: 测试验证

**Files:**
- Test: 手动测试功能

- [ ] **Step 3.1: 上传带图片的文档**

上传一个包含图片的 PDF 或 DOCX 文档到知识库，确认图片被正确提取（存储在 `data/images/` 目录）。

- [ ] **Step 3.2: 发起问答测试**

在智能问答页面，提问一个能触发包含图片片段的问题，验证：
1. 后端返回的 sources 包含 `images` 字段
2. 前端正确展示图片缩略图
3. 点击图片可以放大查看

- [ ] **Step 3.3: 验证现有功能不受影响**

测试不包含图片的文档问答，确保原有功能正常。

---

## 自检清单

1. **Spec coverage**: 所有需求都覆盖了吗？
   - ✓ 图片从片段中提取
   - ✓ 图片在对话输出中展示
   - ✓ 保持图片位置信息（通过显示在来源区域）
   - ✓ 不影响现有功能

2. **Placeholder scan**: 检查是否有 TBD/TODO 等占位符
   - ✓ 无占位符

3. **Type consistency**: 类型一致性检查
   - ✓ 后端 `_extract_images_from_text` 返回 `List[Dict]`
   - ✓ 前端 `sourceImages` computed 返回数组
   - ✓ 图片URL处理一致