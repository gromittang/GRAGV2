# 数据查询接口 `/api/v1/query`

## Endpoints

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/` | 自然语言查询 |
| POST | `/execute` | 直接执行SQL |
| POST | `/insight` | 生成AI分析 |
| GET | `/schema` | 获取数据库Schema |
| GET | `/test-connection` | 测试MySQL连接 |
| GET | `/preview/{table}` | 预览表数据 |
| GET | `/schema/search` | 搜索Schema |
| GET | `/schema/table/{name}/fields` | 获取表字段 |
| GET | `/history/{session_id}` | 获取会话历史 |
| POST | `/history/{session_id}` | 保存历史记录 |
| DELETE | `/history/{session_id}` | 清空会话历史 |
| GET | `/history/all` | 全部查询历史 |

## Schemas

### QueryRequest
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["question"],
  "properties": {
    "question": {
      "type": "string",
      "minLength": 1,
      "maxLength": 500,
      "description": "自然语言问题"
    },
    "session_id": {
      "type": "string",
      "description": "会话ID"
    }
  }
}
```

### QueryResponse

**响应头**: `X-Query-Source: mcp | local | queryagent` (Phase 2 新增)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["success", "session_id"],
  "properties": {
    "success": { "type": "boolean" },
    "source": {
      "type": "string",
      "enum": ["mcp", "local", "queryagent"],
      "description": "实际执行的查询管线 (Phase 2 新增)"
    },
    "sql": {
      "type": "string",
      "description": "生成的SQL语句 (MCP预构建查询时可能为空)"
    },
    "results": {
      "type": "array",
      "items": { "type": "object" },
      "description": "查询结果"
    },
    "columns": {
      "type": "array",
      "items": { "type": "string" },
      "description": "列名"
    },
    "total": {
      "type": "integer",
      "minimum": 0,
      "description": "结果总数"
    },
    "tables_used": {
      "type": "array",
      "items": { "type": "string" },
      "description": "使用的表"
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "置信度"
    },
    "explanation": {
      "type": "string",
      "description": "查询逻辑说明"
    },
    "insight": {
      "type": "object",
      "properties": {
        "summary": { "type": "string" },
        "insights": { "type": "array", "items": { "type": "string" } },
        "follow_ups": { "type": "array", "items": { "type": "string" } }
      }
    },
    "error": {
      "type": "string",
      "description": "错误信息（失败时）"
    },
    "session_id": { "type": "string" }
  }
}
```

### ExecuteRequest
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["sql"],
  "properties": {
    "sql": {
      "type": "string",
      "minLength": 1,
      "description": "SQL语句（仅允许SELECT，后端校验）"
    },
    "session_id": { "type": "string" }
  }
}
```

### HistoryResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["history", "session_id"],
  "properties": {
    "history": {
      "type": "array",
      "items": { "$ref": "#/definitions/HistoryItem" }
    },
    "session_id": { "type": "string" }
  }
}
```

### HistoryAllResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["history", "limit"],
  "properties": {
    "history": {
      "type": "array",
      "items": { "$ref": "#/definitions/HistoryItem" }
    },
    "limit": { "type": "integer", "minimum": 1, "maximum": 100 }
  }
}
```

### ClearHistoryResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["success", "session_id"],
  "properties": {
    "success": { "type": "boolean" },
    "session_id": { "type": "string" }
  }
}
```

### SaveHistoryResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["success", "session_id"],
  "properties": {
    "success": { "const": true },
    "session_id": { "type": "string" }
  }
}
```

### InsightRequest
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["question", "sql", "results"],
  "properties": {
    "question": { "type": "string" },
    "sql": { "type": "string" },
    "results": { "type": "array", "items": { "type": "object" } },
    "session_id": { "type": "string" }
  }
}
```

### SchemaResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["tables", "session_id"],
  "properties": {
    "tables": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "display_name"],
        "properties": {
          "name": { "type": "string" },
          "display_name": { "type": "string" },
          "columns": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "column_name": { "type": "string" },
                "display_name": { "type": "string" },
                "data_type": { "type": "string" },
                "data_length": { "type": "integer" }
              }
            }
          }
        }
      }
    },
    "session_id": { "type": "string" }
  }
}
```

### TableFieldsResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["table_name", "columns"],
  "properties": {
    "table_name": { "type": "string" },
    "display_name": { "type": "string" },
    "description": { "type": "string" },
    "columns": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["column_name", "data_type"],
        "properties": {
          "column_name": { "type": "string" },
          "display_name": { "type": "string" },
          "data_type": { "type": "string" },
          "data_length": { "type": "integer" },
          "comment": { "type": "string" }
        }
      }
    },
    "session_id": { "type": "string" }
  }
}
```

### HistoryItem
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["session_id", "question", "sql"],
  "properties": {
    "session_id": { "type": "string" },
    "question": { "type": "string" },
    "sql": { "type": "string" },
    "result_count": { "type": "integer", "minimum": 0 },
    "insight": { "type": "string" },
    "created_at": { "type": "string", "format": "date-time" }
  }
}
```

### ConnectionTestResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["ok"],
  "properties": {
    "ok": { "type": "boolean" },
    "session_id": { "type": "string" }
  }
}
```

## Query Parameters

### PreviewParams
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100,
      "default": 5
    }
  }
}
```

### HistoryListParams
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100,
      "default": 20
    }
  }
}
```

### SchemaSearchParams
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["q"],
  "properties": {
    "q": { "type": "string", "minLength": 1 },
    "limit": { "type": "integer", "minimum": 1, "maximum": 50, "default": 10 }
  }
}
```

## Errors

| HTTP | code | message |
|------|------|---------|
| 400 | QUESTION_EMPTY | 问题不能为空 |
| 400 | NO_RELATED_TABLE | 无法找到相关数据库表 |
| 400 | SQL_GENERATION_FAILED | SQL生成失败 |
| 400 | SQL_VALIDATION_FAILED | SQL校验失败 |
| 400 | SQL_FORBIDDEN | 禁止的危险操作 |
| 400 | SQL_NO_LIMIT | 缺少LIMIT限制 |
| 400 | EXECUTE_FAILED | SQL执行失败 |