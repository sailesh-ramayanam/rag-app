"""Retrieval routing service for RAG pipeline Stage 2.

Routes queries to appropriate retrieval mechanisms based on classification.
"""

from typing import List, Optional
from uuid import UUID
from dataclasses import dataclass, field
import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.chat import ChatMessage, MessageRole
from app.services.query_classifier import QueryType, ClassificationResult
from app.services.embeddings import get_embedding_service

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A retrieved chunk with similarity score."""
    chunk: DocumentChunk
    similarity: float
    document_name: str


@dataclass
class RetrievalResult:
    """Result of the retrieval routing stage."""
    # What was retrieved
    document_summaries: List[dict] = field(default_factory=list)
    retrieved_chunks: List[RetrievedChunk] = field(default_factory=list)
    conversation_context: List[dict] = field(default_factory=list)
    
    # Metadata
    retrieval_strategy: str = ""
    search_query_used: Optional[str] = None
    
    def has_content(self) -> bool:
        """Check if any content was retrieved."""
        return bool(
            self.document_summaries or 
            self.retrieved_chunks or 
            self.conversation_context
        )


class RetrievalRouter:
    """Routes queries to appropriate retrieval mechanisms."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.embedding_service = get_embedding_service()
    
    async def route(
        self,
        classification: ClassificationResult,
        query: str,
        document_ids: List[UUID],
        conversation_history: List[ChatMessage],
        top_k: int = 5
    ) -> RetrievalResult:
        """
        Route to appropriate retrieval based on query classification.
        
        Args:
            classification: Result from query classifier
            query: Original user query
            document_ids: IDs of documents in the chat
            conversation_history: Previous messages
            top_k: Number of chunks to retrieve for vector search
            
        Returns:
            RetrievalResult with appropriate content
        """
        query_type = classification.query_type
        
        logger.info(f"Routing query type: {query_type.value}")
        
        if query_type == QueryType.DOCUMENT_LEVEL:
            return await self._retrieve_document_level(document_ids)
        
        elif query_type == QueryType.FOLLOW_UP:
            return await self._retrieve_follow_up(
                conversation_history,
                classification.referenced_topic
            )
        
        elif query_type == QueryType.CHUNK_RETRIEVAL:
            search_query = classification.search_query or query
            return await self._retrieve_chunks(
                search_query,
                document_ids,
                top_k
            )
        
        elif query_type == QueryType.MIXED:
            return await self._retrieve_mixed(
                classification,
                query,
                document_ids,
                conversation_history,
                top_k
            )
        
        # Default fallback
        return await self._retrieve_chunks(query, document_ids, top_k)
    
    async def _retrieve_document_level(
        self,
        document_ids: List[UUID]
    ) -> RetrievalResult:
        """
        Retrieve document summaries for document-level queries.
        
        For queries like "Summarize this document" or "What is this about?"
        """
        summaries = []
        
        for doc_id in document_ids:
            result = await self.session.execute(
                select(Document).where(Document.id == doc_id)
            )
            doc = result.scalar_one_or_none()
            
            if doc and doc.status == ProcessingStatus.COMPLETED:
                summary_data = {
                    "document_id": str(doc.id),
                    "document_name": doc.original_filename,
                    "page_count": doc.page_count,
                    "word_count": doc.word_count,
                    "chunk_count": doc.chunk_count,
                    "summary": doc.summary or "Summary not available for this document."
                }
                summaries.append(summary_data)
        
        logger.info(f"Retrieved {len(summaries)} document summaries")
        
        return RetrievalResult(
            document_summaries=summaries,
            retrieval_strategy="document_summaries"
        )
    
    async def _retrieve_follow_up(
        self,
        conversation_history: List[ChatMessage],
        referenced_topic: Optional[str]
    ) -> RetrievalResult:
        """
        Retrieve conversation context for follow-up queries.
        
        For queries like "Tell me more" or "Can you elaborate?"
        """
        context = []
        
        # Get recent conversation (last 6 messages = 3 exchanges)
        recent_messages = conversation_history[-6:]
        
        for msg in recent_messages:
            context.append({
                "role": msg.role.value,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None
            })
        
        logger.info(f"Retrieved {len(context)} messages for follow-up context")
        
        return RetrievalResult(
            conversation_context=context,
            retrieval_strategy="conversation_history",
            search_query_used=referenced_topic
        )
    
    async def _retrieve_chunks(
        self,
        query: str,
        document_ids: List[UUID],
        top_k: int
    ) -> RetrievalResult:
        """
        Retrieve relevant chunks using vector similarity search.
        
        For specific topic queries that need document search.
        """
        # Generate query embedding
        query_embedding = self.embedding_service.generate_embedding(query)
        
        # Convert UUIDs to strings for the query
        doc_ids_str = ",".join(f"'{str(did)}'" for did in document_ids)
        
        # Use pgvector's cosine distance operator (<=>)
        query_sql = text(f"""
            SELECT 
                dc.id,
                dc.document_id,
                dc.content,
                dc.chunk_index,
                dc.page_number,
                d.original_filename,
                1 - (dc.embedding <=> :embedding) as similarity
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE dc.document_id IN ({doc_ids_str})
            AND dc.embedding IS NOT NULL
            ORDER BY dc.embedding <=> :embedding
            LIMIT :limit
        """)
        
        result = await self.session.execute(
            query_sql,
            {"embedding": str(query_embedding), "limit": top_k}
        )
        rows = result.fetchall()
        
        # Get full chunk objects
        retrieved = []
        for row in rows:
            chunk_result = await self.session.execute(
                select(DocumentChunk).where(DocumentChunk.id == row.id)
            )
            chunk = chunk_result.scalar_one()
            
            retrieved.append(RetrievedChunk(
                chunk=chunk,
                similarity=float(row.similarity),
                document_name=row.original_filename
            ))
        
        logger.info(f"Retrieved {len(retrieved)} chunks for query: {query[:50]}...")
        
        return RetrievalResult(
            retrieved_chunks=retrieved,
            retrieval_strategy="vector_search",
            search_query_used=query
        )
    
    async def _retrieve_mixed(
        self,
        classification: ClassificationResult,
        query: str,
        document_ids: List[UUID],
        conversation_history: List[ChatMessage],
        top_k: int
    ) -> RetrievalResult:
        """
        Retrieve both conversation context and document chunks.
        
        For queries that need both history and new information.
        """
        # Get conversation context
        conversation_context = []
        recent_messages = conversation_history[-6:]
        for msg in recent_messages:
            conversation_context.append({
                "role": msg.role.value,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None
            })
        
        # Get chunks using the optimized search query
        search_query = classification.search_query or query
        chunk_result = await self._retrieve_chunks(search_query, document_ids, top_k)
        
        logger.info(
            f"Mixed retrieval: {len(conversation_context)} messages, "
            f"{len(chunk_result.retrieved_chunks)} chunks"
        )
        
        return RetrievalResult(
            retrieved_chunks=chunk_result.retrieved_chunks,
            conversation_context=conversation_context,
            retrieval_strategy="mixed",
            search_query_used=search_query
        )


def get_retrieval_router(session: AsyncSession) -> RetrievalRouter:
    """Factory function to get retrieval router instance."""
    return RetrievalRouter(session)


