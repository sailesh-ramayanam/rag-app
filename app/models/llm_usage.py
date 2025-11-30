"""LLM usage tracking model for internal analytics."""

import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class LLMApiType(str, Enum):
    """Type of LLM API call."""
    CHAT_COMPLETION = "chat_completion"
    EMBEDDING = "embedding"


class LLMUsageLog(Base):
    """Log of LLM API calls for usage tracking and cost analysis."""
    
    __tablename__ = "llm_usage_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Optional reference to chat context (nullable for non-chat calls like embeddings)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="SET NULL"), nullable=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)
    
    # API call details
    api_type = Column(SQLEnum(LLMApiType), nullable=False)
    model = Column(String(100), nullable=False)
    
    # Content (input may be large for embeddings batch calls)
    input_content = Column(Text, nullable=True)
    output_content = Column(Text, nullable=True)
    
    # Token usage
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=True)  # Nullable for embeddings which don't have output tokens
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    chat = relationship("Chat", foreign_keys=[chat_id])
    message = relationship("ChatMessage", foreign_keys=[message_id])
    
    def __repr__(self):
        return f"<LLMUsageLog(id={self.id}, api_type={self.api_type}, model={self.model}, tokens={self.input_tokens}+{self.output_tokens})>"

