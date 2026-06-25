# 知识库接口 `/api/v1/docs`

## Endpoints

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/upload` | 上传文档 |
| GET | `/list/{page}/{size}` | 分页查询文档 |
| DELETE | `/{document_id}` | 删除文档 |
| POST | `/knowledge` | 创建知识库 |
| GET | `/knowledge/list` | 知识库列表 |
| DELETE | `/knowledge/{id}` | 删除知识库 |
| GET | `/detail/{id}` | 文档详情 |
| GET | `/paragraphs/{id}` | 文档段落 |
| GET | `/download-source/{id}` | 下载源文件 |

## Schemas

### UploadRequest (multipart/form-data)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["file"],
  "properties": {
    "file": {
      "type": "string",
      "format": "binary",
      "description": "上传文件"
    },
    "knowledge_name": {
      "type": "string",
      "default": "默认知识库",
      "maxLength": 150,
      "description": "知识库名称（无knowledge_id时使用）"
    },
    "knowledge_id": {
      "type": "string",
      "format": "uuid",
      "description": "指定知识库ID"
    }
  }
}
```

### UploadResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["success", "document_id"],
  "properties": {
    "success": { "type": "boolean" },
    "document_id": { "type": "string", "format": "uuid" },
    "message": { "type": "string" },
    "char_length": { "type": "integer", "minimum": 0 }
  }
}
```

### KnowledgeCreateRequest
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["name"],
  "properties": {
    "name": {
      "type": "string",
      "minLength": 1,
      "maxLength": 150,
      "description": "知识库名称"
    },
    "description": {
      "type": "string",
      "maxLength": 256,
      "default": "",
      "description": "知识库描述"
    }
  }
}
```

### KnowledgeListResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["success", "knowledge_list"],
  "properties": {
    "success": { "const": true },
    "knowledge_list": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "name", "created_at"],
        "properties": {
          "id": { "type": "string" },
          "name": { "type": "string" },
          "description": { "type": "string" },
          "document_count": { "type": "integer", "minimum": 0 },
          "paragraph_count": { "type": "integer", "minimum": 0 },
          "char_length": { "type": "integer", "minimum": 0 },
          "created_at": { "type": "string" },
          "updated_at": { "type": "string" }
        }
      }
    }
  }
}
```

### ParagraphsResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["success", "document_id", "documents"],
  "properties": {
    "success": { "const": true },
    "document_id": { "type": "string" },
    "document_name": { "type": "string" },
    "documents": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "content": { "type": "string" },
          "title": { "type": "string" },
          "position": { "type": "integer" }
        }
      }
    },
    "total_chunks": { "type": "integer", "minimum": 0 }
  }
}
```

### DeleteDocumentResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["success", "message"],
  "properties": {
    "success": { "const": true },
    "message": { "type": "string" }
  }
}
```

### DeleteKnowledgeResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["success", "message"],
  "properties": {
    "success": { "const": true },
    "message": { "type": "string" }
  }
}
```

### DocumentListResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["total", "current_page", "page_size", "documents"],
  "properties": {
    "total": { "type": "integer", "minimum": 0 },
    "current_page": { "type": "integer", "minimum": 1 },
    "page_size": { "type": "integer", "minimum": 1, "maximum": 100 },
    "documents": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "name", "status"],
        "properties": {
          "id": { "type": "string", "format": "uuid" },
          "name": { "type": "string" },
          "char_length": { "type": "integer", "minimum": 0 },
          "status": { "type": "string", "enum": ["0", "1", "2", "3"] },
          "paragraph_count": { "type": "integer", "minimum": 0 },
          "created_at": { "type": "string", "format": "date-time" }
        }
      }
    },
    "total_char_length": { "type": "integer", "minimum": 0 }
  }
}
```

### DocumentDetailResponse
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "name", "documents"],
  "properties": {
    "id": { "type": "string", "format": "uuid" },
    "name": { "type": "string" },
    "char_length": { "type": "integer", "minimum": 0 },
    "status": { "type": "string", "enum": ["0", "1", "2", "3"] },
    "paragraph_count": { "type": "integer", "minimum": 0 },
    "documents": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string", "format": "uuid" },
          "content": { "type": "string" },
          "title": { "type": "string" },
          "position": { "type": "integer", "minimum": 0 }
        }
      }
    }
  }
}
```

## Path Parameters

### PaginationParams
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["page", "size"],
  "properties": {
    "page": { "type": "integer", "minimum": 1 },
    "size": { "type": "integer", "minimum": 1, "maximum": 100 }
  }
}
```

## Errors

| HTTP | code | message |
|------|------|---------|
| 400 | FILE_TYPE_INVALID | 不支持的文件类型 |
| 400 | FILE_EMPTY | 文件内容为空 |
| 400 | FILE_TOO_LARGE | 文件大小超限(10MB) |
| 400 | KB_NAME_DUPLICATE | 知识库名称重复 |
| 404 | KB_NOT_FOUND | 知识库不存在 |
| 404 | DOC_NOT_FOUND | 文档不存在 |
| 500 | PROCESS_FAILED | 处理失败 |

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