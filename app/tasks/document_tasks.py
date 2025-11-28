"""Celery tasks for document processing."""

import logging
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.tasks.celery_app import celery_app
from app.core.config import get_settings
from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.services.document_processor import DocumentProcessor
from app.services.chunking import create_chunks
from app.services.embeddings import get_embedding_service

settings = get_settings()
logger = logging.getLogger(__name__)

# Create sync engine for Celery tasks
sync_engine = create_engine(settings.sync_database_url, echo=False)
SyncSession = sessionmaker(bind=sync_engine)


@celery_app.task(bind=True, max_retries=3)
def process_document_task(self, document_id: str):
    """
    Process a document: extract text, create chunks, generate embeddings.
    
    Args:
        document_id: UUID of the document to process
    """
    session = SyncSession()
    
    try:
        # Get document
        document = session.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            logger.error(f"Document {document_id} not found")
            return {"status": "error", "message": "Document not found"}
        
        # Update status to processing
        document.status = ProcessingStatus.PROCESSING
        document.status_message = "Extracting text from document..."
        session.commit()
        
        logger.info(f"Processing document: {document.filename}")
        
        # Step 1: Extract text
        processor = DocumentProcessor(document.file_path)
        text, metadata = processor.extract_text()
        
        document.page_count = metadata.get("page_count")
        document.word_count = metadata.get("word_count")
        document.status_message = "Creating chunks..."
        session.commit()
        
        logger.info(f"Extracted {document.word_count} words from {document.filename}")
        
        # Step 2: Create chunks
        chunks = create_chunks(text)
        
        document.chunk_count = len(chunks)
        document.status_message = f"Generating embeddings for {len(chunks)} chunks..."
        session.commit()
        
        logger.info(f"Created {len(chunks)} chunks for {document.filename}")
        
        # Step 3: Generate embeddings
        embedding_service = get_embedding_service()
        chunk_texts = [chunk.content for chunk in chunks]
        embeddings = embedding_service.generate_embeddings_batch(chunk_texts)
        
        logger.info(f"Generated embeddings for {document.filename}")
        
        # Step 4: Store chunks with embeddings
        for chunk, embedding in zip(chunks, embeddings):
            db_chunk = DocumentChunk(
                document_id=document.id,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                embedding=embedding,
            )
            session.add(db_chunk)
        
        # Update document status
        document.status = ProcessingStatus.COMPLETED
        document.status_message = "Processing completed successfully"
        document.processed_at = datetime.utcnow()
        session.commit()
        
        logger.info(f"Successfully processed document: {document.filename}")
        
        return {
            "status": "success",
            "document_id": str(document.id),
            "chunks_created": len(chunks),
            "word_count": document.word_count,
        }
        
    except Exception as e:
        logger.exception(f"Error processing document {document_id}: {e}")
        session.rollback()
        
        # Update document status to failed
        try:
            document = session.query(Document).filter(Document.id == document_id).first()
            if document:
                document.status = ProcessingStatus.FAILED
                document.status_message = str(e)[:500]  # Limit error message length
                session.commit()
        except Exception:
            pass
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        
    finally:
        session.close()

