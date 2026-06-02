"""
文档管理API
支持上传、列表、删除
"""
from fastapi import APIRouter, UploadFile, File as FastAPIFile, HTTPException, Path, Form
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
import os
import uuid

from app.models.document import get_session, Knowledge, Document, Paragraph, File as FileModel

router = APIRouter()


class DocumentCreateResponse(BaseModel):
    success: bool
    document_id: str
    message: str
    char_length: int = 0


class DocumentListResponse(BaseModel):
    total: int
    current_page: int
    page_size: int
    documents: List[Dict]
    total_char_length: int


class KnowledgeCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: str = Field(default="", max_length=256)


class KnowledgeResponse(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    paragraph_count: int
    char_length: int
    created_at: str
    updated_at: str


@router.post("/upload", response_model=DocumentCreateResponse)
async def upload_document(
    file: UploadFile = FastAPIFile(...),
    knowledge_name: str = Form(default="默认知识库"),
    knowledge_id: Optional[str] = Form(default=None)
):
    """上传文档"""
    allowed_ext = ['.pdf', '.docx', '.txt', '.md']
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_ext:
        raise HTTPException(400, f"不支持的文件类型: {file_ext}")

    file_content = await file.read()
    if len(file_content) == 0:
        raise HTTPException(400, "文件内容为空")

    if len(file_content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小超过限制(10MB)")

    session = get_session()
    try:
        if knowledge_id:
            kb = session.query(Knowledge).filter(Knowledge.id == knowledge_id).first()
            if not kb:
                session.close()
                raise HTTPException(404, f"知识库 {knowledge_id} 不存在")
            target_kb_id = kb.id
        else:
            from app.models.document import get_or_create_knowledge
            kb = get_or_create_knowledge(session, knowledge_name)
            target_kb_id = kb.id
    except Exception as e:
        session.close()
        raise HTTPException(500, f"知识库初始化失败: {str(e)}")

    # 创建文档记录
    doc_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        knowledge_id=target_kb_id,
        name=file.filename,
        char_length=len(file_content),
        status="0"
    )
    session.add(doc)

    # 保存源文件
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{doc_id}_{file.filename}")
    with open(file_path, 'wb') as f:
        f.write(file_content)

    file_record = FileModel(
        document_id=doc_id,
        file_name=file.filename,
        file_size=len(file_content),
        file_path=file_path,
        file_type=file_ext
    )
    session.add(file_record)

    session.commit()
    session.close()

    # 处理文档
    await process_document_async(doc_id, file_path, target_kb_id)

    return DocumentCreateResponse(
        success=True,
        document_id=doc_id,
        message="文档上传成功",
        char_length=len(file_content)
    )


async def process_document_async(doc_id: str, file_path: str, knowledge_id: str):
    """异步处理文档"""
    from app.rag.document_processor import DocumentProcessor
    from app.services.rag_service import get_rag_service

    session = get_session()
    doc = session.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        session.close()
        return

    doc.status = "1"
    session.commit()

    try:
        processor = DocumentProcessor()
        nodes = processor.process_file(file_path, {"document_id": doc_id, "knowledge_id": knowledge_id})

        for i, node in enumerate(nodes):
            para = Paragraph(
                id=str(uuid.uuid4()),
                document_id=doc_id,
                knowledge_id=knowledge_id,
                content=node.text,
                title=node.metadata.get("title", ""),
                position=i
            )
            session.add(para)

        rag_service = get_rag_service()
        documents = [{"id": str(uuid.uuid4()), "content": n.text, "metadata": n.metadata} for n in nodes]
        rag_service.add_documents(documents)

        doc.status = "2"
        doc.char_length = sum(len(n.text) for n in nodes)
        session.commit()

    except Exception as e:
        doc.status = "3"
        session.commit()
        print(f"[Document] 处理失败: {e}")

    session.close()


@router.get("/list/{page}/{size}", response_model=DocumentListResponse)
async def list_documents(
    page: int = Path(ge=1),
    size: int = Path(ge=1, le=100),
    knowledge_id: Optional[str] = None,
    name: Optional[str] = None
):
    """分页获取文档列表"""
    session = get_session()
    try:
        query = session.query(Document)

        if knowledge_id:
            query = query.filter(Document.knowledge_id == knowledge_id)
        if name:
            query = query.filter(Document.name.contains(name))

        total = query.count()
        offset = (page - 1) * size
        documents = query.order_by(Document.created_at.desc()).offset(offset).limit(size).all()

        doc_list = []
        total_char_length = 0

        for doc in documents:
            para_count = session.query(Paragraph).filter(Paragraph.document_id == doc.id).count()
            doc_list.append({
                "id": doc.id,
                "name": doc.name,
                "char_length": doc.char_length,
                "status": doc.status,
                "is_active": doc.is_active,
                "paragraph_count": para_count,
                "created_at": doc.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": doc.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            })
            total_char_length += doc.char_length

        session.close()

        return DocumentListResponse(
            total=total,
            current_page=page,
            page_size=size,
            documents=doc_list,
            total_char_length=total_char_length
        )

    except Exception as e:
        session.close()
        raise HTTPException(500, f"获取文档列表失败: {str(e)}")


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """删除单个文档"""
    session = get_session()
    try:
        doc = session.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(404, "文档不存在")

        session.delete(doc)
        session.commit()
        session.close()

        return {"success": True, "message": f"文档 {document_id} 已删除"}

    except HTTPException:
        session.close()
        raise
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(500, f"删除失败: {str(e)}")


@router.post("/knowledge", response_model=KnowledgeResponse)
async def create_knowledge(request: KnowledgeCreateRequest):
    """创建新知识库"""
    session = get_session()
    try:
        existing = session.query(Knowledge).filter(Knowledge.name == request.name).first()
        if existing:
            session.close()
            raise HTTPException(400, f"知识库 '{request.name}' 已存在")

        knowledge = Knowledge(name=request.name, description=request.description)
        session.add(knowledge)
        session.commit()

        kb_id = knowledge.id
        created_at = knowledge.created_at.strftime("%Y-%m-%d %H:%M:%S")
        updated_at = knowledge.updated_at.strftime("%Y-%m-%d %H:%M:%S")
        session.close()

        return KnowledgeResponse(
            id=kb_id,
            name=request.name,
            description=request.description,
            document_count=0,
            paragraph_count=0,
            char_length=0,
            created_at=created_at,
            updated_at=updated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(500, f"创建知识库失败: {str(e)}")


@router.get("/knowledge/list")
async def list_knowledge():
    """获取所有知识库"""
    session = get_session()
    try:
        knowledge_list = session.query(Knowledge).all()

        result = []
        for kb in knowledge_list:
            doc_count = session.query(Document).filter(Document.knowledge_id == kb.id).count()
            para_count = session.query(Paragraph).filter(Paragraph.knowledge_id == kb.id).count()
            total_chars = session.query(Document).filter(Document.knowledge_id == kb.id).with_entities(Document.char_length).all()
            char_length = sum(d[0] or 0 for d in total_chars)

            result.append({
                "id": kb.id,
                "name": kb.name,
                "description": kb.description or "",
                "document_count": doc_count,
                "paragraph_count": para_count,
                "char_length": char_length,
                "created_at": kb.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": kb.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            })

        session.close()
        return {"success": True, "knowledge_list": result}

    except Exception as e:
        session.close()
        raise HTTPException(500, f"获取知识库列表失败: {str(e)}")


@router.delete("/knowledge/{knowledge_id}")
async def delete_knowledge(knowledge_id: str):
    """删除知识库"""
    session = get_session()
    try:
        kb = session.query(Knowledge).filter(Knowledge.id == knowledge_id).first()
        if not kb:
            session.close()
            raise HTTPException(404, "知识库不存在")

        session.query(Document).filter(Document.knowledge_id == knowledge_id).delete()
        session.delete(kb)
        session.commit()
        session.close()

        return {"success": True, "message": f"知识库 {knowledge_id} 已删除"}

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(500, f"删除知识库失败: {str(e)}")


@router.get("/detail/{document_id}")
async def get_document_detail(document_id: str):
    """获取文档详情（用于预览）"""
    session = get_session()
    try:
        doc = session.query(Document).filter(Document.id == document_id).first()
        if not doc:
            session.close()
            raise HTTPException(404, "文档不存在")

        # 获取段落
        paragraphs = session.query(Paragraph).filter(
            Paragraph.document_id == document_id
        ).order_by(Paragraph.position).all()

        chunks = []
        for p in paragraphs:
            chunks.append({
                "id": p.id,
                "content": p.content,
                "title": p.title or "",
                "position": p.position
            })

        result = {
            "id": doc.id,
            "name": doc.name,
            "char_length": doc.char_length,
            "status": doc.status,
            "paragraph_count": len(paragraphs),
            "created_at": doc.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "documents": chunks,
        }

        session.close()
        return result

    except HTTPException:
        raise
    except Exception as e:
        session.close()
        raise HTTPException(500, f"获取文档详情失败: {str(e)}")


@router.get("/paragraphs/{document_id}")
async def get_document_paragraphs(document_id: str):
    """获取文档段落（用于预览）"""
    session = get_session()
    try:
        # 检查文档是否存在
        doc = session.query(Document).filter(Document.id == document_id).first()
        if not doc:
            session.close()
            raise HTTPException(404, "文档不存在")

        # 获取所有段落
        paragraphs = session.query(Paragraph).filter(
            Paragraph.document_id == document_id
        ).order_by(Paragraph.position).all()

        chunks = []
        for p in paragraphs:
            chunks.append({
                "id": p.id,
                "content": p.content,
                "title": p.title or "",
                "position": p.position
            })

        session.close()

        return {
            "success": True,
            "document_id": document_id,
            "document_name": doc.name,
            "documents": chunks,
            "total_chunks": len(chunks)
        }

    except HTTPException:
        raise
    except Exception as e:
        session.close()
        raise HTTPException(500, f"获取段落失败: {str(e)}")


@router.get("/download-source/{document_id}")
async def download_source_file(document_id: str):
    """下载源文件"""
    session = get_session()
    try:
        file_record = session.query(FileModel).filter(
            FileModel.document_id == document_id
        ).first()

        if not file_record:
            session.close()
            raise HTTPException(404, "源文件不存在")

        file_path = file_record.file_path
        file_name = file_record.file_name

        session.close()

        if not os.path.exists(file_path):
            raise HTTPException(404, "文件已丢失")

        from fastapi.responses import FileResponse
        return FileResponse(
            path=file_path,
            filename=file_name,
            media_type="application/octet-stream"
        )

    except HTTPException:
        raise
    except Exception as e:
        session.close()
        raise HTTPException(500, f"下载失败: {str(e)}")