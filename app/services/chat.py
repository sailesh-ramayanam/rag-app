"""Chat service for document Q&A with RAG."""

from typing import List, Optional, Tuple
from uuid import UUID
from dataclasses import dataclass
import logging

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.chat import Chat, ChatMessage, MessageRole, chat_documents
from app.services.llm import get_llm, ChatMessage as LLMMessage
from app.services.embeddings import get_embedding_service
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A retrieved chunk with similarity score."""
    chunk: DocumentChunk
    similarity: float
    document_name: str


@dataclass
class ChatResponse:
    """Response from chat service."""
    answer: str
    sources: List[dict]
    message_id: UUID


SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the provided document context.

Instructions:
- Answer questions based ONLY on the provided context
- If the context doesn't contain enough information to answer, say so clearly
- Cite specific parts of the documents when relevant
- Be concise but thorough
- If asked about something not in the documents, politely explain that you can only answer based on the provided documents

Context from documents:
{context}
"""


class ChatService:
    """Service for handling document chat with RAG."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm = get_llm()
        self.embedding_service = get_embedding_service()
    
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
    
    async def _retrieve_chunks(
        self,
        query: str,
        document_ids: List[UUID],
        top_k: int = 5
    ) -> List[RetrievedChunk]:
        """
        Retrieve top-k most relevant chunks for a query.
        
        Uses cosine similarity with pgvector.
        """
        # Generate query embedding
        query_embedding = self.embedding_service.generate_embedding(query)
        
        # Build query for vector similarity search
        # Filter by document_ids and order by cosine distance
        from sqlalchemy import text
        
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
        
        return retrieved
    
    def _build_context(self, chunks: List[RetrievedChunk]) -> str:
        """Build context string from retrieved chunks."""
        context_parts = []
        
        for i, rc in enumerate(chunks, 1):
            page_info = f" (Page {rc.chunk.page_number})" if rc.chunk.page_number else ""
            context_parts.append(
                f"[Source {i}: {rc.document_name}{page_info}]\n{rc.chunk.content}"
            )
        
        return "\n\n---\n\n".join(context_parts)
    
    def _build_messages(
        self,
        history: List[ChatMessage],
        context: str,
        question: str
    ) -> List[LLMMessage]:
        """Build messages for LLM from history and new question."""
        messages = [
            LLMMessage(role="system", content=SYSTEM_PROMPT.format(context=context))
        ]
        
        # Add conversation history (skip system messages, limit history)
        for msg in history[-10:]:  # Last 10 messages for context window
            if msg.role != MessageRole.SYSTEM:
                messages.append(LLMMessage(role=msg.role.value, content=msg.content))
        
        # Add current question
        messages.append(LLMMessage(role="user", content=question))
        
        return messages
    
    async def ask(
        self,
        chat_id: UUID,
        question: str,
        top_k: int = 5
    ) -> ChatResponse:
        """
        Ask a question in a chat session.
        
        Args:
            chat_id: Chat session ID
            question: User's question
            top_k: Number of chunks to retrieve
            
        Returns:
            ChatResponse with answer and sources
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
        
        # Retrieve relevant chunks
        retrieved_chunks = await self._retrieve_chunks(question, document_ids, top_k)
        
        if not retrieved_chunks:
            raise ValueError("No relevant content found in documents")
        
        # Build context and messages
        context = self._build_context(retrieved_chunks)
        messages = self._build_messages(list(chat.messages), context, question)
        
        # Generate response
        logger.info(f"Generating response for chat {chat_id}")
        response = await self.llm.agenerate(messages)
        
        # Save user message with retrieved chunks
        user_message = ChatMessage(
            chat_id=chat_id,
            role=MessageRole.USER,
            content=question
        )
        user_message.retrieved_chunks = [rc.chunk for rc in retrieved_chunks]
        self.session.add(user_message)
        
        # Save assistant message
        assistant_message = ChatMessage(
            chat_id=chat_id,
            role=MessageRole.ASSISTANT,
            content=response.content
        )
        self.session.add(assistant_message)
        
        # Update chat title if first message
        if not chat.title and len(chat.messages) == 0:
            # Generate title from first question (truncated)
            chat.title = question[:100] + ("..." if len(question) > 100 else "")
        
        await self.session.commit()
        await self.session.refresh(assistant_message)
        
        # Build sources
        sources = [
            {
                "document_id": str(rc.chunk.document_id),
                "document_name": rc.document_name,
                "chunk_content": rc.chunk.content[:500] + "..." if len(rc.chunk.content) > 500 else rc.chunk.content,
                "page_number": rc.chunk.page_number,
                "similarity": round(rc.similarity, 4)
            }
            for rc in retrieved_chunks
        ]
        
        return ChatResponse(
            answer=response.content,
            sources=sources,
            message_id=assistant_message.id
        )


async def get_chat_service(session: AsyncSession) -> ChatService:
    """Factory function to get chat service instance."""
    return ChatService(session)

