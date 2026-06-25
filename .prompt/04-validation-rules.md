# Validation Rules

## Final Checklist (Must Execute)

### 1. Constitution Compliance
- No forbidden SQL operations
- No SELECT *
- LIMIT clause present
- API prefix correct `/api/v1/`
- Error format correct

### 2. Spec Alignment
- Endpoint matches spec definition
- Request/Response fields match
- HTTP status codes match spec
- Database constraints respected

### 3. Edge Cases Covered
- Empty input handled
- Missing resource (404)
- Invalid type/format
- Size limits enforced
- Concurrent access safe

### 4. Security Check
- No hardcoded secrets
- No SQL injection path
- File upload validated
- User input sanitized

### 5. Code Standards
- Existing patterns followed
- No duplicate code
- No unused imports
- Comments for non-obvious logic only
- Chinese for user messages