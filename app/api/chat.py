"""Chat API endpoints for document Q&A."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.services.chat import ChatService
from app.api.schemas import ErrorResponse

router = APIRouter(prefix="/chats", tags=["chats"])


# Request/Response schemas
class CreateChatRequest(BaseModel):
    """Request to create a new chat."""
    document_ids: List[UUID] = Field(..., min_length=1, description="Document IDs to chat with")
    title: Optional[str] = Field(None, max_length=255, description="Optional chat title")


class AskQuestionRequest(BaseModel):
    """Request to ask a question."""
    question: str = Field(..., min_length=1, max_length=10000, description="Question to ask")
    top_k: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")
    use_smart_routing: bool = Field(True, description="Use LLM-based query classification (more accurate but slower)")


class SourceResponse(BaseModel):
    """Source citation in response."""
    document_id: str
    document_name: str
    chunk_content: str
    page_number: Optional[int]
    similarity: float


class AskQuestionResponse(BaseModel):
    """Response to a question."""
    answer: str
    sources: List[SourceResponse]
    message_id: UUID
    # New: metadata about how the query was processed
    query_type: str = Field(description="Type of query: document_level, follow_up, chunk_retrieval, or mixed")
    retrieval_strategy: str = Field(description="Strategy used for retrieval: document_summaries, conversation_history, vector_search, or mixed")


class DocumentSummary(BaseModel):
    """Summary of a document in chat."""
    id: UUID
    original_filename: str
    status: str


class MessageResponse(BaseModel):
    """Chat message response."""
    id: UUID
    role: str
    content: str
    created_at: str
    
    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    """Full chat response."""
    id: UUID
    title: Optional[str]
    documents: List[DocumentSummary]
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class ChatDetailResponse(ChatResponse):
    """Chat with messages."""
    messages: List[MessageResponse]


class ChatListResponse(BaseModel):
    """Paginated list of chats."""
    chats: List[ChatResponse]
    total: int
    page: int
    page_size: int


@router.post(
    "/",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}},
)
async def create_chat(
    request: CreateChatRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Create a new chat session with specified documents.
    
    All documents must be fully processed (status: completed) before creating a chat.
    """
    service = ChatService(session)
    
    try:
        chat = await service.create_chat(
            document_ids=request.document_ids,
            title=request.title
        )
        
        return ChatResponse(
            id=chat.id,
            title=chat.title,
            documents=[
                DocumentSummary(
                    id=doc.id,
                    original_filename=doc.original_filename,
                    status=doc.status.value
                )
                for doc in chat.documents
            ],
            created_at=chat.created_at.isoformat(),
            updated_at=chat.updated_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/",
    response_model=ChatListResponse,
)
async def list_chats(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    """List all chat sessions with pagination."""
    service = ChatService(session)
    
    offset = (page - 1) * page_size
    chats, total = await service.list_chats(limit=page_size, offset=offset)
    
    return ChatListResponse(
        chats=[
            ChatResponse(
                id=chat.id,
                title=chat.title,
                documents=[
                    DocumentSummary(
                        id=doc.id,
                        original_filename=doc.original_filename,
                        status=doc.status.value
                    )
                    for doc in chat.documents
                ],
                created_at=chat.created_at.isoformat(),
                updated_at=chat.updated_at.isoformat(),
            )
            for chat in chats
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{chat_id}",
    response_model=ChatDetailResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_chat(
    chat_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Get chat details with full message history."""
    service = ChatService(session)
    
    chat = await service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    return ChatDetailResponse(
        id=chat.id,
        title=chat.title,
        documents=[
            DocumentSummary(
                id=doc.id,
                original_filename=doc.original_filename,
                status=doc.status.value
            )
            for doc in chat.documents
        ],
        messages=[
            MessageResponse(
                id=msg.id,
                role=msg.role.value,
                content=msg.content,
                created_at=msg.created_at.isoformat(),
            )
            for msg in chat.messages
        ],
        created_at=chat.created_at.isoformat(),
        updated_at=chat.updated_at.isoformat(),
    )


@router.post(
    "/{chat_id}/messages",
    response_model=AskQuestionResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def ask_question(
    chat_id: UUID,
    request: AskQuestionRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Ask a question in a chat session using the 3-stage RAG pipeline.
    
    The enhanced pipeline:
    1. **Query Classification**: Analyzes the query type (document-level, follow-up, chunk-retrieval, or mixed)
    2. **Retrieval Routing**: Routes to appropriate content based on query type
       - Document-level queries → Document summaries
       - Follow-up queries → Conversation history
       - Chunk retrieval queries → Vector search
       - Mixed queries → Both history and vector search
    3. **Context Building**: Builds optimal prompt for the LLM based on retrieved content
    
    Set `use_smart_routing=false` for faster (but less accurate) rule-based classification.
    """
    service = ChatService(session)
    
    try:
        response = await service.ask(
            chat_id=chat_id,
            question=request.question,
            top_k=request.top_k,
            use_smart_routing=request.use_smart_routing
        )
        
        return AskQuestionResponse(
            answer=response.answer,
            sources=[
                SourceResponse(**source)
                for source in response.sources
            ],
            message_id=response.message_id,
            query_type=response.query_type,
            retrieval_strategy=response.retrieval_strategy,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)


@router.delete(
    "/{chat_id}",
    responses={404: {"model": ErrorResponse}},
)
async def delete_chat(
    chat_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a chat and all its messages."""
    service = ChatService(session)
    
    deleted = await service.delete_chat(chat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    return {"message": "Chat deleted successfully"}

