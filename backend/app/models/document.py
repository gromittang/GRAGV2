"""
数据模型 - SQLite
支持多任务状态管理
"""
from sqlalchemy import Column, String, Integer, Boolean, JSON, DateTime, ForeignKey, Text, Float, create_engine, event, text
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from datetime import datetime
import uuid
import os

Base = declarative_base()


class Knowledge(Base):
    """知识库表"""
    __tablename__ = 'knowledge'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(150), nullable=False, index=True)
    description = Column(String(256), default='')
    workspace_id = Column(String(64), default='default', index=True)
    type = Column(Integer, default=0)
    embedding_model_id = Column(String(36), nullable=True)
    file_size_limit = Column(Integer, default=100)
    file_count_limit = Column(Integer, default=50)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    documents = relationship("Document", back_populates="knowledge")
    tags = relationship("Tag", back_populates="knowledge")


class Document(Base):
    """文档表"""
    __tablename__ = 'document'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    knowledge_id = Column(String(36), ForeignKey('knowledge.id'), nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    char_length = Column(Integer, default=0)
    status = Column(String(20), default='0', index=True)  # 0=PENDING, 1=STARTED, 2=SUCCESS, 3=FAILURE
    status_meta = Column(JSON, default=lambda: {"state_time": {}, "progress": 0})
    is_active = Column(Boolean, default=True, index=True)
    type = Column(Integer, default=0)
    hit_handling_method = Column(String(20), default='optimization')
    directly_return_similarity = Column(Float, default=0.9)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    knowledge = relationship("Knowledge", back_populates="documents")
    paragraphs = relationship("Paragraph", back_populates="document", cascade="all, delete-orphan")
    tags = relationship("DocumentTag", back_populates="document", cascade="all, delete-orphan")
    file = relationship("File", back_populates="document", uselist=False)


class Paragraph(Base):
    """段落/分块表"""
    __tablename__ = 'paragraph'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey('document.id'), nullable=False, index=True)
    knowledge_id = Column(String(36), ForeignKey('knowledge.id'), nullable=False, index=True)
    content = Column(Text, nullable=False)
    title = Column(String(256), default='', index=True)
    status = Column(String(20), default='0')
    status_meta = Column(JSON, default=lambda: {"state_time": {}})
    hit_num = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, index=True)
    position = Column(Integer, default=0, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="paragraphs")


class Tag(Base):
    """标签表"""
    __tablename__ = 'tag'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    knowledge_id = Column(String(36), ForeignKey('knowledge.id'), index=True)
    key = Column(String(64), index=True)
    value = Column(String(128), index=True)
    color = Column(String(16), default='#3B82F6')
    created_at = Column(DateTime, default=datetime.utcnow)

    knowledge = relationship("Knowledge", back_populates="tags")


class DocumentTag(Base):
    """文档标签关联表"""
    __tablename__ = 'document_tag'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey('document.id'), index=True)
    tag_id = Column(String(36), ForeignKey('tag.id'), index=True)

    document = relationship("Document", back_populates="tags")
    tag = relationship("Tag")


class File(Base):
    """源文件表"""
    __tablename__ = 'file'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey('document.id'), index=True)
    file_name = Column(String(256), nullable=False)
    file_size = Column(Integer, default=0)
    file_path = Column(String(512))
    file_type = Column(String(20), default='')
    sha256_hash = Column(String(64), index=True)
    source_type = Column(String(20), default='DOCUMENT')
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="file")


# 数据库引擎和会话
_engine = None
_session_factory = None


def _set_sqlite_pragma(connection, branch):
    """SQLite连接初始化"""
    if branch:
        return
    connection.execute(text("PRAGMA foreign_keys = ON"))
    connection.execute(text("PRAGMA journal_mode = WAL"))


def get_engine():
    """获取SQLite数据库引擎"""
    global _engine
    if _engine is None:
        from app.config import get_settings
        settings = get_settings()
        _engine = create_engine(
            settings.sqlite_connection_url,
            echo=False,
            connect_args={"check_same_thread": False}
        )
        event.listen(_engine, 'connect', _set_sqlite_pragma)
    return _engine


def get_session():
    """获取数据库会话"""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(bind=engine)
    return _session_factory()


def init_db():
    """初始化数据库，创建所有表"""
    engine = get_engine()
    # 导入 PM 模型确保表也被创建
    from app.models.pm_solution import PMSession, PMStage, PMChat
    Base.metadata.create_all(engine)
    print("SQLite数据库表创建完成（包含PM方案表）")


def get_or_create_knowledge(session, name: str = "默认知识库") -> Knowledge:
    """获取或创建知识库"""
    knowledge = session.query(Knowledge).filter(Knowledge.name == name).first()
    if knowledge is None:
        knowledge = Knowledge(name=name)
        session.add(knowledge)
        session.commit()
    return knowledge