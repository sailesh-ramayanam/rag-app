"""Document management API endpoints."""

import os
import uuid
import aiofiles
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_async_session
from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.services.document_processor import get_mime_type, is_supported_file
from app.tasks.document_tasks import process_document_task
from app.api.schemas import (
    DocumentUploadResponse,
    DocumentResponse,
    DocumentListResponse,
    DocumentChunkResponse,
    ProcessingStatsResponse,
    ErrorResponse,
)

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Upload a document for processing.
    
    Supported formats: PDF, DOCX, TXT
    
    The document will be:
    1. Saved to storage
    2. Queued for async processing
    3. Text extracted, chunked, and embedded
    """
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    if not is_supported_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Supported: PDF, DOCX, TXT"
        )
    
    # Generate unique filename
    file_id = uuid.uuid4()
    file_extension = Path(file.filename).suffix
    unique_filename = f"{file_id}{file_extension}"
    
    # Create storage directory if needed
    storage_path = Path(settings.storage_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    
    file_path = storage_path / unique_filename
    
    try:
        # Save file
        content = await file.read()
        file_size = len(content)
        
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
        
        # Create document record
        document = Document(
            id=file_id,
            filename=unique_filename,
            original_filename=file.filename,
            file_path=str(file_path),
            file_size=file_size,
            mime_type=get_mime_type(file.filename),
            status=ProcessingStatus.PENDING,
        )
        
        session.add(document)
        await session.commit()
        await session.refresh(document)
        
        # Queue processing task
        process_document_task.delay(str(document.id))
        
        return DocumentUploadResponse(
            id=document.id,
            filename=document.filename,
            original_filename=document.original_filename,
            file_size=document.file_size,
            mime_type=document.mime_type,
            status=document.status,
            message="Document uploaded successfully. Processing started.",
        )
        
    except Exception as e:
        # Clean up file if saved
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get(
    "/",
    response_model=DocumentListResponse,
)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: Optional[ProcessingStatus] = None,
    session: AsyncSession = Depends(get_async_session),
):
    """
    List all documents with pagination.
    
    Optional filters:
    - status: Filter by processing status
    """
    # Build query
    query = select(Document).order_by(Document.created_at.desc())
    count_query = select(func.count(Document.id))
    
    if status:
        query = query.where(Document.status == status)
        count_query = count_query.where(Document.status == status)
    
    # Get total count
    total = (await session.execute(count_query)).scalar()
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await session.execute(query)
    documents = result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size
    
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(doc) for doc in documents],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Get document details by ID."""
    result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return DocumentResponse.model_validate(document)


@router.get(
    "/{document_id}/download",
    responses={404: {"model": ErrorResponse}},
)
async def download_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Download the original document file."""
    result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(
        path=file_path,
        filename=document.original_filename,
        media_type=document.mime_type,
    )


@router.get(
    "/{document_id}/chunks",
    response_model=list[DocumentChunkResponse],
    responses={404: {"model": ErrorResponse}},
)
async def get_document_chunks(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Get all chunks for a document."""
    # Verify document exists
    doc_result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    if not doc_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get chunks
    result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = result.scalars().all()
    
    return [DocumentChunkResponse.model_validate(chunk) for chunk in chunks]


@router.delete(
    "/{document_id}",
    responses={404: {"model": ErrorResponse}},
)
async def delete_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a document and its chunks."""
    result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete file from storage
    file_path = Path(document.file_path)
    if file_path.exists():
        file_path.unlink()
    
    # Delete document (chunks cascade)
    await session.delete(document)
    await session.commit()
    
    return {"message": "Document deleted successfully"}


@router.get(
    "/stats/overview",
    response_model=ProcessingStatsResponse,
)
async def get_processing_stats(
    session: AsyncSession = Depends(get_async_session),
):
    """Get document processing statistics."""
    # Count by status
    status_counts = {}
    for status in ProcessingStatus:
        result = await session.execute(
            select(func.count(Document.id)).where(Document.status == status)
        )
        status_counts[status.value] = result.scalar()
    
    # Total documents
    total_result = await session.execute(select(func.count(Document.id)))
    total_documents = total_result.scalar()
    
    # Total chunks
    chunks_result = await session.execute(select(func.count(DocumentChunk.id)))
    total_chunks = chunks_result.scalar()
    
    # Total words
    words_result = await session.execute(
        select(func.coalesce(func.sum(Document.word_count), 0))
    )
    total_words = words_result.scalar()
    
    return ProcessingStatsResponse(
        total_documents=total_documents,
        pending=status_counts.get("pending", 0),
        processing=status_counts.get("processing", 0),
        completed=status_counts.get("completed", 0),
        failed=status_counts.get("failed", 0),
        total_chunks=total_chunks,
        total_words=total_words,
    )

