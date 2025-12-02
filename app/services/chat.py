"""Chat service for document Q&A with enhanced 3-stage RAG pipeline."""

from typing import List, Optional, Tuple
from uuid import UUID
from dataclasses import dataclass
import logging

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.chat import Chat, ChatMessage, MessageRole, chat_documents
from app.models.llm_usage import LLMUsageLog, LLMApiType
from app.services.llm import get_llm, ChatMessage as LLMMessage
from app.services.embeddings import get_embedding_service
from app.services.query_classifier import (
    QueryClassifier, QueryType, ClassificationResult, get_query_classifier
)
from app.services.retrieval_router import (
    RetrievalRouter, RetrievalResult, RetrievedChunk, get_retrieval_router
)
from app.services.context_builder import ContextBuilder, BuiltContext, get_context_builder
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    """Response from chat service."""
    answer: str
    sources: List[dict]
    message_id: UUID
    # New: metadata about how the query was processed
    query_type: str
    retrieval_strategy: str


class ChatService:
    """Service for handling document chat with enhanced 3-stage RAG pipeline.
    
    The pipeline consists of:
    1. Query Classification - Determine query type (DOCUMENT_LEVEL, FOLLOW_UP, CHUNK_RETRIEVAL, MIXED)
    2. Retrieval Routing - Route to appropriate retrieval mechanism
    3. Context Building - Build optimal prompt for the LLM
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm = get_llm()
        self.embedding_service = get_embedding_service()
        self.query_classifier = get_query_classifier()
        self.retrieval_router = get_retrieval_router(session)
        self.context_builder = get_context_builder()
    
    async def create_chat(
        self,
        document_ids: List[UUID],
        title: Optional[str] = None
    ) -> Chat:
        """
        Create a new chat session with specified documents.
        
        Args:
            document_ids: List of document IDs to chat with
            title: Optional chat title
            
        Returns:
            Created Chat object
            
        Raises:
            ValueError: If any document is not found or not processed
        """
        # Verify all documents exist and are processed
        documents = []
        for doc_id in document_ids:
            result = await self.session.execute(
                select(Document).where(Document.id == doc_id)
            )
            doc = result.scalar_one_or_none()
            
            if not doc:
                raise ValueError(f"Document {doc_id} not found")
            
            if doc.status != ProcessingStatus.COMPLETED:
                raise ValueError(
                    f"Document '{doc.original_filename}' is not ready. "
                    f"Status: {doc.status.value}"
                )
            
            documents.append(doc)
        
        # Create chat
        chat = Chat(title=title)
        chat.documents = documents
        
        self.session.add(chat)
        await self.session.commit()
        await self.session.refresh(chat)
        
        logger.info(f"Created chat {chat.id} with {len(documents)} documents")
        return chat
    
    async def get_chat(self, chat_id: UUID) -> Optional[Chat]:
        """Get a chat by ID with all relationships loaded."""
        result = await self.session.execute(
            select(Chat)
            .where(Chat.id == chat_id)
            .options(
                selectinload(Chat.documents),
                selectinload(Chat.messages).selectinload(ChatMessage.retrieved_chunks)
            )
        )
        return result.scalar_one_or_none()
    
    async def list_chats(
        self,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Chat], int]:
        """List all chats with pagination."""
        # Count total
        from sqlalchemy import func
        count_result = await self.session.execute(select(func.count(Chat.id)))
        total = count_result.scalar()
        
        # Get chats
        result = await self.session.execute(
            select(Chat)
            .options(selectinload(Chat.documents))
            .order_by(Chat.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        chats = result.scalars().all()
        
        return list(chats), total
    
    async def delete_chat(self, chat_id: UUID) -> bool:
        """Delete a chat and all its messages."""
        chat = await self.get_chat(chat_id)
        if not chat:
            return False
        
        await self.session.delete(chat)
        await self.session.commit()
        return True
    
    async def ask(
        self,
        chat_id: UUID,
        question: str,
        top_k: int = 5,
        use_smart_routing: bool = True
    ) -> ChatResponse:
        """
        Ask a question in a chat session using the 3-stage RAG pipeline.
        
        Pipeline Stages:
        1. Query Classification - Analyze query to determine type
        2. Retrieval Routing - Fetch appropriate content based on type
        3. Context Building - Build optimal prompt for LLM
        
        Args:
            chat_id: Chat session ID
            question: User's question
            top_k: Number of chunks to retrieve for vector search
            use_smart_routing: If True, uses LLM-based classification; else uses simple rules
            
        Returns:
            ChatResponse with answer, sources, and metadata
        """
        # Get chat
        chat = await self.get_chat(chat_id)
        if not chat:
            raise ValueError(f"Chat {chat_id} not found")
        
        if not chat.documents:
            raise ValueError("Chat has no documents attached")
        
        # Verify all documents are still processed
        document_ids = [doc.id for doc in chat.documents]
        for doc in chat.documents:
            if doc.status != ProcessingStatus.COMPLETED:
                raise ValueError(
                    f"Document '{doc.original_filename}' is no longer available. "
                    f"Status: {doc.status.value}"
                )
        
        conversation_history = list(chat.messages)
        
        # ===== STAGE 1: Query Classification =====
        logger.info(f"Stage 1: Classifying query for chat {chat_id}")
        
        if use_smart_routing:
            classification = await self.query_classifier.classify(
                question, conversation_history
            )
        else:
            classification = self.query_classifier.classify_simple(
                question, has_history=len(conversation_history) > 0
            )
        
        logger.info(
            f"Query classified as {classification.query_type.value} "
            f"(confidence: {classification.confidence})"
        )
        
        # ===== STAGE 2: Retrieval Routing =====
        logger.info(f"Stage 2: Routing retrieval for {classification.query_type.value}")
        
        retrieval_result = await self.retrieval_router.route(
            classification=classification,
            query=question,
            document_ids=document_ids,
            conversation_history=conversation_history,
            top_k=top_k
        )
        
        # Check if we have any content to work with
        if not retrieval_result.has_content():
            # Fallback to basic chunk retrieval if nothing was found
            logger.warning("No content retrieved, falling back to chunk retrieval")
            retrieval_result = await self.retrieval_router.route(
                classification=ClassificationResult(
                    query_type=QueryType.CHUNK_RETRIEVAL,
                    confidence=1.0,
                    reasoning="Fallback due to empty retrieval",
                    search_query=question
                ),
                query=question,
                document_ids=document_ids,
                conversation_history=conversation_history,
                top_k=top_k
            )
            
            if not retrieval_result.has_content():
                raise ValueError("No relevant content found in documents")
        
        logger.info(
            f"Retrieved: {len(retrieval_result.document_summaries)} summaries, "
            f"{len(retrieval_result.retrieved_chunks)} chunks, "
            f"{len(retrieval_result.conversation_context)} context messages"
        )
        
        # ===== STAGE 3: Context Building =====
        logger.info(f"Stage 3: Building context for LLM")
        
        # Determine if we should include history in messages
        # For CHUNK_RETRIEVAL, we might not need history if query is self-contained
        include_history = classification.query_type in [
            QueryType.FOLLOW_UP, QueryType.MIXED
        ] or len(conversation_history) > 0
        
        built_context = self.context_builder.build(
            query=question,
            classification=classification,
            retrieval=retrieval_result,
            conversation_history=conversation_history,
            include_history_in_messages=include_history
        )
        
        logger.info(f"Context built: {built_context.strategy_description}")
        
        # ===== Generate Response =====
        logger.info(f"Generating response for chat {chat_id}")
        response = await self.llm.agenerate(built_context.messages)
        
        # ===== Save Messages and Log Usage =====
        # Get the chunks that were used (for attribution)
        chunks_used = retrieval_result.retrieved_chunks
        
        # Save user message with retrieved chunks
        user_message = ChatMessage(
            chat_id=chat_id,
            role=MessageRole.USER,
            content=question
        )
        if chunks_used:
            user_message.retrieved_chunks = [rc.chunk for rc in chunks_used]
        self.session.add(user_message)
        await self.session.flush()
        
        # Save assistant message
        assistant_message = ChatMessage(
            chat_id=chat_id,
            role=MessageRole.ASSISTANT,
            content=response.content
        )
        self.session.add(assistant_message)
        
        # Log LLM usage for cost tracking
        usage_log = LLMUsageLog(
            chat_id=chat_id,
            message_id=user_message.id,
            api_type=LLMApiType.CHAT_COMPLETION,
            model=response.model,
            input_content="\n".join(f"[{m.role}]: {m.content[:200]}..." for m in built_context.messages),
            output_content=response.content,
            input_tokens=response.usage["prompt_tokens"],
            output_tokens=response.usage["completion_tokens"]
        )
        self.session.add(usage_log)
        
        # Update chat title if first message
        if not chat.title and len(chat.messages) == 0:
            chat.title = question[:100] + ("..." if len(question) > 100 else "")
        
        await self.session.commit()
        await self.session.refresh(assistant_message)
        
        # Build sources from retrieved chunks
        sources = [
            {
                "document_id": str(rc.chunk.document_id),
                "document_name": rc.document_name,
                "chunk_content": rc.chunk.content[:500] + "..." if len(rc.chunk.content) > 500 else rc.chunk.content,
                "page_number": rc.chunk.page_number,
                "similarity": round(rc.similarity, 4)
            }
            for rc in chunks_used
        ]
        
        # Also include document summaries as sources if used
        if retrieval_result.document_summaries:
            for summary in retrieval_result.document_summaries:
                sources.append({
                    "document_id": summary["document_id"],
                    "document_name": summary["document_name"],
                    "chunk_content": f"[Document Summary] {summary.get('summary', '')[:500]}...",
                    "page_number": None,
                    "similarity": 1.0  # Summaries are always relevant for document-level queries
                })
        
        return ChatResponse(
            answer=response.content,
            sources=sources,
            message_id=assistant_message.id,
            query_type=classification.query_type.value,
            retrieval_strategy=retrieval_result.retrieval_strategy
        )


async def get_chat_service(session: AsyncSession) -> ChatService:
    """Factory function to get chat service instance."""
    return ChatService(session)
