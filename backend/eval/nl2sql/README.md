# NL2SQL Evals

NL2SQL 模块的自动化评估系统。不打包进 Docker 生产镜像。

## 快速开始

```bash
# 1. 放入你的常用 SQL
# 编辑 datasets/seed_queries.json，格式见下方

# 2. 生成标准用例
cd backend
python -m eval.nl2sql.dataset_builder

# 3. 审核生成的用例
# 打开 datasets/golden_sql.json，检查每条用例，删除 _PENDING_REVIEW 字段

# 4. 快速验证（不调 LLM Judge，免费）
python -m eval.nl2sql.runner --dry-run

# 5. 完整评估
python -m eval.nl2sql.runner
```

## 环境要求

- `.env` 中的 MySQL 连接**必须指向测试库**（强烈建议只读副本）
- **不要在线上库跑 eval**，大查询可能影响性能
- LLM 配置与项目一致（deepseek/openai/anthropic）

## seed_queries.json 格式

```json
[
  {
    "sql": "SELECT item_code, SUM(qty) FROM sto_out_batch_yyyymm WHERE ... LIMIT 10",
    "description": "近30天出库量TOP10商品"
  }
]
```

## CLI 参数

| 参数 | 说明 |
|------|------|
| `--dry-run` | 快速模式，只做确定性检查，不调 LLM Judge |
| `--all` | 包含未审核用例 |
| `--category inventory` | 只跑某分类 |
| `--max-judge-calls 20` | 限制 Judge LLM 调用次数 |
| `--concurrency 3` | 并发数（默认 3） |
| `--json-output` | 指定 JSON 报告输出路径 |
