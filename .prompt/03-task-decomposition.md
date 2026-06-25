# Task Decomposition

## Process (Strict Order)

### 1. Understand Scope
- Clarify requirements
- Identify boundaries
- Confirm with user if ambiguous

### 2. Read/Generate Spec
- Check existing spec in `/spec/spec.md`
- If missing, create section first

### 3. Design Interface/Schema
- API endpoints → match existing patterns
- DB tables → follow existing models
- Validate against spec

### 4. Write Tests (TDD)
- Unit tests first
- Must fail before implementation
- Cover edge cases

### 5. Implement Code
- Minimal code to pass tests
- No premature abstraction
- Follow existing patterns

### 6. Self-Check
- Run all tests
- Apply validation rules (see 04-validation-rules.md)
- Commit with clear message