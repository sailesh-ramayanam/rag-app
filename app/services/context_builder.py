"""Context building service for RAG pipeline Stage 3.

Builds appropriate prompts based on retrieval results and query type.
"""

from typing import List, Optional
from dataclasses import dataclass
import logging

from app.services.query_classifier import QueryType, ClassificationResult
from app.services.retrieval_router import RetrievalResult, RetrievedChunk
from app.models.chat import ChatMessage, MessageRole
from app.services.llm import ChatMessage as LLMMessage

logger = logging.getLogger(__name__)


# System prompts for different query types
SYSTEM_PROMPTS = {
    QueryType.DOCUMENT_LEVEL: """You are a helpful assistant that provides document summaries and overviews.

Instructions:
- Provide clear, comprehensive summaries based on the document information provided
- Highlight the main topics, themes, and key points
- If multiple documents are involved, organize information by document
- Be thorough but concise

Document Information:
{context}
""",

    QueryType.FOLLOW_UP: """You are a helpful assistant continuing a conversation about documents.

Instructions:
- Continue the conversation naturally based on the previous context
- Expand on previously discussed topics when asked
- If the user asks for more details, provide additional relevant information
- Reference what was previously discussed when appropriate
- If you need information not in the conversation history, politely indicate you need a more specific question

Previous Conversation Context:
{context}
""",

    QueryType.CHUNK_RETRIEVAL: """You are a helpful assistant that answers questions based on the provided document context.

Instructions:
- Answer questions based ONLY on the provided context
- If the context doesn't contain enough information to answer, say so clearly
- Cite specific parts of the documents when relevant
- Be concise but thorough
- If asked about something not in the documents, politely explain that you can only answer based on the provided documents

Context from documents:
{context}
""",

    QueryType.MIXED: """You are a helpful assistant that answers questions using both document context and conversation history.

Instructions:
- Use both the conversation history and document context to provide comprehensive answers
- Reference previous discussion points when relevant
- Incorporate new information from documents to expand on earlier topics
- Be clear about what information comes from where
- If comparing or relating topics, be explicit about the connections

Previous Conversation:
{conversation}

Document Context:
{documents}
"""
}


@dataclass
class BuiltContext:
    """Result of context building."""
    messages: List[LLMMessage]
    system_prompt: str
    # For tracking what was used
    chunk_ids_used: List[str]
    strategy_description: str


class ContextBuilder:
    """Builds appropriate LLM prompts based on retrieval results."""
    
    def build(
        self,
        query: str,
        classification: ClassificationResult,
        retrieval: RetrievalResult,
        conversation_history: List[ChatMessage],
        include_history_in_messages: bool = True
    ) -> BuiltContext:
        """
        Build LLM messages and system prompt based on query type and retrieval.
        
        Args:
            query: User's question
            classification: Query classification result
            retrieval: Retrieved content
            conversation_history: Full conversation history
            include_history_in_messages: Whether to include history as separate messages
            
        Returns:
            BuiltContext with messages ready for LLM
        """
        query_type = classification.query_type
        
        logger.info(f"Building context for query type: {query_type.value}")
        
        if query_type == QueryType.DOCUMENT_LEVEL:
            return self._build_document_level(query, retrieval)
        
        elif query_type == QueryType.FOLLOW_UP:
            return self._build_follow_up(query, retrieval, conversation_history)
        
        elif query_type == QueryType.CHUNK_RETRIEVAL:
            return self._build_chunk_retrieval(
                query, retrieval, conversation_history, include_history_in_messages
            )
        
        elif query_type == QueryType.MIXED:
            return self._build_mixed(query, retrieval, conversation_history)
        
        # Default fallback
        return self._build_chunk_retrieval(
            query, retrieval, conversation_history, include_history_in_messages
        )
    
    def _format_document_summaries(self, summaries: List[dict]) -> str:
        """Format document summaries for the prompt."""
        parts = []
        for i, summary in enumerate(summaries, 1):
            doc_info = f"""
[Document {i}: {summary['document_name']}]
- Pages: {summary.get('page_count', 'N/A')}
- Words: {summary.get('word_count', 'N/A')}

Summary:
{summary.get('summary', 'No summary available.')}
""".strip()
            parts.append(doc_info)
        
        return "\n\n---\n\n".join(parts)
    
    def _format_chunks(self, chunks: List[RetrievedChunk]) -> str:
        """Format retrieved chunks for the prompt."""
        parts = []
        for i, rc in enumerate(chunks, 1):
            page_info = f" (Page {rc.chunk.page_number})" if rc.chunk.page_number else ""
            similarity_info = f" [Relevance: {rc.similarity:.2f}]"
            parts.append(
                f"[Source {i}: {rc.document_name}{page_info}]{similarity_info}\n{rc.chunk.content}"
            )
        
        return "\n\n---\n\n".join(parts)
    
    def _format_conversation_context(self, context: List[dict]) -> str:
        """Format conversation context for the prompt."""
        parts = []
        for msg in context:
            role = msg['role'].capitalize()
            content = msg['content']
            parts.append(f"{role}: {content}")
        
        return "\n\n".join(parts)
    
    def _build_document_level(
        self,
        query: str,
        retrieval: RetrievalResult
    ) -> BuiltContext:
        """Build context for document-level queries (summaries, overviews)."""
        # Format document summaries
        context_str = self._format_document_summaries(retrieval.document_summaries)
        
        # Build system prompt
        system_prompt = SYSTEM_PROMPTS[QueryType.DOCUMENT_LEVEL].format(context=context_str)
        
        # For document-level queries, we don't include conversation history
        # as the user is asking about the document itself
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=query)
        ]
        
        return BuiltContext(
            messages=messages,
            system_prompt=system_prompt,
            chunk_ids_used=[],
            strategy_description="Document summaries only, no conversation history"
        )
    
    def _build_follow_up(
        self,
        query: str,
        retrieval: RetrievalResult,
        conversation_history: List[ChatMessage]
    ) -> BuiltContext:
        """Build context for follow-up queries."""
        # Format conversation context
        context_str = self._format_conversation_context(retrieval.conversation_context)
        
        # Build system prompt
        system_prompt = SYSTEM_PROMPTS[QueryType.FOLLOW_UP].format(context=context_str)
        
        # Include recent conversation as separate messages for better context
        messages = [LLMMessage(role="system", content=system_prompt)]
        
        # Add conversation history as messages (last 10)
        for msg in conversation_history[-10:]:
            if msg.role != MessageRole.SYSTEM:
                messages.append(LLMMessage(role=msg.role.value, content=msg.content))
        
        # Add current question
        messages.append(LLMMessage(role="user", content=query))
        
        return BuiltContext(
            messages=messages,
            system_prompt=system_prompt,
            chunk_ids_used=[],
            strategy_description="Conversation history only, answering follow-up"
        )
    
    def _build_chunk_retrieval(
        self,
        query: str,
        retrieval: RetrievalResult,
        conversation_history: List[ChatMessage],
        include_history: bool
    ) -> BuiltContext:
        """Build context for chunk retrieval queries."""
        # Format retrieved chunks
        context_str = self._format_chunks(retrieval.retrieved_chunks)
        
        # Build system prompt
        system_prompt = SYSTEM_PROMPTS[QueryType.CHUNK_RETRIEVAL].format(context=context_str)
        
        messages = [LLMMessage(role="system", content=system_prompt)]
        
        # Optionally include recent conversation for continuity
        if include_history and conversation_history:
            # Only include last 4 messages to leave room for new context
            for msg in conversation_history[-4:]:
                if msg.role != MessageRole.SYSTEM:
                    messages.append(LLMMessage(role=msg.role.value, content=msg.content))
        
        # Add current question
        messages.append(LLMMessage(role="user", content=query))
        
        # Track chunk IDs used
        chunk_ids = [str(rc.chunk.id) for rc in retrieval.retrieved_chunks]
        
        strategy = "Vector search results"
        if include_history and conversation_history:
            strategy += f" + {min(len(conversation_history), 4)} messages of history"
        
        return BuiltContext(
            messages=messages,
            system_prompt=system_prompt,
            chunk_ids_used=chunk_ids,
            strategy_description=strategy
        )
    
    def _build_mixed(
        self,
        query: str,
        retrieval: RetrievalResult,
        conversation_history: List[ChatMessage]
    ) -> BuiltContext:
        """Build context for mixed queries (history + new retrieval)."""
        # Format both conversation and document context
        conversation_str = self._format_conversation_context(retrieval.conversation_context)
        documents_str = self._format_chunks(retrieval.retrieved_chunks)
        
        # Build system prompt with both contexts
        system_prompt = SYSTEM_PROMPTS[QueryType.MIXED].format(
            conversation=conversation_str,
            documents=documents_str
        )
        
        messages = [LLMMessage(role="system", content=system_prompt)]
        
        # Include conversation history as messages
        for msg in conversation_history[-6:]:
            if msg.role != MessageRole.SYSTEM:
                messages.append(LLMMessage(role=msg.role.value, content=msg.content))
        
        # Add current question
        messages.append(LLMMessage(role="user", content=query))
        
        # Track chunk IDs
        chunk_ids = [str(rc.chunk.id) for rc in retrieval.retrieved_chunks]
        
        return BuiltContext(
            messages=messages,
            system_prompt=system_prompt,
            chunk_ids_used=chunk_ids,
            strategy_description=f"Mixed: {len(retrieval.conversation_context)} messages + {len(retrieval.retrieved_chunks)} chunks"
        )


def get_context_builder() -> ContextBuilder:
    """Factory function to get context builder instance."""
    return ContextBuilder()


