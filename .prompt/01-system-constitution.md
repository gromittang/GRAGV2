# System Constitution

You MUST follow:

/spec/system.md

## Tech Stack
- Backend: FastAPI + SQLAlchemy + ChromaDB + LlamaIndex
- Frontend: Vue 3 + Pinia + TailwindCSS
- DB: SQLite(meta) + MySQL(business) + ChromaDB(vector)
- LLM: DeepSeek/OpenAI/Claude (configurable)

## Architecture
```
Frontend → FastAPI → Service Layer → LLM/RAG/MySQL
                    ↓
              ChromaDB (vector)
```

## Before any development:

identify task type
load required spec files
read business rules
check edge cases
implement
self-review

## Never:

bypass workflow
violate constraints
ignore ADR
modify architecture without approval

## High risk modules:

PM workflow
NL2SQL
Permission system
State machine

must follow corresponding spec.