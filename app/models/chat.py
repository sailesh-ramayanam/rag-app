"""Chat models for document Q&A."""

import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Table, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship

from app.core.database import Base


class MessageRole(str, Enum):
    """Chat message role."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# Junction table: Chat <-> Document (many-to-many)
chat_documents = Table(
    "chat_documents",
    Base.metadata,
    Column("chat_id", UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True),
    Column("document_id", UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
)


# Junction table: ChatMessage <-> DocumentChunk (many-to-many for retrieved chunks)
message_chunks = Table(
    "message_chunks",
    Base.metadata,
    Column("message_id", UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), primary_key=True),
    Column("chunk_id", UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), primary_key=True),
    Column("similarity_score", Integer, nullable=True),  # Store similarity for ranking
)


class Chat(Base):
    """Chat session with documents."""
    
    __tablename__ = "chats"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=True)  # Auto-generated from first question
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    documents = relationship(
        "Document",
        secondary=chat_documents,
        backref="chats",
        lazy="selectin"
    )
    messages = relationship(
        "ChatMessage",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at"
    )
    
    def __repr__(self):
        return f"<Chat(id={self.id}, title={self.title})>"


class ChatMessage(Base):
    """Individual message in a chat."""
    
    __tablename__ = "chat_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    
    # Message content
    role = Column(SQLEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    chat = relationship("Chat", back_populates="messages")
    retrieved_chunks = relationship(
        "DocumentChunk",
        secondary=message_chunks,
        backref="messages",
        lazy="selectin"
    )
    
    def __repr__(self):
        return f"<ChatMessage(id={self.id}, role={self.role})>"

