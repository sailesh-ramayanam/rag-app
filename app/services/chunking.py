"""Text chunking service using LlamaIndex."""

from typing import List
from dataclasses import dataclass

from llama_index.core.node_parser import SentenceSplitter

from app.core.config import get_settings

settings = get_settings()


@dataclass
class TextChunk:
    """Represents a chunk of text with metadata."""
    content: str
    chunk_index: int
    start_char: int
    end_char: int
    page_number: int | None = None


class TextChunker:
    """Handles splitting text into chunks for embedding using LlamaIndex."""
    
    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap
        
        self.splitter = SentenceSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
    
    def chunk_text(self, text: str) -> List[TextChunk]:
        """
        Split text into chunks with metadata.
        
        Args:
            text: The full document text
            
        Returns:
            List of TextChunk objects
        """
        # Use LlamaIndex's splitter to get text chunks
        chunk_texts = self.splitter.split_text(text)
        
        chunks = []
        current_pos = 0
        
        for idx, content in enumerate(chunk_texts):
            # Find position in original text
            start_char = text.find(content, current_pos)
            if start_char == -1:
                start_char = current_pos
            end_char = start_char + len(content)
            current_pos = max(current_pos, start_char + 1)
            
            chunks.append(TextChunk(
                content=content,
                chunk_index=idx,
                start_char=start_char,
                end_char=end_char,
            ))
        
        return chunks

def create_chunks(text: str, chunk_size: int = None, chunk_overlap: int = None) -> List[TextChunk]:
    """
    Convenience function to chunk text.
    
    Args:
        text: Text to chunk
        chunk_size: Size of each chunk
        chunk_overlap: Overlap between chunks
        
    Returns:
        List of TextChunk objects
    """
    chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return chunker.chunk_text(text)
