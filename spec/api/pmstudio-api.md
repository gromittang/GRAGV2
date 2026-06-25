# PM方案工作室接口 `/api/v1/pm-solution`

## Endpoints

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/sessions` | 创建方案会话 |
| GET | `/sessions` | 会话列表 |
| GET | `/sessions/{id}` | 会话详情 |
| GET | `/sessions/{id}/chats` | 对话记录 |
| PATCH | `/sessions/{id}/title` | 更新标题 |
| POST | `/sessions/{id}/chat` | 阶段对话（SSE） |
| POST | `/sessions/{id}/confirm` | 确认阶段 |
| POST | `/sessions/{id}/rollback` | 回溯阶段 |
| POST | `/sessions/{id}/export` | 导出PRD |
| DELETE | `/sessions/{id}` | 删除会话 |

## Schemas

### SessionCreateRequest
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["problem"],
  "properties": {
    "problem": {
      "type": "string",
      "minLength": 1,
      "description": "问题描述"
    },
    "title": {
      "type": "string",
      "maxLength": 256,
      "description": "会话标题（可选，默认自动生成）"
    },
    "knowledge_id": {
      "type": "string",
      "description": "知识库ID。传空字符串''表示检索全部知识库；不传则使用默认'PM方案知识库'"
    }
  }
}
```

### SessionResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "title", "problem", "current_stage", "stage_status"],
  "properties": {
    "id": { "type": "string", "format": "uuid" },
    "title": { "type": "string", "maxLength": 256 },
    "problem": { "type": "string" },
    "knowledge_id": { "type": "string", "format": "uuid" },
    "document_id": { "type": "string", "format": "uuid" },
    "current_stage": { "type": "integer", "minimum": 0, "maximum": 3 },
    "stage_status": { "type": "string", "enum": ["active", "completed"] },
    "stages": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "name", "status"],
        "properties": {
          "type": { "type": "string", "enum": ["problem", "analysis", "detail", "prd"] },
          "name": { "type": "string" },
          "status": { "type": "string", "enum": ["pending", "active", "generated", "confirmed"] },
          "output_summary": { "type": "string", "maxLength": 100 }
        }
      }
    },
    "created_at": { "type": "string", "format": "date-time" },
    "updated_at": { "type": "string", "format": "date-time" }
  }
}
```

### SessionListResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["total", "sessions"],
  "properties": {
    "total": { "type": "integer", "minimum": 0 },
    "sessions": {
      "type": "array",
      "items": { "$ref": "#/definitions/SessionSummary" }
    }
  },
  "definitions": {
    "SessionSummary": {
      "type": "object",
      "required": ["id", "title", "current_stage"],
      "properties": {
        "id": { "type": "string", "format": "uuid" },
        "title": { "type": "string" },
        "problem": { "type": "string", "maxLength": 100 },
        "knowledge_id": { "type": "string" },
        "current_stage": { "type": "integer" },
        "stage_status": { "type": "string" },
        "created_at": { "type": "string", "format": "date-time" }
      }
    }
  }
}
```

### ChatRequest
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["user_input"],
  "properties": {
    "user_input": {
      "type": "string",
      "minLength": 1,
      "description": "用户输入"
    },
    "current_phase": {
      "type": "integer",
      "minimum": 0,
      "maximum": 3,
      "description": "用户当前阶段(0-3)，用于确定生成下一阶段"
    }
  }
}
```

### RollbackRequest
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["target_phase"],
  "properties": {
    "target_phase": {
      "type": "integer",
      "minimum": 0,
      "maximum": 3,
      "description": "回溯目标阶段"
    }
  }
}
```

### StageOutputResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["stage_type", "stage_name", "status", "output_data"],
  "properties": {
    "stage_type": { "type": "string", "enum": ["problem", "analysis", "detail", "prd"] },
    "stage_name": { "type": "string" },
    "status": { "const": "confirmed" },
    "output_data": { "type": "object" },
    "output_summary": { "type": "string" }
  }
}
```

### SSE Event Types
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "oneOf": [
    {
      "type": "object",
      "required": ["type", "content"],
      "properties": {
        "type": { "const": "token" },
        "content": { "type": "string" }
      }
    },
    {
      "type": "object",
      "required": ["type", "content"],
      "properties": {
        "type": { "const": "status" },
        "content": { "type": "string" }
      }
    },
    {
      "type": "object",
      "required": ["type"],
      "properties": {
        "type": { "const": "done" },
        "sources": { "type": "array" }
      }
    }
  ]
}
```

## Stage Templates

| stage_type | name | order | output_schema |
|------------|------|-------|---------------|
| problem | 问题定义 | 0 | {summary, background, goals[], constraints[], stakeholders[]} |
| analysis | 方案分析 | 1 | {options[{name,approach,pros,cons,score}], recommendation} |
| detail | 方案细化 | 2 | {features[{name,description,priority}], user_stories[], technical_requirements[]} |
| prd | PRD生成 | 3 | {prd_content} |

## Stage Status

| status | description |
|--------|-------------|
| pending | 待处理 |
| active | 进行中 |
| generated | 已生成未确认 |
| confirmed | 已确认 |

## Errors

| HTTP | code | message |
|------|------|---------|
| 404 | SESSION_NOT_FOUND | 会话不存在 |
| 400 | STAGE_INVALID | 当前阶段不存在 |
| 500 | CHAT_FAILED | 对话失败 |
| 500 | CONFIRM_FAILED | 确认阶段失败 |
| 500 | ROLLBACK_FAILED | 回溯失败 |