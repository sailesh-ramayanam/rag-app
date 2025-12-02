"""Query classification service for RAG pipeline Stage 1.

Classifies user queries into different categories to determine the optimal
retrieval strategy.
"""

from enum import Enum
from typing import List, Optional
from dataclasses import dataclass
import logging

from app.services.llm import get_llm, ChatMessage
from app.models.chat import ChatMessage as DBChatMessage, MessageRole

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    """Types of queries that can be made against documents."""
    
    # Questions about the document as a whole (summaries, overviews, main topics)
    DOCUMENT_LEVEL = "document_level"
    
    # Follow-up questions that depend on conversation context
    # e.g., "Tell me more", "Can you explain that?", "What else?"
    FOLLOW_UP = "follow_up"
    
    # Specific topic queries that need vector search
    # e.g., "What is the pricing model?", "Tell me about feature X"
    CHUNK_RETRIEVAL = "chunk_retrieval"
    
    # Queries that need both context from history AND new chunk retrieval
    # e.g., "Compare this with what you said earlier about..."
    MIXED = "mixed"


@dataclass
class ClassificationResult:
    """Result of query classification."""
    query_type: QueryType
    confidence: float
    reasoning: str
    # For follow-up queries, this indicates what topic from history is being referenced
    referenced_topic: Optional[str] = None
    # For chunk retrieval, this is the optimized search query
    search_query: Optional[str] = None


CLASSIFICATION_PROMPT = """You are a query classifier for a document Q&A system. Analyze the user's query and conversation history to determine the best retrieval strategy.

## Query Types:

1. **DOCUMENT_LEVEL**: Questions about the document as a whole.
   - Examples: "Summarize this document", "What is this document about?", "What are the main topics?"
   - Indicators: Words like "summary", "overview", "main points", "document", "overall"

2. **FOLLOW_UP**: Questions that reference previous conversation without introducing new topics.
   - Examples: "Tell me more", "Can you elaborate?", "What else?", "Explain that further"
   - Indicators: Pronouns like "that", "it", "this" without clear referent, continuation phrases

3. **CHUNK_RETRIEVAL**: Specific questions about topics that need searching the document.
   - Examples: "What is the pricing?", "How does feature X work?", "What are the requirements?"
   - Indicators: Specific nouns, technical terms, clear topic references

4. **MIXED**: Questions that need both conversation history AND new document search.
   - Examples: "How does this compare to what you mentioned about X?", "Is there more about the topic we discussed?"
   - Indicators: References to both past conversation AND needs new information

## Conversation History:
{history}

## Current User Query:
{query}

## Task:
Classify this query and respond in the following exact format:

QUERY_TYPE: <one of: DOCUMENT_LEVEL, FOLLOW_UP, CHUNK_RETRIEVAL, MIXED>
CONFIDENCE: <0.0-1.0>
REASONING: <brief explanation>
REFERENCED_TOPIC: <if FOLLOW_UP or MIXED, what topic from history is being referenced, else "none">
SEARCH_QUERY: <if CHUNK_RETRIEVAL or MIXED, the optimized search query to use for vector search, else "none">
"""


class QueryClassifier:
    """Classifies queries to determine optimal retrieval strategy."""
    
    def __init__(self):
        self.llm = get_llm()
    
    def _format_history(self, messages: List[DBChatMessage], max_messages: int = 10) -> str:
        """Format conversation history for the classifier prompt."""
        if not messages:
            return "No previous conversation."
        
        recent_messages = messages[-max_messages:]
        history_parts = []
        
        for msg in recent_messages:
            role = "User" if msg.role == MessageRole.USER else "Assistant"
            # Truncate long messages for classification
            content = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
            history_parts.append(f"{role}: {content}")
        
        return "\n".join(history_parts)
    
    def _parse_response(self, response: str, query: str) -> ClassificationResult:
        """Parse LLM response into ClassificationResult."""
        lines = response.strip().split("\n")
        
        # Default values
        query_type = QueryType.CHUNK_RETRIEVAL
        confidence = 0.5
        reasoning = "Unable to parse classification"
        referenced_topic = None
        search_query = query  # Default to original query
        
        for line in lines:
            line = line.strip()
            if line.startswith("QUERY_TYPE:"):
                type_str = line.split(":", 1)[1].strip().upper()
                try:
                    query_type = QueryType(type_str.lower())
                except ValueError:
                    # Try to match partial
                    if "DOCUMENT" in type_str:
                        query_type = QueryType.DOCUMENT_LEVEL
                    elif "FOLLOW" in type_str:
                        query_type = QueryType.FOLLOW_UP
                    elif "MIXED" in type_str:
                        query_type = QueryType.MIXED
            
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                    confidence = max(0.0, min(1.0, confidence))
                except ValueError:
                    pass
            
            elif line.startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()
            
            elif line.startswith("REFERENCED_TOPIC:"):
                topic = line.split(":", 1)[1].strip()
                if topic.lower() != "none":
                    referenced_topic = topic
            
            elif line.startswith("SEARCH_QUERY:"):
                sq = line.split(":", 1)[1].strip()
                if sq.lower() != "none" and sq:
                    search_query = sq
        
        return ClassificationResult(
            query_type=query_type,
            confidence=confidence,
            reasoning=reasoning,
            referenced_topic=referenced_topic,
            search_query=search_query
        )
    
    async def classify(
        self,
        query: str,
        conversation_history: List[DBChatMessage]
    ) -> ClassificationResult:
        """
        Classify a user query to determine the retrieval strategy.
        
        Args:
            query: The user's question
            conversation_history: Previous messages in the chat
            
        Returns:
            ClassificationResult with query type and metadata
        """
        # Format history for prompt
        history_str = self._format_history(conversation_history)
        
        # Build classification prompt
        prompt = CLASSIFICATION_PROMPT.format(
            history=history_str,
            query=query
        )
        
        messages = [
            ChatMessage(role="user", content=prompt)
        ]
        
        try:
            logger.info(f"Classifying query: {query[:100]}...")
            response = await self.llm.agenerate(messages)
            result = self._parse_response(response.content, query)
            logger.info(f"Query classified as {result.query_type.value} (confidence: {result.confidence})")
            return result
            
        except Exception as e:
            logger.error(f"Error classifying query: {e}")
            # Default to chunk retrieval on error
            return ClassificationResult(
                query_type=QueryType.CHUNK_RETRIEVAL,
                confidence=0.5,
                reasoning=f"Classification failed, defaulting to chunk retrieval: {str(e)}",
                search_query=query
            )
    
    def classify_simple(self, query: str, has_history: bool) -> ClassificationResult:
        """
        Simple rule-based classification without LLM call.
        
        Use this for fast classification when LLM call is not desired.
        Less accurate but much faster.
        """
        query_lower = query.lower().strip()
        
        # Document-level indicators
        document_keywords = [
            "summary", "summarize", "summarise", "overview", "main points",
            "what is this document about", "what's this document about",
            "what are the key points", "main topics", "document about",
            "overall", "general", "brief"
        ]
        
        # Follow-up indicators (only if there's history)
        follow_up_keywords = [
            "tell me more", "more about", "elaborate", "explain that",
            "what else", "anything else", "continue", "go on",
            "can you expand", "more details", "more information"
        ]
        
        # Check for document-level query
        for keyword in document_keywords:
            if keyword in query_lower:
                return ClassificationResult(
                    query_type=QueryType.DOCUMENT_LEVEL,
                    confidence=0.8,
                    reasoning=f"Query contains document-level keyword: '{keyword}'"
                )
        
        # Check for follow-up query (only if history exists)
        if has_history:
            for keyword in follow_up_keywords:
                if keyword in query_lower:
                    return ClassificationResult(
                        query_type=QueryType.FOLLOW_UP,
                        confidence=0.8,
                        reasoning=f"Query contains follow-up keyword: '{keyword}'",
                        referenced_topic="previous topic"
                    )
            
            # Very short queries with history are likely follow-ups
            if len(query.split()) <= 4 and any(
                word in query_lower for word in ["this", "that", "it", "more", "why", "how"]
            ):
                return ClassificationResult(
                    query_type=QueryType.FOLLOW_UP,
                    confidence=0.6,
                    reasoning="Short query with context reference",
                    referenced_topic="previous topic"
                )
        
        # Default to chunk retrieval
        return ClassificationResult(
            query_type=QueryType.CHUNK_RETRIEVAL,
            confidence=0.7,
            reasoning="Query appears to be a specific topic search",
            search_query=query
        )


def get_query_classifier() -> QueryClassifier:
    """Factory function to get query classifier instance."""
    return QueryClassifier()


