# AI-Powered Vault Document System

An intelligent document management system where users can upload documents, get AI-powered insights, and chat with their documents using natural language.

## Features

- **Document Upload & Processing**: Support for PDF, DOCX, and TXT files
- **Automatic Text Extraction**: Intelligent parsing using pdfplumber and python-docx
- **Smart Chunking**: LlamaIndex sentence splitter with configurable chunk sizes
- **Local Vector Embeddings**: sentence-transformers (no API key required for ingestion!)
- **AI-Generated Document Summaries**: Automatic summary generation during processing
- **Document Chat**: RAG-based Q&A with conversation history
- **Multi-document Chat**: Ask questions across multiple documents at once
- **Smart Query Routing**: 3-stage pipeline that intelligently routes queries
- **Source Citations**: Get references to source documents with page numbers
- **Async Processing**: Background processing with Celery and Redis
- **RESTful API**: Clean FastAPI endpoints with automatic documentation

## Tech Stack

- **Backend**: FastAPI (Python 3.11)
- **Database**: PostgreSQL with pgvector extension
- **Task Queue**: Celery with Redis
- **RAG Framework**: LlamaIndex
- **Embeddings**: sentence-transformers (all-MiniLM-L6-v2) - local
- **LLM**: OpenAI GPT-4o-mini (configurable)
- **Containerization**: Docker & Docker Compose

## Quick Start

### Prerequisites

- Docker and Docker Compose
- OpenAI API Key (for chat feature)

### Setup

1. **Clone and navigate to the project:**
   ```bash
   cd rag-app
   ```

2. **Create environment file:**
   ```bash
   cp env.example .env
   ```

3. **Add your OpenAI API key to `.env`:**
   ```
   OPENAI_API_KEY=sk-your-api-key-here
   ```

4. **Start the services:**
   ```bash
   docker-compose up --build
   ```

   > Note: First run will download the embedding model (~90MB). This is cached for subsequent runs.

5. **Access the API:**
   - API: http://localhost:8000
   - Swagger Docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## API Endpoints

### Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/documents/upload` | Upload a document for processing |
| GET | `/api/v1/documents/` | List all documents (paginated) |
| GET | `/api/v1/documents/{id}` | Get document details |
| GET | `/api/v1/documents/{id}/chunks` | Get document chunks |
| DELETE | `/api/v1/documents/{id}` | Delete a document |
| GET | `/api/v1/documents/stats/overview` | Get processing statistics |

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/chats/` | Create a new chat with document IDs |
| GET | `/api/v1/chats/` | List all chats (paginated) |
| GET | `/api/v1/chats/{id}` | Get chat with message history |
| POST | `/api/v1/chats/{id}/messages` | Ask a question (with smart routing) |
| DELETE | `/api/v1/chats/{id}` | Delete a chat |

### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/admin/usage/summary` | Get overall usage summary |
| GET | `/api/v1/admin/usage/chats` | Get per-chat token usage |
| GET | `/api/v1/admin/documents/summaries` | Get document summary status |
| POST | `/api/v1/admin/documents/regenerate-summaries` | Regenerate document summaries |

### Example: Complete Chat Workflow

```bash
# 1. Upload a document
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your-document.pdf"

# Response: { "id": "doc-uuid-here", "status": "pending", ... }

# 2. Wait for processing (check status)
curl "http://localhost:8000/api/v1/documents/doc-uuid-here"

# 3. Create a chat with the document
curl -X POST "http://localhost:8000/api/v1/chats/" \
  -H "Content-Type: application/json" \
  -d '{"document_ids": ["doc-uuid-here"]}'

# Response: { "id": "chat-uuid-here", ... }

# 4. Ask a question
curl -X POST "http://localhost:8000/api/v1/chats/chat-uuid-here/messages" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main topic of this document?"}'

# Response: { 
#   "answer": "...", 
#   "sources": [...], 
#   "query_type": "chunk_retrieval",
#   "retrieval_strategy": "vector_search" 
# }

# 5. Ask for a summary (uses document summaries, not vector search)
curl -X POST "http://localhost:8000/api/v1/chats/chat-uuid-here/messages" \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarize this document"}'

# Response: { 
#   "answer": "...", 
#   "sources": [...], 
#   "query_type": "document_level",
#   "retrieval_strategy": "document_summaries" 
# }

# 6. Ask a follow-up (uses conversation history)
curl -X POST "http://localhost:8000/api/v1/chats/chat-uuid-here/messages" \
  -H "Content-Type: application/json" \
  -d '{"question": "Tell me more about that"}'

# Response: { 
#   "answer": "...", 
#   "sources": [...], 
#   "query_type": "follow_up",
#   "retrieval_strategy": "conversation_history" 
# }
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────>│   FastAPI   │────>│  PostgreSQL │
│             │     │    (API)    │     │  (pgvector) │
└─────────────┘     └─────────────┘     └─────────────┘
                          │
                          ▼
                   ┌─────────────┐     ┌─────────────┐
                   │    Redis    │<────│   Celery    │
                   │   (Queue)   │     │  (Worker)   │
                   └─────────────┘     └──────┬──────┘
                                              │
                                              ▼
                   ┌─────────────┐     ┌─────────────┐
                   │   OpenAI    │     │  Sentence   │
                   │  GPT-4o     │     │ Transformers│
                   └─────────────┘     └─────────────┘
```

### Processing Pipeline

1. **Upload**: Document uploaded via API, saved to storage
2. **Queue**: Processing task queued in Redis
3. **Extract**: Celery worker extracts text from document
4. **Chunk**: LlamaIndex splits text into overlapping chunks (~1000 chars)
5. **Embed**: sentence-transformers generates 384-dim vectors locally
6. **Store**: Chunks and embeddings saved to PostgreSQL with pgvector

### Enhanced 3-Stage Chat Pipeline

The chat system uses an intelligent 3-stage RAG pipeline that adapts to different query types:

#### Stage 1: Query Classification
Analyzes the user's query to determine its type:
- **DOCUMENT_LEVEL**: "Summarize this document", "What is this about?"
- **FOLLOW_UP**: "Tell me more", "Can you elaborate?"
- **CHUNK_RETRIEVAL**: "What is the pricing?", "How does feature X work?"
- **MIXED**: Queries needing both history and new search

#### Stage 2: Retrieval Routing
Routes to appropriate content based on query type:
- Document summaries for overview questions
- Conversation history for follow-up questions
- Vector search for specific topic queries
- Combined retrieval for complex queries

#### Stage 3: Context Building
Builds optimized prompts with:
- Appropriate system instructions per query type
- Relevant retrieved content
- Conversation history when needed

This approach ensures:
- "Provide a summary" → Uses pre-generated document summaries
- "Tell me more" → Uses conversation context, not vector search
- "What is X?" → Uses vector search for relevant chunks

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required for chat) | - |
| `LLM_PROVIDER` | LLM provider | `openai` |
| `LLM_MODEL` | LLM model | `gpt-5-nano` |
| `EMBEDDING_MODEL` | sentence-transformers model | `all-MiniLM-L6-v2` |
| `CHUNK_SIZE` | Characters per chunk | `1000` |
| `CHUNK_OVERLAP` | Overlap between chunks | `200` |

### Available LLM Models

| Model | Cost | Quality | Speed |
|-------|------|---------|-------|
| `gpt-4o-mini` | $ | Good | Fast |
| `gpt-4o` | $$$ | Best | Medium |
| `gpt-3.5-turbo` | $ | Decent | Fastest |

### Available Embedding Models

| Model | Dimensions | Size | Speed |
|-------|------------|------|-------|
| `all-MiniLM-L6-v2` | 384 | ~90MB | Fast |
| `all-mpnet-base-v2` | 768 | ~420MB | Better quality |

## Development

### Project Structure

```
rag-app/
├── app/
│   ├── api/           # API routes (documents, chat)
│   ├── core/          # Config, database
│   ├── models/        # SQLAlchemy models (Document, Chat, Message)
│   ├── services/      # Business logic (chat, embeddings, llm)
│   ├── tasks/         # Celery tasks
│   └── main.py        # FastAPI app
├── storage/           # Document storage
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

### Running Locally (without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL and Redis (manually or via Docker)
docker-compose up db redis -d

# Set environment variables
export OPENAI_API_KEY=sk-your-key-here

# Run FastAPI
uvicorn app.main:app --reload

# Run Celery worker (separate terminal)
celery -A app.tasks.celery_app worker --loglevel=info
```

## Coming Soon

- [ ] Streaming chat responses (SSE)
- [x] AI-generated document summaries
- [x] Smart query routing (follow-up detection)
- [ ] Follow-up question suggestions
- [ ] Document categorization
- [x] Cost tracking for API usage

## License

MIT
