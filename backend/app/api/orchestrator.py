from fastapi import APIRouter

router = APIRouter()


@router.post("/chat")
async def orchestrator_chat():
    return {"status": "ok"}
