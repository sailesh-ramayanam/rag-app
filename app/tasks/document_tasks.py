"""Celery tasks for document processing."""

import logging
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from openai import OpenAI

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


def generate_document_summary(text: str, filename: str, max_chars: int = 10000) -> str:
    """
    Generate a summary of the document using the LLM.
    
    Args:
        text: Full document text
        filename: Name of the document
        max_chars: Maximum characters to send to LLM for summary generation
        
    Returns:
        Generated summary string
    """
    try:
        # Use OpenAI client synchronously for Celery task
        client = OpenAI(api_key=settings.openai_api_key)
        
        # Truncate text if too long (use beginning and end for better coverage)
        if len(text) > max_chars:
            half = max_chars // 2
            text_for_summary = text[:half] + "\n\n[... content truncated ...]\n\n" + text[-half:]
        else:
            text_for_summary = text
        
        prompt = f"""Analyze the following document and provide a comprehensive summary.

Document Name: {filename}

Document Content:
{text_for_summary}

Please provide a summary that includes:
1. Main topic/purpose of the document
2. Key points and themes
3. Important findings, conclusions, or recommendations (if applicable)
4. Target audience or context (if identifiable)

Keep the summary concise but informative (2-4 paragraphs)."""

        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        summary = response.choices[0].message.content
        logger.info(f"Generated summary for {filename}")
        return summary
        
    except Exception as e:
        logger.error(f"Error generating summary for {filename}: {e}")
        return f"Summary generation failed: {str(e)[:200]}"


@celery_app.task(bind=True, max_retries=3)
def process_document_task(self, document_id: str):
    """
    Process a document: extract text, create chunks, generate embeddings, and create summary.
    
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
        
        # Step 5: Generate document summary
        document.status_message = "Generating document summary..."
        session.commit()
        
        logger.info(f"Generating summary for {document.filename}")
        summary = generate_document_summary(text, document.original_filename)
        document.summary = summary
        
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
            "summary_generated": bool(summary),
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


@celery_app.task(bind=True, max_retries=2)
def regenerate_summary_task(self, document_id: str):
    """
    Regenerate the summary for an existing processed document.
    
    Useful for documents that were processed before summary generation was added,
    or to update summaries with improved prompts.
    
    Args:
        document_id: UUID of the document
    """
    session = SyncSession()
    
    try:
        document = session.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            logger.error(f"Document {document_id} not found")
            return {"status": "error", "message": "Document not found"}
        
        if document.status != ProcessingStatus.COMPLETED:
            return {"status": "error", "message": f"Document not processed: {document.status.value}"}
        
        logger.info(f"Regenerating summary for document: {document.filename}")
        
        # Re-extract text
        processor = DocumentProcessor(document.file_path)
        text, _ = processor.extract_text()
        
        # Generate new summary
        summary = generate_document_summary(text, document.original_filename)
        document.summary = summary
        session.commit()
        
        logger.info(f"Successfully regenerated summary for {document.filename}")
        
        return {
            "status": "success",
            "document_id": str(document.id),
            "summary_generated": bool(summary),
        }
        
    except Exception as e:
        logger.exception(f"Error regenerating summary for {document_id}: {e}")
        session.rollback()
        raise self.retry(exc=e, countdown=30)
        
    finally:
        session.close()
