"""Embedding generation service using sentence-transformers (local)."""

from typing import List
import logging

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Global model instance (loaded once)
_model = None


def _get_model() -> SentenceTransformer:
    """Get or initialize the embedding model (singleton)."""
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        _model = SentenceTransformer(settings.embedding_model)
        logger.info("Embedding model loaded successfully")
    return _model


class EmbeddingService:
    """Handles generating embeddings using sentence-transformers (local)."""
    
    def __init__(self):
        self.model = _get_model()
        self.dimensions = settings.embedding_dimensions
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        # Clean text
        text = text.replace("\n", " ").strip()
        
        if not text:
            return [0.0] * self.dimensions
        
        # Use convert_to_tensor=False to get numpy array directly
        embedding = self.model.encode(
            text, 
            convert_to_tensor=False,
            normalize_embeddings=True
        )
        return embedding.tolist()
    
    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 32
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per batch
            
        Returns:
            List of embedding vectors
        """
        # Clean texts
        cleaned_texts = [t.replace("\n", " ").strip() for t in texts]
        
        # Handle empty texts
        non_empty_indices = [i for i, t in enumerate(cleaned_texts) if t]
        non_empty_texts = [cleaned_texts[i] for i in non_empty_indices]
        
        if not non_empty_texts:
            return [[0.0] * self.dimensions] * len(texts)
        
        # Generate embeddings for non-empty texts
        logger.info(f"Generating embeddings for {len(non_empty_texts)} chunks...")
        
        # Use convert_to_tensor=False to avoid numpy conversion issues
        embeddings = self.model.encode(
            non_empty_texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_tensor=False,
            normalize_embeddings=True
        )
        
        # Map embeddings back to original positions
        result = [[0.0] * self.dimensions for _ in range(len(texts))]
        for idx, orig_idx in enumerate(non_empty_indices):
            result[orig_idx] = embeddings[idx].tolist()
        
        logger.info(f"Generated {len(non_empty_texts)} embeddings")
        return result


def get_embedding_service() -> EmbeddingService:
    """Factory function to get embedding service instance."""
    return EmbeddingService()
