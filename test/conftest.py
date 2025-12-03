"""
Pytest configuration and fixtures for RAG pipeline testing.
"""

import os
import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
import httpx

# Test configuration
TEST_DATA_DIR = Path(__file__).parent / "test-data"
BASE_URL = os.getenv("TEST_API_URL", "http://localhost:8000/api/v1")
POLLING_INTERVAL = 2  # seconds
MAX_PROCESSING_WAIT = 180  # seconds (3 minutes for large documents)


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )


@pytest.fixture(scope="session")
def event_loop_policy():
    """Return the event loop policy."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Return path to test data directory."""
    return TEST_DATA_DIR


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Return API base URL."""
    return BASE_URL


@pytest_asyncio.fixture(scope="session")
async def http_client():
    """Create async HTTP client for the test session."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def api_client(http_client, api_base_url):
    """
    API client wrapper with helper methods.
    """
    class APIClient:
        def __init__(self, client: httpx.AsyncClient, base_url: str):
            self.client = client
            self.base_url = base_url
            self._uploaded_docs = []
            self._created_chats = []
        
        async def upload_document(self, file_path: Path) -> str:
            """Upload a document and return its ID."""
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f)}
                response = await self.client.post(
                    f"{self.base_url}/documents/upload",
                    files=files
                )
            
            response.raise_for_status()
            doc_id = response.json()["id"]
            self._uploaded_docs.append(doc_id)
            return doc_id
        
        async def get_document_status(self, document_id: str) -> str:
            """Get document processing status."""
            response = await self.client.get(
                f"{self.base_url}/documents/{document_id}"
            )
            response.raise_for_status()
            return response.json()["status"]
        
        async def wait_for_processing(self, document_id: str) -> bool:
            """Wait for document processing to complete."""
            import time
            start_time = time.time()
            
            while time.time() - start_time < MAX_PROCESSING_WAIT:
                status = await self.get_document_status(document_id)
                
                if status == "completed":
                    return True
                elif status == "failed":
                    raise Exception(f"Document {document_id} processing failed")
                
                await asyncio.sleep(POLLING_INTERVAL)
            
            raise TimeoutError(
                f"Document processing timed out after {MAX_PROCESSING_WAIT}s"
            )
        
        async def create_chat(self, document_ids: list, title: str = None) -> str:
            """Create a chat session and return its ID."""
            response = await self.client.post(
                f"{self.base_url}/chats/",
                json={"document_ids": document_ids, "title": title}
            )
            response.raise_for_status()
            chat_id = response.json()["id"]
            self._created_chats.append(chat_id)
            return chat_id
        
        async def ask_question(
            self, 
            chat_id: str, 
            question: str,
            top_k: int = 5,
            use_smart_routing: bool = True
        ) -> dict:
            """Ask a question in a chat and return the response."""
            response = await self.client.post(
                f"{self.base_url}/chats/{chat_id}/messages",
                json={
                    "question": question,
                    "top_k": top_k,
                    "use_smart_routing": use_smart_routing
                }
            )
            response.raise_for_status()
            return response.json()
        
        async def delete_chat(self, chat_id: str):
            """Delete a chat session."""
            try:
                await self.client.delete(f"{self.base_url}/chats/{chat_id}")
            except Exception:
                pass  # Ignore deletion errors
        
        async def delete_document(self, document_id: str):
            """Delete a document."""
            try:
                await self.client.delete(f"{self.base_url}/documents/{document_id}")
            except Exception:
                pass  # Ignore deletion errors
        
        async def cleanup(self):
            """Clean up all created resources."""
            for chat_id in self._created_chats:
                await self.delete_chat(chat_id)
            for doc_id in self._uploaded_docs:
                await self.delete_document(doc_id)
            self._created_chats.clear()
            self._uploaded_docs.clear()
    
    client = APIClient(http_client, api_base_url)
    yield client
    # Cleanup after all tests
    await client.cleanup()


def pytest_collection_modifyitems(config, items):
    """Add slow marker to integration tests."""
    for item in items:
        if "test_rag" in item.nodeid:
            item.add_marker(pytest.mark.slow)

