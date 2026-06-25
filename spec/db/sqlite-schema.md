# SQLite系统表

## knowledge (知识库)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| name | VARCHAR(150) | NOT NULL, INDEX | 名称 |
| description | VARCHAR(256) | DEFAULT '' | 描述 |
| workspace_id | VARCHAR(64) | DEFAULT 'default', INDEX | 工作空间 |
| type | INTEGER | DEFAULT 0 | 类型 |
| embedding_model_id | VARCHAR(36) | | Embedding模型ID |
| file_size_limit | INTEGER | DEFAULT 100 | 文件大小限制MB |
| file_count_limit | INTEGER | DEFAULT 50 | 文件数量限制 |
| meta | JSON | DEFAULT {} | 扩展元数据 |
| created_at | DATETIME | DEFAULT utcnow | 创建时间 |
| updated_at | DATETIME | DEFAULT utcnow, onupdate=utcnow | 更新时间 |

## document (文档)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| knowledge_id | VARCHAR(36) | FK→knowledge, NOT NULL, INDEX | 知识库ID |
| name | VARCHAR(150) | NOT NULL, INDEX | 文件名 |
| char_length | INTEGER | DEFAULT 0 | 字符数 |
| status | VARCHAR(20) | DEFAULT '0', INDEX | 状态码 |
| status_meta | JSON | DEFAULT {"state_time":{}, "progress":0} | 状态详情 |
| is_active | BOOLEAN | DEFAULT TRUE, INDEX | 是否启用 |
| type | INTEGER | DEFAULT 0 | 类型 |
| hit_handling_method | VARCHAR(20) | DEFAULT 'optimization' | 命中处理 |
| directly_return_similarity | FLOAT | DEFAULT 0.9 | 相似度阈值 |
| meta | JSON | DEFAULT {} | 扩展元数据 |
| created_at | DATETIME | DEFAULT utcnow | 创建时间 |
| updated_at | DATETIME | DEFAULT utcnow, onupdate=utcnow | 更新时间 |

## paragraph (段落)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| document_id | VARCHAR(36) | FK→document, NOT NULL, INDEX | 文档ID |
| knowledge_id | VARCHAR(36) | FK→knowledge, NOT NULL, INDEX | 知识库ID |
| content | TEXT | NOT NULL | 内容 |
| title | VARCHAR(256) | DEFAULT '', INDEX | 标题 |
| status | VARCHAR(20) | DEFAULT '0' | 状态 |
| status_meta | JSON | DEFAULT {"state_time":{}} | 状态详情 |
| hit_num | INTEGER | DEFAULT 0 | 命中次数 |
| is_active | BOOLEAN | DEFAULT TRUE, INDEX | 是否启用 |
| position | INTEGER | DEFAULT 0, INDEX | 位置 |
| created_at | DATETIME | DEFAULT utcnow | 创建时间 |
| updated_at | DATETIME | DEFAULT utcnow, onupdate=utcnow | 更新时间 |

## tag (标签)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| knowledge_id | VARCHAR(36) | FK→knowledge, INDEX | 知识库ID |
| key | VARCHAR(64) | INDEX | 标签键 |
| value | VARCHAR(128) | INDEX | 标签值 |
| color | VARCHAR(16) | DEFAULT '#3B82F6' | 颜色 |
| created_at | DATETIME | DEFAULT utcnow | 创建时间 |

## document_tag (文档标签关联)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| document_id | VARCHAR(36) | FK→document, INDEX | 文档ID |
| tag_id | VARCHAR(36) | FK→tag, INDEX | 标签ID |

## file (源文件)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| document_id | VARCHAR(36) | FK→document, INDEX | 文档ID |
| file_name | VARCHAR(256) | NOT NULL | 原始文件名 |
| file_size | INTEGER | DEFAULT 0 | 文件大小bytes |
| file_path | VARCHAR(512) | | 存储路径 |
| file_type | VARCHAR(20) | DEFAULT '' | 文件类型 |
| sha256_hash | VARCHAR(64) | INDEX | SHA256哈希 |
| source_type | VARCHAR(20) | DEFAULT 'DOCUMENT' | 来源类型 |
| meta | JSON | DEFAULT {} | 扩展元数据 |
| created_at | DATETIME | DEFAULT utcnow | 创建时间 |

## pm_session (方案会话)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| title | VARCHAR(256) | NOT NULL, DEFAULT '' | 标题 |
| knowledge_id | VARCHAR(36) | FK→knowledge, nullable, INDEX | 知识库ID(空=全部) |
| document_id | VARCHAR(36) | FK→document, nullable, INDEX | 关联文档ID |
| problem | TEXT | DEFAULT '' | 问题描述 |
| current_stage | INTEGER | DEFAULT 0 | 当前阶段(0-3) |
| stage_status | VARCHAR(20) | DEFAULT 'active' | 阶段状态 |
| created_at | DATETIME | DEFAULT utcnow | 创建时间 |
| updated_at | DATETIME | DEFAULT utcnow, onupdate=utcnow | 更新时间 |

## pm_stage (阶段记录)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| session_id | VARCHAR(36) | FK→pm_session, NOT NULL, INDEX | 会话ID |
| stage_type | VARCHAR(20) | NOT NULL, INDEX | 阶段类型 |
| status | VARCHAR(20) | DEFAULT 'pending' | 状态 |
| output_data | JSON | DEFAULT {} | 结构化输出 |
| output_summary | TEXT | DEFAULT '' | 输出摘要 |
| confirmed_at | DATETIME | nullable | 确认时间 |
| created_at | DATETIME | DEFAULT utcnow | 创建时间 |

## pm_chat (对话记录)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(36) | PK | UUID |
| session_id | VARCHAR(36) | FK→pm_session, NOT NULL, INDEX | 会话ID |
| stage_id | VARCHAR(36) | FK→pm_stage, nullable, INDEX | 阶段ID |
| role | VARCHAR(20) | NOT NULL | user/assistant |
| content | TEXT | NOT NULL | 内容 |
| sources | JSON | DEFAULT [] | 引用来源 |
| created_at | DATETIME | DEFAULT utcnow | 创建时间 |

## query_history (查询历史)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | |
| session_id | TEXT | NOT NULL | 会话ID |
| question | TEXT | NOT NULL | 用户问题 |
| sql | TEXT | NOT NULL | 执行的SQL (MCP 预构建查询时为空) |
| result_count | INTEGER | DEFAULT 0 | 返回行数 |
| insight | TEXT | — | AI 洞察摘要 |
| tables_used | TEXT | — | 使用的表 (JSON数组) |
| trace_json | TEXT | — | **Phase 2 新增** — 查询追踪结构化数据 (JSON) |
| favorite | INTEGER | DEFAULT 0 | 收藏标记 |
| created_at | TEXT | NOT NULL | 创建时间 (ISO 8601) |

> `trace_json` 结构: `{leader_view, pipeline, ops_view, debug_view}` — 详见 `docs/superpowers/plans/2026-06-25-query-trace-design.md`

## query_feedback (查询反馈)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | |
| history_id | INTEGER | FK → query_history.id | 关联的查询历史 |
| session_id | TEXT | — | 会话ID |
| question | TEXT | — | 问题快照 |
| sql | TEXT | — | SQL快照 |
| table_correct | INTEGER | — | 表选择是否正确 |
| field_correct | INTEGER | — | 字段选择是否正确 |
| result_correct | INTEGER | — | 结果是否正确 |
| comment | TEXT | — | 用户备注 |
| created_at | TEXT | — | 创建时间 |

## 文档状态码
| 值 | 说明 |
|------|------|
| '0' | PENDING 待处理 |
| '1' | STARTED 处理中 |
| '2' | SUCCESS 成功 |
| '3' | FAILURE 失败 |
