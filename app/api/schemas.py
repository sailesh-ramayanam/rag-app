"""Pydantic schemas for API requests and responses."""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.document import ProcessingStatus


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document."""
    id: UUID
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    status: ProcessingStatus
    message: str
    
    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    """Full document details response."""
    id: UUID
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    status: ProcessingStatus
    status_message: Optional[str]
    page_count: Optional[int]
    word_count: Optional[int]
    chunk_count: int
    created_at: datetime
    updated_at: Optional[datetime]
    processed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class DocumentChunkResponse(BaseModel):
    """Document chunk response."""
    id: UUID
    document_id: UUID
    content: str
    chunk_index: int
    page_number: Optional[int]
    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""
    documents: List[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProcessingStatsResponse(BaseModel):
    """Document processing statistics."""
    total_documents: int
    pending: int
    processing: int
    completed: int
    failed: int
    total_chunks: int
    total_words: int


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None

