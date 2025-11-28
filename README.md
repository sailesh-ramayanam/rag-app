# AI-Powered Vault Document System

An intelligent document management system where users can upload documents, get AI-powered insights, and chat with their documents using natural language.

## Features

- **Document Upload & Processing**: Support for PDF, DOCX, and TXT files
- **Automatic Text Extraction**: Intelligent parsing using pdfplumber and python-docx
- **Smart Chunking**: LlamaIndex sentence splitter with configurable chunk sizes
- **Local Vector Embeddings**: sentence-transformers (no API key required!)
- **Async Processing**: Background processing with Celery and Redis
- **RESTful API**: Clean FastAPI endpoints with automatic documentation

## Tech Stack

- **Backend**: FastAPI (Python 3.11)
- **Database**: PostgreSQL with pgvector extension
- **Task Queue**: Celery with Redis
- **RAG Framework**: LlamaIndex
- **Embeddings**: sentence-transformers (all-MiniLM-L6-v2)
- **Containerization**: Docker & Docker Compose

## Quick Start

### Prerequisites

- Docker and Docker Compose

### Setup

1. **Clone and navigate to the project:**
   ```bash
   cd rag-app
   ```

2. **Start the services:**
   ```bash
   docker-compose up --build
   ```

   > Note: First run will download the embedding model (~90MB). This is cached for subsequent runs.

3. **Access the API:**
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

### Example: Upload a Document

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your-document.pdf"
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
                                       ┌─────────────┐
                                       │  Sentence   │
                                       │ Transformers│
                                       └─────────────┘
```

### Processing Pipeline

1. **Upload**: Document uploaded via API, saved to storage
2. **Queue**: Processing task queued in Redis
3. **Extract**: Celery worker extracts text from document
4. **Chunk**: LlamaIndex splits text into overlapping chunks (~1000 chars)
5. **Embed**: sentence-transformers generates 384-dim vectors locally
6. **Store**: Chunks and embeddings saved to PostgreSQL with pgvector

## Configuration

Environment variables (optional, defaults are set in Docker):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Async PostgreSQL URL | Auto-configured |
| `REDIS_URL` | Redis connection URL | Auto-configured |
| `STORAGE_PATH` | Document storage path | `/app/storage` |
| `EMBEDDING_MODEL` | sentence-transformers model | `all-MiniLM-L6-v2` |
| `CHUNK_SIZE` | Characters per chunk | `1000` |
| `CHUNK_OVERLAP` | Overlap between chunks | `200` |

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
│   ├── api/           # API routes
│   ├── core/          # Config, database
│   ├── models/        # SQLAlchemy models
│   ├── services/      # Business logic
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

# Run FastAPI
uvicorn app.main:app --reload

# Run Celery worker (separate terminal)
celery -A app.tasks.celery_app worker --loglevel=info
```

## Coming Soon

- [ ] Document Chat API (RAG-based Q&A)
- [ ] AI-generated summaries  
- [ ] Multi-document semantic search
- [ ] Chat history and sessions
- [ ] Document categorization

## License

MIT
