"""Main FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import async_engine, Base
from app.api.documents import router as documents_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - runs on startup and shutdown."""
    # Startup
    logger.info("Starting up Vault Document System...")
    
    # Create database tables
    async with async_engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database tables created successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Vault Document System...")
    await async_engine.dispose()


# Create FastAPI app
app = FastAPI(
    title="AI-Powered Vault Document System",
    description="""
    An intelligent document management system with AI-powered insights.
    
    ## Features
    
    - **Document Upload**: Upload PDF, DOCX, and TXT files
    - **Automatic Processing**: Text extraction, chunking, and embedding generation
    - **Async Processing**: Background processing with Celery
    - **Vector Search Ready**: Embeddings stored in pgvector for semantic search
    
    ## Coming Soon
    
    - Document Chat (RAG-based Q&A)
    - AI-generated summaries
    - Multi-document search
    """,
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(documents_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": "AI-Powered Vault Document System",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

