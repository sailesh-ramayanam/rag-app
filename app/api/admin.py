"""Admin API endpoints for usage analytics."""

from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.database import get_async_session
from app.models.llm_usage import LLMUsageLog, LLMApiType
from app.models.chat import Chat

router = APIRouter(prefix="/admin", tags=["admin"])


class ChatUsageResponse(BaseModel):
    """Token usage for a single chat."""
    chat_id: UUID
    chat_title: Optional[str]
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    message_count: int
    created_at: str
    last_activity: Optional[str]
    
    class Config:
        from_attributes = True


class ChatUsageListResponse(BaseModel):
    """Paginated list of chat usage."""
    chats: List[ChatUsageResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class UsageSummaryResponse(BaseModel):
    """Overall usage summary."""
    total_chats: int
    total_messages: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_embedding_tokens: int


@router.get(
    "/usage/chats",
    response_model=ChatUsageListResponse,
)
async def get_chat_usage(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
):
    """Get token usage statistics per chat with pagination."""
    
    # Subquery for aggregated usage per chat
    usage_subquery = (
        select(
            LLMUsageLog.chat_id,
            func.sum(LLMUsageLog.input_tokens).label("total_input_tokens"),
            func.coalesce(func.sum(LLMUsageLog.output_tokens), 0).label("total_output_tokens"),
            func.count(LLMUsageLog.id).label("api_call_count"),
            func.max(LLMUsageLog.created_at).label("last_activity"),
        )
        .where(LLMUsageLog.chat_id.isnot(None))
        .where(LLMUsageLog.api_type == LLMApiType.CHAT_COMPLETION)
        .group_by(LLMUsageLog.chat_id)
        .subquery()
    )
    
    # Count total chats with usage
    count_query = select(func.count()).select_from(usage_subquery)
    total = (await session.execute(count_query)).scalar() or 0
    
    # Main query joining with Chat
    query = (
        select(
            Chat.id,
            Chat.title,
            Chat.created_at,
            usage_subquery.c.total_input_tokens,
            usage_subquery.c.total_output_tokens,
            usage_subquery.c.api_call_count,
            usage_subquery.c.last_activity,
        )
        .join(usage_subquery, Chat.id == usage_subquery.c.chat_id)
        .order_by(usage_subquery.c.last_activity.desc())
    )
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await session.execute(query)
    rows = result.all()
    
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    chats = []
    for row in rows:
        input_tokens = row.total_input_tokens or 0
        output_tokens = row.total_output_tokens or 0
        chats.append(ChatUsageResponse(
            chat_id=row.id,
            chat_title=row.title,
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            message_count=row.api_call_count or 0,
            created_at=row.created_at.isoformat() if row.created_at else "",
            last_activity=row.last_activity.isoformat() if row.last_activity else None,
        ))
    
    return ChatUsageListResponse(
        chats=chats,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/usage/summary",
    response_model=UsageSummaryResponse,
)
async def get_usage_summary(
    session: AsyncSession = Depends(get_async_session),
):
    """Get overall usage summary across all chats."""
    
    # Count total chats
    chat_count = await session.execute(select(func.count(Chat.id)))
    total_chats = chat_count.scalar() or 0
    
    # Count chat completion usage
    chat_usage = await session.execute(
        select(
            func.count(LLMUsageLog.id),
            func.coalesce(func.sum(LLMUsageLog.input_tokens), 0),
            func.coalesce(func.sum(LLMUsageLog.output_tokens), 0),
        )
        .where(LLMUsageLog.api_type == LLMApiType.CHAT_COMPLETION)
    )
    chat_row = chat_usage.one()
    total_messages = chat_row[0] or 0
    total_input_tokens = chat_row[1] or 0
    total_output_tokens = chat_row[2] or 0
    
    # Count embedding usage
    embedding_usage = await session.execute(
        select(func.coalesce(func.sum(LLMUsageLog.input_tokens), 0))
        .where(LLMUsageLog.api_type == LLMApiType.EMBEDDING)
    )
    total_embedding_tokens = embedding_usage.scalar() or 0
    
    return UsageSummaryResponse(
        total_chats=total_chats,
        total_messages=total_messages,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_tokens=total_input_tokens + total_output_tokens,
        total_embedding_tokens=total_embedding_tokens,
    )

