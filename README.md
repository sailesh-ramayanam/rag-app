# AI-Powered Vault Document System

An intelligent document management system where users can upload documents, get AI-powered insights, and chat with their documents using natural language.

## Features

- **Document Upload & Processing**: Support for PDF, DOCX, and TXT files
- **Automatic Text Extraction**: Intelligent parsing using pdfplumber and python-docx
- **Smart Chunking**: LlamaIndex sentence splitter with configurable chunk sizes
- **Local Vector Embeddings**: sentence-transformers (no API key required for ingestion!)
- **Document Chat**: RAG-based Q&A with conversation history
- **Multi-document Chat**: Ask questions across multiple documents at once
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
| POST | `/api/v1/chats/{id}/messages` | Ask a question |
| DELETE | `/api/v1/chats/{id}` | Delete a chat |

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

# Response: { "answer": "...", "sources": [...] }
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

### Chat Pipeline

1. **Create Chat**: Select documents to chat with
2. **Ask Question**: Question embedded using same model
3. **Retrieve**: Top-k similar chunks found via pgvector cosine similarity
4. **Generate**: OpenAI GPT generates answer with context
5. **Cite**: Response includes source citations with page numbers

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
- [ ] AI-generated document summaries
- [ ] Follow-up question suggestions
- [ ] Document categorization
- [ ] Cost tracking for API usage

## License

MIT
