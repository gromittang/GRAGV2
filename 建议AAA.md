已经开始站在“企业可控性”视角思考了。

但里面有几处我会修正，尤其是：

> **1. Hybrid Router 的顺序**
> **2. Planner 的边界**
> **3. ainvoke vs subgraph（你看不懂那句）**
> **4. RBAC 对 NL2SQL 的实现方式（这里有坑）**

我逐条审查。

---

# 一、Hybrid Router —— 方向对，但顺序建议调整

Claude 建议：

```text
Rule
↓
Embedding
↓
LLM
```

并说：

> 宁缺毋滥。

### 这个思路是对的。

但是：

> **Embedding Router 不要过度依赖。**

因为你现在场景：

* RAG
* NL2SQL
* PM Studio

这些边界其实比较模糊。

例如：

> “库存管理的SOP规范”

Embedding 很容易误判。

因为：

### 语义接近 ≠ 能力归属

它会更偏：

> 库存 → SQL

而不是：

> SOP → RAG

---

## 我更建议：

### Router v1：

```text
Rule
 ↓
Lightweight LLM
 ↓
Fallback
```

不要急着 embedding。

原因：

### Embedding 更适合：

#### 知识分类

不是：

#### tool routing

---

例如：

你直接让一个便宜模型：

比如：

DeepSeek 的小模型

输出：

```json
{
  "intent":"hybrid",
  "confidence":0.82
}
```

会比 embedding 更稳。

---

### 推荐：

#### Rule 只做“高置信度命中”

比如：

```python
[
 "统计",
 "同比",
 "环比",
 "趋势",
 "销量"
]
```

直接 SQL。

---

其余：

直接：

```text
mini-llm-router
```

---

### 不要过早上：

embedding router

否则容易：

> “看起来聪明，实际上不可解释”

企业不喜欢。

---

# 二、Planner vs Supervisor —— 基本同意，但补一个关键点

Claude 说：

> JSON Plan + 声明式执行

### 这个非常对。

你以后简历里都能写：

> Declarative Execution Plan

挺加分。

---

例如：

用户：

> 为什么库存下降？

Planner：

```json
{
  "workflow":"inventory_analysis",
  "steps":[
    {
      "tool":"nl2sql",
      "query":"最近库存趋势"
    },
    {
      "tool":"rag",
      "query":"库存管理规范"
    },
    {
      "tool":"summary"
    }
  ]
}
```

很好。

---

## 但我要补一个：

### 不要让 Planner 完全自由规划

这是关键。

建议：

### Workflow Registry（很企业）

不要：

```text
LLM无限发挥
```

改：

### 预定义 workflow template

例如：

```python
WORKFLOW_REGISTRY = {
   "faq": [...],
   "sql_only": [...],
   "hybrid_analysis": [...],
   "sop_lookup": [...]
}
```

LLM：

只负责：

```text
选模板 + 填参数
```

而不是：

```text
自由设计执行计划
```

因为：

### 企业需要稳定性。

---

所以：

不是：

> LLM planner

而是：

> constrained planner

这个差异非常重要。

---

# 三、你没看懂那句 ainvoke() —— 我给你讲通俗版

Claude 说：

> 先 ainvoke()，别急着 subgraph

你看不懂正常。

因为这是 LangGraph 内部架构问题。

---

## 通俗理解：

你现在：

有：

### RAG Graph

### SQL Graph

### PM Graph

---

问题：

Orchestrator 怎么调用它们？

有两种方式。

---

## 方式1：普通函数调用（推荐）

就是：

### 当独立服务调用

例如：

```python
result = await rag_graph.ainvoke(input)
```

意思：

> “像调用普通函数一样”

---

流程：

```text
Orchestrator
    ↓
调用 RAG
    ↓
拿结果
    ↓
继续下一步
```

---

优点：

### 简单

### 易 debug

### 易维护

### 状态隔离

---

你可以理解成：

```text
微服务调用
```

---

## 方式2：subgraph（现在别碰）

LangGraph 有：

### graph inside graph

例如：

```text
Main Graph
 ├── RAG Subgraph
 ├── SQL Subgraph
```

所有 graph：

共享：

* state
* checkpoint
* memory

---

好处：

### 可以中断恢复

比如：

执行到 SQL：

停了。

明天继续。

---

坏处：

### 非常复杂

尤其 debug 地狱。

---

所以 Claude 说：

> 先 ainvoke

意思：

> **把子图当黑盒模块调用，不要急着嵌套 graph。**

这是对的。

---

# 四、前端设计 —— 我非常认可（这是亮点）

这个：

```text
保留模块
新增 /orchestrator
```

我觉得：

> 非常合理。

甚至：

### 比纯统一入口更成熟。

因为：

你兼顾：

#### 专业用户

直接：

```text
/query
```

---

#### 普通用户

走：

```text
/orchestrator
```

---

### 这个其实很企业

企业最怕：

> 强迫所有人用 AI

---

所以：

> Power User 保留专业入口

是很好的产品设计。

---

## ExecutionPlanPanel

这个我特别建议做。

因为：

> 它是“可解释 AI”

非常企业。

例如：

```text
Step1 查询库存数据 ✓
Step2 检索相关SOP ✓
Step3 生成分析结论...
```

面试超级好讲。

---

### 但建议：

不要做太复杂。

v1：

只展示：

```text
当前步骤
状态
结果摘要
耗时
```

就够。

---

# 五、被动增强 —— 好，但别太激进

Claude 说：

> 查不到建议跨模块。

这个不错。

但：

### 不要自动触发。

例如：

❌ 自动帮你查数据库

---

改：

### 用户确认

```text
没有找到相关制度。

是否尝试查询业务数据？
[确认]
```

原因：

### 企业强调：

> 可控性

尤其：

NL2SQL。

---

# 六、RBAC + NL2SQL —— Claude 这里方向对，但实现我会改

他说：

> prompt 注入 + sql_validate 正则检查

---

### Prompt 注入 ✔

同意。

例如：

```text
用户只能查深圳仓数据
```

---

### 正则校验 ❌ 不够

这是重点。

因为：

LLM SQL：

太复杂。

Regex 会被绕过。

例如：

join/subquery。

---

更企业方式：

### SQL AST 校验

比如：

解析 SQL：

看：

```text
WHERE
tenant_id
warehouse_id
dept_scope
```

有没有。

---

你以后可以：

用：

SQLGlot

做：

### AST parse

这个非常加分。

---

# 七、我会补充的一个缺失（重要）

Claude 漏了：

## Validator Layer

建议加：

```text
Planner
 ↓
Executor
 ↓
Validator
```

例如：

SQL 空结果：

```text
自动retry
```

---

RAG confidence 太低：

```text
提示不确定
```

---

避免：

> 幻觉。

企业非常看重。

---

## 最后结论（我给评分）

### Hybrid Router

8/10
（建议去 embedding 化）

---

### Planner

9/10
（补 workflow registry）

---

### ainvoke

9/10
（正确）

---

### 前端

9.5/10
（很成熟）

---

### RBAC

7/10
（regex 不够）

---

### 整体方案成熟度

如果你做出来：

> **已经很像一个企业级 AI Copilot，而不是练手项目了。**
