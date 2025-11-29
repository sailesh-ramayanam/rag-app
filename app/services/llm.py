"""LLM service with configurable providers."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass
import logging

from openai import OpenAI, AsyncOpenAI

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """Represents a chat message for LLM."""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None


class BaseLLM(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def generate(
        self,
        messages: List[ChatMessage],
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a response from the LLM."""
        pass
    
    @abstractmethod
    async def agenerate(
        self,
        messages: List[ChatMessage],
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Async generate a response from the LLM."""
        pass
    
    @abstractmethod
    async def astream(
        self,
        messages: List[ChatMessage],
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response from the LLM."""
        pass


class OpenAILLM(BaseLLM):
    """OpenAI LLM implementation."""
    
    def __init__(
        self,
        api_key: str = None,
        model: str = None,
    ):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.llm_model
        self.client = OpenAI(api_key=self.api_key)
        self.async_client = AsyncOpenAI(api_key=self.api_key)
    
    def _format_messages(self, messages: List[ChatMessage]) -> List[Dict[str, str]]:
        """Format messages for OpenAI API."""
        return [{"role": m.role, "content": m.content} for m in messages]
    
    def generate(
        self,
        messages: List[ChatMessage],
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a response using OpenAI."""
        kwargs = {
            "model": self.model,
            "messages": self._format_messages(messages),
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        
        response = self.client.chat.completions.create(**kwargs)
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        )
    
    async def agenerate(
        self,
        messages: List[ChatMessage],
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Async generate a response using OpenAI."""
        kwargs = {
            "model": self.model,
            "messages": self._format_messages(messages),
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        
        response = await self.async_client.chat.completions.create(**kwargs)
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        )
    
    async def astream(
        self,
        messages: List[ChatMessage],
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response from OpenAI."""
        kwargs = {
            "model": self.model,
            "messages": self._format_messages(messages),
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        
        stream = await self.async_client.chat.completions.create(**kwargs)
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class LLMFactory:
    """Factory for creating LLM instances."""
    
    _providers = {
        "openai": OpenAILLM,
    }
    
    @classmethod
    def register_provider(cls, name: str, provider_class: type):
        """Register a new LLM provider."""
        cls._providers[name] = provider_class
    
    @classmethod
    def create(cls, provider: str = None, **kwargs) -> BaseLLM:
        """Create an LLM instance.
        
        Args:
            provider: LLM provider name (default from settings)
            **kwargs: Additional arguments for the provider
            
        Returns:
            LLM instance
        """
        provider = provider or settings.llm_provider
        
        if provider not in cls._providers:
            raise ValueError(f"Unknown LLM provider: {provider}. Available: {list(cls._providers.keys())}")
        
        logger.info(f"Creating LLM instance for provider: {provider}")
        return cls._providers[provider](**kwargs)


def get_llm() -> BaseLLM:
    """Get default LLM instance."""
    return LLMFactory.create()

