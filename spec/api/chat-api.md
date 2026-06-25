# 对话问答接口 `/api/v1/chat`

## Endpoints

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/` | 对话问答 |
| POST | `/stream` | 流式对话（SSE） |
| GET | `/sessions` | 获取会话列表 |
| GET | `/sessions/{id}` | 获取会话详情 |
| DELETE | `/sessions/{id}` | 删除会话 |

## Schemas

### ChatRequest
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["question"],
  "properties": {
    "question": {
      "type": "string",
      "minLength": 1,
      "description": "用户问题"
    },
    "session_id": {
      "type": "string",
      "description": "会话ID，不传则新建"
    },
    "context_type": {
      "type": "string",
      "default": "all",
      "description": "检索范围"
    }
  }
}
```

### ChatResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["answer", "session_id", "has_documents"],
  "properties": {
    "answer": {
      "type": "string",
      "description": "LLM生成的答案"
    },
    "sources": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "doc_name": { "type": "string" },
          "content": { "type": "string" }
        }
      },
      "description": "引用来源"
    },
    "related_questions": {
      "type": "array",
      "items": { "type": "string" },
      "maxItems": 5,
      "description": "推荐追问"
    },
    "session_id": {
      "type": "string",
      "description": "会话ID"
    },
    "has_documents": {
      "type": "boolean",
      "description": "是否有文档检索"
    }
  }
}
```

### SessionListResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["sessions"],
  "properties": {
    "sessions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["session_id", "title"],
        "properties": {
          "session_id": { "type": "string" },
          "title": { "type": "string" },
          "message_count": { "type": "integer", "minimum": 0 },
          "updated_at": { "type": "string" }
        }
      }
    }
  }
}
```

### SessionDetailResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["session_id", "history"],
  "properties": {
    "session_id": { "type": "string" },
    "history": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["role", "content"],
        "properties": {
          "role": { "type": "string", "enum": ["user", "assistant"] },
          "content": { "type": "string" },
          "sources": { "type": "array" }
        }
      }
    }
  }
}
```

### DeleteSessionResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": { "const": true }
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
    },
    {
      "type": "object",
      "required": ["type", "content"],
      "properties": {
        "type": { "const": "error" },
        "content": { "type": "string" }
      }
    }
  ]
}
```

## Errors

| HTTP | code | message |
|------|------|---------|
| 400 | QUESTION_EMPTY | 问题不能为空 |
| 500 | SYSTEM_BUSY | 系统繁忙 |

### ErrorResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["detail"],
  "properties": {
    "detail": { "type": "string" }
  }
}
```