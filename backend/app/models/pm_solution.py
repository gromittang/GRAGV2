"""
PM方案工作室数据模型
支持多阶段方案设计工作流
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import uuid

# 使用同一个 Base（从 document.py 导入）
from app.models.document import Base


class PMSession(Base):
    """方案会话表"""
    __tablename__ = 'pm_session'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(256), nullable=False, default='')
    knowledge_id = Column(String(36), ForeignKey('knowledge.id'), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey('document.id'), nullable=True, index=True)
    problem = Column(Text, default='')  # 问题描述
    current_stage = Column(Integer, default=0)  # 当前阶段 (0-3)
    stage_status = Column(String(20), default='active')  # active, confirmed, paused
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    stages = relationship("PMStage", back_populates="session", cascade="all, delete-orphan")
    chats = relationship("PMChat", back_populates="session", cascade="all, delete-orphan")


class PMStage(Base):
    """阶段记录表"""
    __tablename__ = 'pm_stage'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey('pm_session.id'), nullable=False, index=True)
    stage_type = Column(String(20), nullable=False, index=True)  # problem, analysis, detail, prd
    status = Column(String(20), default='pending')  # pending, active, confirmed
    output_summary = Column(Text, default='')  # 阶段输出摘要（列表显示用）
    output_data = Column(JSON, default=dict)  # 完整结构化输出数据
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)  # 确认时间

    session = relationship("PMSession", back_populates="stages")
    chats = relationship("PMChat", back_populates="stage", cascade="all, delete-orphan")


class PMChat(Base):
    """对话记录表"""
    __tablename__ = 'pm_chat'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey('pm_session.id'), nullable=False, index=True)
    stage_id = Column(String(36), ForeignKey('pm_stage.id'), nullable=True, index=True)
    role = Column(String(20), nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    sources = Column(JSON, default=list)  # 检索来源
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("PMSession", back_populates="chats")
    stage = relationship("PMStage", back_populates="chats")