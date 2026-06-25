先说结论：**你现在走的方向是对的，但还停留在“提示词工程阶段”**。一个真正稳定的 NL2SQL，核心不是“把 prompt 调到完美”，而是逐步演进成 **“受约束的 SQL 编译系统（Constrained SQL Generation System）”**。

你遇到的三个问题，其实是 NL2SQL 最经典的坑：

1. **查错表（schema grounding 失败）**
2. **域太大，不知道查哪张（retrieval / routing 问题）**
3. **字段幻觉（hallucinated schema）**

你现在已经自然地开始做了：

* SQL few-shot（常用查询样例）
* domain（按业务域缩小范围）
* 硬编码路由（关键词→固定表）
* prompt 控制

这些都是对的，但它们只是 **第一阶段（可用）**。

真正效果好，通常会走到 **第三阶段（稳定）**。

我按“企业级 NL2SQL 演进路线”给你讲。

---

# 第一阶段：Prompt 驱动（你现在的位置）

架构大概是：

```text
用户问题
   ↓
Prompt（数据字典 + few-shot）
   ↓
LLM 直接生成 SQL
   ↓
执行
```

你现在做的：

### 1. 数据字典

比如：

```text
商品表 B
字段：
plucode 商品编码
pluname 商品名称
spec 规格

出库头表 A
bill_no 单号
orgcode 机构
...
```

### 2. few-shot SQL

你说的：

> 常用查询 sql 放进 prompt

这是对的。

例如：

问题：
查询昨天门店A出库金额

SQL:
xxx

问题：
查询商品销量top10

SQL:
xxx

这种是行业标准。

因为：

> **业务逻辑比 schema 更重要**

LLM 知道表结构，不代表知道：

* 哪张是正式业务表
* 哪张是中间表
* 哪张是汇总表
* 哪张是最终口径表

这个只能靠真实 SQL 学。

所以：

> **真实查询日志是最宝贵训练集**

你判断是对的。

---

# 第二阶段：检索增强（大多数人忽略）

很多人失败，是因为：

> **一次性把整个 schema 丢给模型**

例如：

500张表
8000字段

然后让 AI 自己选。

结果：

> 必死。

因为 attention 根本不够。

正确做法：

不是全给。

而是：

# 先检索，再生成

变成：

```text
用户问题
    ↓
领域识别
    ↓
表召回（Top K）
    ↓
字段召回
    ↓
few-shot 检索
    ↓
LLM生成SQL
```

这是关键升级。

---

## Step1：领域识别（Domain Routing）

你已经开始做了。

例如：

### 库存域

* 库存
* 在库
* 库存数量

### 出库域

* 出库
* 发货
* 配送
* 调拨出

### 销售域

* 销售
* 营业额
* 收银

但：

你现在可能是：

```php
if(str_contains($question,'出库')){
    domain='出库';
}
```

这只是初级版。

更好的：

让 LLM 做 domain classification。

输出：

```json
{
  "domain":"出库",
  "confidence":0.89
}
```

因为：

“出库”未必出现。

比如：

> 昨天配送了多少件货？

本质是出库。

关键词规则会漏。

---

## Step2：表召回（最关键）

你说：

> 出库不是固定表，是一系列表

这就是：

### schema linking

不要把全部表给模型。

而是：

先召回相关表。

例如：

问题：

> 查询昨日门店A出库商品明细

先召回：

```text
sto_out_note_head
sto_out_note_detail
sto_send_plan
dst_dispatch_calc
goods
shop
```

而不是：

300张表。

怎么召回？

### 方法1：关键词

低成本。

建立 metadata：

```json
{
 "table":"sto_out_note_head",
 "keywords":["出库","配送","发货"]
}
```

召回 top K。

简单有效。

---

### 方法2：embedding（推荐）

表说明 embedding。

例如：

表描述：

```text
sto_out_note_head

出库单头表
记录门店配送出库单
包含单号、机构、日期
```

用户问题：

```text
昨天配送情况
```

向量检索：

top5 tables。

这个效果会明显提升。

尤其：

业务词 ≠ 表名。

比如：

“报货”

实际查：

```sql
sto_send_pln_head
```

模型自己猜不到。

---

## Step3：字段召回（防止幻觉）

你第三个问题：

> 编了字段名

这是超经典问题。

比如：

LLM 编：

```sql
where stock_status=1
```

实际：

```sql
bill_status
```

### 原因：

上下文太多。

字段太杂。

模型脑补。

### 正确做法：

只给允许字段。

例如：

召回表后：

生成：

```text
允许字段：

sto_out_note_head:
bill_no
bill_status
org_code
make_date

sto_out_note_detail:
plucode
qty
amount
```

再加规则：

```text
禁止使用未提供字段
如字段不存在，必须说明无法生成SQL
```

幻觉率下降很多。

---

# 第三阶段：SQL Agent（真正稳定）

企业级不会：

> 一次生成 SQL 就执行

而是：

### 多阶段编译

流程：

```text
用户问题
    ↓
意图理解
    ↓
候选表选择
    ↓
候选字段选择
    ↓
SQL生成
    ↓
SQL校验
    ↓
自动修复
    ↓
执行
```

这是你目前最缺的一层。

---

## SQL Validator（强烈推荐）

你现在：

生成→执行

应该：

生成→验证→执行

验证什么？

---

### 1. 表是否存在

SQL AST 解析：

检查：

```sql
from abc_table
```

是否存在。

不存在：

退回重写。

---

### 2. 字段是否存在

检查：

```sql
select xxx
```

是否合法。

如果：

```sql
stock_status
```

不存在。

反馈模型：

```text
字段 stock_status 不存在。

允许字段：
bill_status
status
```

让模型重新生成。

这个成功率很高。

---

### 3. join 是否合理

例如：

AI：

```sql
A.plucode = B.pluname
```

明显错。

建立：

### join graph

类似：

```json
[
 {
   "left":"out_detail.plucode",
   "right":"goods.plucode"
 }
]
```

限制 join。

只允许：

白名单 join。

效果会暴涨。

---

# Few-shot 应该怎么喂？

很多人也喂错。

不是：

100条 SQL 全塞 prompt。

没用。

正确：

### 动态 few-shot

检索相似问题。

例如：

问题：

> 查询昨天出库金额

向量检索：

最相似 3 条：

```text
查询昨日出库金额
查询某门店出库金额
查询日期范围出库统计
```

只放这3条。

效果比塞100条强。

因为：

上下文相关性 > 数量。

---

# 一个成熟 NL2SQL 的推荐架构

我建议你升级成：

```text
1. 用户问题

2. Domain Router
   ↓
   出库域

3. Schema Retriever
   ↓
   Top 5 tables

4. Field Retriever
   ↓
   Top fields

5. Few-shot Retriever
   ↓
   Similar SQL examples

6. LLM Generate SQL

7. SQL Validator
   - 表存在？
   - 字段存在？
   - join合法？
   - 聚合合理？

8. Auto Repair（可选）

9. Execute

10. 用户反馈学习
```

你会发现：

> Prompt 反而只占 20%

剩下是工程。

---

# 关于你说的“是不是要不断喂真实 SQL 和反馈？”

答案：

**是，而且这是必须的。**

但不是无脑堆。

是：

### 建立 Query Memory

记录：

```json
{
 "question":"昨天门店A出库金额",
 "domain":"出库",
 "sql":"select ..."
}
```

以及：

失败案例：

```json
{
 "question":"昨天配送量",
 "wrong_sql":"...",
 "fixed_sql":"..."
}
```

重点是：

### 错误案例价值更高

因为：

它教会模型：

> 什么不能做。

很多企业：

半年后效果暴涨。

本质是：

积累了几千条真实 query pair。

而不是换了模型。

---

最后给你一个很现实的判断：

如果你现在是：

> “纯 prompt + Claude/DeepSeek 一把梭生成 SQL”

效果一般是正常的。

一个 **70~85 分的 NL2SQL**，通常需要：

* schema retrieval
* domain routing
* few-shot retrieval
* SQL validation
* auto repair
* query memory

全部上。

否则业务数据库稍复杂（几十张表以上）就开始崩。

而你现在其实已经踩到了正确方向，只是缺少一个“标准架构视角”，导致一直在 prompt 上硬调。真正的提升点，已经从 **prompt engineering → system engineering** 了。
