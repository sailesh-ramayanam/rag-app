# AI-Powered Vault Document System

An intelligent document management system where users can upload documents, get AI-powered insights, and chat with their documents using natural language.

## Table of Contents

- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Run App](#run-app)
  - [Run Tests](#run-tests)
- [Architecture](#architecture)
  - [Processing Pipeline](#processing-pipeline)
  - [Enhanced 3-Stage Chat Pipeline](#enhanced-3-stage-chat-pipeline)
  - [Testing Strategy](#testing-strategy)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [API Endpoints](#api-endpoints)
  - [Documents](#documents)
  - [Chat](#chat)
  - [Admin](#admin)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [To Dos](#to-dos)
  - [Investigate Tests](#investigate-tests)
  - [Review](#review)
    - [Functional](#functional)
    - [System Design](#system-design)
    - [Tests](#tests)
    - [Dev](#dev)
- [Enhancements](#enhancements)
  - [Instrumentation](#instrumentation)
  - [Functionality](#functionality)
  - [UI](#ui)

## Quick Start

### Prerequisites

- Docker and Docker Compose
- OpenAI API Key

### Run App

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

5. **Access the application:**
   - UI: http://localhost:3000
   - API: http://localhost:8000
   - Swagger Docs: http://localhost:8000/docs

### Run Tests

The test suite runs RAG pipeline evaluation tests against the running backend services.

**Prerequisites:** Backend services must be running (`docker-compose up -d`)

**Linux/macOS (Bash):**
```bash
# Run all tests
./run_tests.sh

# Run specific test (e.g., biography)
./run_tests.sh biography

# Rebuild test container and run
./run_tests.sh --build
```

**Windows (PowerShell): Not tested**
```powershell
# Run all tests
.\run_tests.ps1

# Run specific test (e.g., biography)
.\run_tests.ps1 biography

# Rebuild test container and run
.\run_tests.ps1 -Build
```

The tests use `docker-compose.test.yml` to run pytest in a container that connects to the backend services.

## Architecture

```
                    ┌─────────────┐
                    │   OpenAI    │
                    │  gpt-5-nano │
                    └─────────────┘
                          ▲
                          │
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
                                      │   Sentence  │
                                      │Transformers │
                                      └─────────────┘
```

### Processing Pipeline

1. **Upload**: Document uploaded via API, saved to storage
2. **Queue**: Processing task queued in Redis
3. **Extract**: Celery worker extracts text from document and generates a summary
4. **Chunk**: LlamaIndex splits text into overlapping chunks (~1000 chars)
5. **Embed**: sentence-transformers generates 384-dim vectors locally
6. **Store**: Summary, chunks and embeddings saved to PostgreSQL with pgvector

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

### Testing Strategy

The test suite validates the RAG pipeline using a combination of **LLM-as-Judge** and **Semantic similarity** scores. A test case is marked as passed if it crosses threshold in at least one of the two (**LLM-as-Judge** and **Semantic similarity**) scores.

#### Test Data Format (JSONL)
Each test case is a JSONL file containing:
```jsonl
{"file_name": "document.pdf"}
{"question_id": "Q1", "question": "...", "expected_answer": "...", "type": "extractive"}
{"question_id": "Q2", "question": "...", "expected_answer": "...", "type": "abstractive"}
```

#### Question Types
| Type | Description | Evaluation |
|------|-------------|------------|
| `extractive` | Direct facts from document | Strict matching (threshold: 0.70) |
| `abstractive` | Summary/synthesis questions | Lenient matching (threshold: 0.60) |
| `unanswerable` | Info not in document | Should indicate "not found" |
| `table` | Table/numerical extraction | Fact checking (threshold: 0.65) |
| `conflict` | Contradictory information | Should acknowledge conflict |

#### Evaluation Pipeline
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Test Data   │────>│  RAG System  │────>│   Evaluator  │
│   (JSONL)    │     │  (Chat API)  │     │              │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                 │
                     ┌───────────────────────────|
                     │                           │                           │
                     ▼                           ▼                           ▼
              ┌─────────────┐            ┌─────────────┐
              │  Semantic   │            │ LLM-as-Judge│
              │ Similarity  │            │   (GPT-4)   │
              └─────────────┘            └─────────────┘
```

1. **Upload & Process**: Test PDF uploaded via API
2. **Create Chat**: Chat session created with document
3. **Ask Questions**: Each question from JSONL sent to chat API
4. **Evaluate Answers**: Multi-strategy evaluation:
   - **Semantic Similarity**: sentence-transformers compares embeddings
   - **LLM-as-Judge**: GPT-4 evaluates correctness and reasoning

## Features

- **Document Upload & Processing**: Support for PDF
- **Automatic Text Extraction**: Intelligent parsing using pdfplumber
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
- **LLM**: OpenAI gpt-5-nano (configurable)
- **Containerization**: Docker & Docker Compose

## API Endpoints

### Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/documents/upload` | Upload a document for processing |
| GET | `/api/v1/documents/` | List all documents (paginated) |
| GET | `/api/v1/documents/{id}` | Get document details |
| GET | `/api/v1/documents/{id}/chunks` | Get document chunks |
| DELETE | `/api/v1/documents/{id}` | Delete a document |
| GET | `/api/v1/documents/stats/overview` | Not tested |

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
| GET | `/api/v1/admin/documents/summaries` | Not tested |
| POST | `/api/v1/admin/documents/regenerate-summaries` | Not tested |

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required for chat) | - |
| `LLM_PROVIDER` | LLM provider | `openai` |
| `LLM_MODEL` | LLM model | `gpt-5-nano` |
| `EMBEDDING_MODEL` | sentence-transformers model | `all-MiniLM-L6-v2` |


## Project Structure

```
rag-app/
├── app/
│   ├── api/              # API routes (documents, chat, admin)
│   ├── core/             # Config, database
│   ├── models/           # SQLAlchemy models (Document, Chat, Message, LLMUsage)
│   ├── services/         # Business logic (chat, embeddings, llm, query routing)
│   ├── tasks/            # Celery tasks
│   └── main.py           # FastAPI app
├── frontend/
│   ├── src/
│   │   ├── api/          # API client
│   │   ├── components/   # React components
│   │   ├── pages/        # Page components
│   │   └── types/        # TypeScript types
│   └── ...
├── test/
│   ├── test-data/        # Test PDFs and expected Q&A (JSONL)
│   ├── evaluator.py      # LLM-based answer evaluation
│   ├── test_rag_pipeline.py  # Main test suite
│   └── conftest.py       # Pytest fixtures
├── storage/              # Uploaded document storage
├── docker-compose.yml    # Main services
├── docker-compose.test.yml  # Test container config
├── Dockerfile
├── Dockerfile.test
├── requirements.txt
├── requirements-test.txt
├── run_tests.sh          # Test runner (Linux/macOS)
├── run_tests.ps1         # Test runner (Windows)
└── README.md
```

## To Dos
### Investigate Tests
Investigate the failing tests
```
test_rag_pipeline.py::test_rag_document[biography] PASSED                [ 14%]
test_rag_pipeline.py::test_rag_document[conflicting-statements] FAILED   [ 28%]
test_rag_pipeline.py::test_rag_document[leave-policy] PASSED             [ 42%]
test_rag_pipeline.py::test_rag_document[news-article] FAILED             [ 57%]
test_rag_pipeline.py::test_rag_document[research] PASSED                 [ 71%]
test_rag_pipeline.py::test_rag_document[table] FAILED                    [ 85%]
test_rag_pipeline.py::test_single_question SKIPPED (Enable this test...) [100%]

.....
.....

=========================== short test summary info ============================
FAILED test_rag_pipeline.py::test_rag_document[conflicting-statements] - Runt...
FAILED test_rag_pipeline.py::test_rag_document[news-article] - RuntimeError: ...
FAILED test_rag_pipeline.py::test_rag_document[table] - RuntimeError: Event l...
======== 3 failed, 3 passed, 1 skipped, 2 warnings in 289.97s (0:04:49) ========
```

### Review
Almost all of the code is LLM generated. Following are a few aspects I noticed while skimming through the code (but not an exhaustive list of issues)
#### Functional
- Is error handling present at all steps?
    - When document summary generation failed, the doc processing was marked complete with summary containing the error
    - There is truncation of text in some places 
- Reuse agenerate instead of chat.completions.create (document_tasks.py)
- LLM usage for query classification is not logged - logging should happen at the LLM call. This way the caller need not log the LLM usage 
- Test for DOCX, and TXT files
- Parameterize chunk size and chunk overlap

#### System Design
- Integrity checks
    - deleting chat-id is deleting the messages and nullifies the chat-id in llm_usage, but the message-id remains non-null
    - should we use soft delete?

#### Tests
- evaluator.py is using gpt-4o-mini. Parameterize it.
- Cleanup in the tests is unguarded. There can be leakage in case of exceptions.

#### Dev
- Clean up requirements.txt - e.g. python-docx is not used

## Enhancements
### Instrumentation
- Logs for all the requests
  - There is some logging. It needs to be reviewed.
  - Use a system like Splunk
- Only LLM token usage is logged. We can have other performance metrics like response time (p99, p95), failures etc.

### Functionality
- File size limits
- Option to use Open AI for embeddings
- Reduce token usage by sending a summary of the history instead of the raw history
- Handling multi-modal documents
- Pagination for documents API (and other relevant APIs)

### UI
- Provide a name to a document
- Rename a document
- Currently doc search is just a filter of fetched documents, not a search on server
- User login
- Chunk references in the frontend are not shown well
