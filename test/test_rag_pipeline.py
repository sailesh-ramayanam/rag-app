"""
Automated RAG pipeline tests using JSONL test data files.

Test data format (JSONL):
- Line 1: {"file_name": "document.pdf"}
- Lines 2+: {"question_id": "Q1", "question": "...", "expected_answer": "...", "type": "extractive|abstractive|unanswerable"}

Usage:
    # Run all tests (from test directory)
    pytest test_rag_pipeline.py -v

    # Run specific test file
    pytest test_rag_pipeline.py -v -k "biography"

    # Run with detailed output
    pytest test_rag_pipeline.py -v --tb=short
    
    # Skip slow tests
    pytest test_rag_pipeline.py -v -m "not slow"
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pytest
import pytest_asyncio

from evaluator import get_evaluator, EvaluationResult


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class TestQuestion:
    """A single test question from JSONL file."""
    question_id: str
    question: str
    expected_answer: str
    question_type: str  # extractive, abstractive, unanswerable


@dataclass
class TestCase:
    """A complete test case from a JSONL file."""
    jsonl_path: Path
    document_path: Path
    document_name: str
    questions: List[TestQuestion]
    
    @property
    def test_name(self) -> str:
        """Generate a test name from the JSONL filename."""
        return self.jsonl_path.stem


# ============================================================
# TEST DATA DISCOVERY
# ============================================================

def discover_test_cases(test_data_dir: Path) -> List[TestCase]:
    """
    Discover all JSONL test files and parse them into TestCase objects.
    
    Args:
        test_data_dir: Path to test-data directory
        
    Returns:
        List of TestCase objects
    """
    test_cases = []
    
    for jsonl_file in sorted(test_data_dir.glob("*.jsonl")):
        test_case = parse_jsonl_file(jsonl_file, test_data_dir)
        if test_case:
            test_cases.append(test_case)
    
    return test_cases


def parse_jsonl_file(jsonl_path: Path, test_data_dir: Path) -> Optional[TestCase]:
    """
    Parse a JSONL test file.
    
    Format:
    - Line 1: {"file_name": "document.pdf"}
    - Lines 2+: {"question_id": "...", "question": "...", "expected_answer": "...", "type": "..."}
    
    Args:
        jsonl_path: Path to the JSONL file
        test_data_dir: Base directory for test data
        
    Returns:
        TestCase object or None if invalid
    """
    questions = []
    document_name = None
    
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"Warning: Invalid JSON at {jsonl_path}:{line_num}: {e}")
                continue
            
            # First line should have file_name
            if line_num == 1:
                if "file_name" in data:
                    document_name = data["file_name"]
                else:
                    print(f"Warning: First line of {jsonl_path} should have 'file_name'")
                    return None
            else:
                # Parse question
                if all(k in data for k in ["question_id", "question", "expected_answer"]):
                    questions.append(TestQuestion(
                        question_id=data["question_id"],
                        question=data["question"],
                        expected_answer=data["expected_answer"],
                        question_type=data.get("type", "extractive")
                    ))
    
    if not document_name:
        print(f"Warning: No document name found in {jsonl_path}")
        return None
    
    document_path = test_data_dir / document_name
    if not document_path.exists():
        print(f"Warning: Document not found: {document_path}")
        return None
    
    if not questions:
        print(f"Warning: No questions found in {jsonl_path}")
        return None
    
    return TestCase(
        jsonl_path=jsonl_path,
        document_path=document_path,
        document_name=document_name,
        questions=questions
    )


# ============================================================
# TEST FIXTURES
# ============================================================

# Discover test cases at module load time
TEST_DATA_DIR = Path(__file__).parent / "test-data"
TEST_CASES = discover_test_cases(TEST_DATA_DIR)


def get_test_ids():
    """Generate test IDs for parametrization."""
    return [tc.test_name for tc in TEST_CASES]


@pytest.fixture(scope="module")
def evaluator():
    """Get the answer evaluator."""
    return get_evaluator()


# ============================================================
# MAIN TEST
# ============================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("test_case", TEST_CASES, ids=get_test_ids())
async def test_rag_document(test_case: TestCase, api_client, evaluator):
    """
    Test RAG pipeline with a document and its questions.
    
    Steps:
    1. Upload the document
    2. Wait for processing
    3. Create a chat session
    4. Ask each question and evaluate the answer
    """
    print(f"\n{'='*60}")
    print(f"TEST: {test_case.test_name}")
    print(f"Document: {test_case.document_name}")
    print(f"Questions: {len(test_case.questions)}")
    print(f"{'='*60}")
    
    # Step 1: Upload document
    print(f"\n📤 Uploading {test_case.document_name}...")
    doc_id = await api_client.upload_document(test_case.document_path)
    print(f"   Document ID: {doc_id}")
    
    # Step 2: Wait for processing
    print("⏳ Waiting for document processing...")
    await api_client.wait_for_processing(doc_id)
    print("   ✅ Processing complete!")
    
    # Step 3: Create chat
    print("💬 Creating chat session...")
    chat_id = await api_client.create_chat(
        [doc_id], 
        title=f"Test: {test_case.test_name}"
    )
    print(f"   Chat ID: {chat_id}")
    
    # Step 4: Ask questions and evaluate
    print(f"\n🧪 Running {len(test_case.questions)} questions...\n")
    
    results: List[EvaluationResult] = []
    
    for i, question in enumerate(test_case.questions, 1):
        print(f"Q{i} [{question.question_id}] ({question.question_type}):")
        print(f"   {question.question[:80]}{'...' if len(question.question) > 80 else ''}")
        
        # Ask the question
        response = await api_client.ask_question(chat_id, question.question)
        actual_answer = response["answer"]
        
        # Evaluate
        result = evaluator.evaluate(
            question_id=question.question_id,
            question=question.question,
            actual_answer=actual_answer,
            expected_answer=question.expected_answer,
            question_type=question.question_type
        )
        results.append(result)
        
        # Print result
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"   {status} | Semantic: {result.semantic_similarity:.2f} | LLM: {result.llm_judge_score:.2f}")
        
        if not result.passed:
            print(f"   Expected: {question.expected_answer[:100]}...")
            print(f"   Got: {actual_answer}...")
            for reason in result.failure_reasons:
                print(f"   ⚠️  {reason}")
        
        print()
    
    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    pass_rate = passed / total * 100 if total > 0 else 0
    
    print(f"{'='*60}")
    print(f"SUMMARY: {passed}/{total} questions passed ({pass_rate:.0f}%)")
    print(f"{'='*60}")
    
    # Generate detailed report
    report = {
        "test_name": test_case.test_name,
        "document": test_case.document_name,
        "total_questions": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": f"{pass_rate:.1f}%",
        "results": [r.to_dict() for r in results]
    }
    
    # Save report to file
    report_path = TEST_DATA_DIR / f"{test_case.test_name}_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n📊 Report saved to: {report_path}")
    
    # Assert all tests pass
    failed_questions = [r for r in results if not r.passed]
    assert len(failed_questions) == 0, (
        f"Failed {len(failed_questions)} questions: "
        f"{[r.question_id for r in failed_questions]}"
    )


# ============================================================
# INDIVIDUAL QUESTION TESTS (for debugging)
# ============================================================

@pytest.mark.asyncio
async def test_single_question(api_client, evaluator, test_data_dir):
    """
    Test a single question for debugging purposes.
    
    Modify the question details below to test specific cases.
    """
    pytest.skip("Enable this test manually for debugging")
    
    # Configure the test
    document_path = test_data_dir / "biography.pdf"
    question = "When did Maya Rao lead the FalconDB project?"
    expected_answer = "From 2015 to 2019."
    question_type = "extractive"
    
    # Upload and process
    doc_id = await api_client.upload_document(document_path)
    await api_client.wait_for_processing(doc_id)
    
    # Create chat and ask
    chat_id = await api_client.create_chat([doc_id])
    response = await api_client.ask_question(chat_id, question)
    
    # Evaluate
    result = evaluator.evaluate(
        question_id="debug_test",
        question=question,
        actual_answer=response["answer"],
        expected_answer=expected_answer,
        question_type=question_type
    )
    
    print(f"\nActual answer: {response['answer']}")
    print(f"Semantic similarity: {result.semantic_similarity:.3f}")
    print(f"LLM judge score: {result.llm_judge_score:.2f}")
    print(f"LLM reasoning: {result.llm_judge_reasoning}")
    print(f"Passed: {result.passed}")
    
    assert result.passed


# ============================================================
# STANDALONE RUNNER
# ============================================================

async def run_all_tests():
    """
    Run all tests standalone (without pytest).
    
    Useful for quick testing or integration with CI/CD.
    """
    import httpx
    from conftest import BASE_URL, MAX_PROCESSING_WAIT, POLLING_INTERVAL
    import asyncio
    import time
    
    print("🚀 RAG Pipeline Test Runner")
    print(f"API: {BASE_URL}")
    print(f"Test data: {TEST_DATA_DIR}")
    print()
    
    if not TEST_CASES:
        print("❌ No test cases found! Add JSONL files to test-data/")
        return
    
    print(f"Found {len(TEST_CASES)} test case(s):")
    for tc in TEST_CASES:
        print(f"  - {tc.test_name}: {len(tc.questions)} questions")
    print()
    
    evaluator = get_evaluator()
    all_results = []
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        for test_case in TEST_CASES:
            print(f"\n{'='*60}")
            print(f"Running: {test_case.test_name}")
            print(f"{'='*60}")
            
            try:
                # Upload
                print(f"📤 Uploading {test_case.document_name}...")
                with open(test_case.document_path, "rb") as f:
                    files = {"file": (test_case.document_name, f)}
                    resp = await client.post(f"{BASE_URL}/documents/upload", files=files)
                resp.raise_for_status()
                doc_id = resp.json()["id"]
                print(f"   Document ID: {doc_id}")
                
                # Wait for processing
                print("⏳ Processing...")
                start = time.time()
                while time.time() - start < MAX_PROCESSING_WAIT:
                    resp = await client.get(f"{BASE_URL}/documents/{doc_id}")
                    status = resp.json()["status"]
                    if status == "completed":
                        break
                    elif status == "failed":
                        raise Exception("Processing failed")
                    await asyncio.sleep(POLLING_INTERVAL)
                print("   ✅ Done!")
                
                # Create chat
                resp = await client.post(
                    f"{BASE_URL}/chats/",
                    json={"document_ids": [doc_id], "title": test_case.test_name}
                )
                chat_id = resp.json()["id"]
                
                # Run questions
                case_results = []
                for q in test_case.questions:
                    resp = await client.post(
                        f"{BASE_URL}/chats/{chat_id}/messages",
                        json={"question": q.question}
                    )
                    answer = resp.json()["answer"]
                    
                    result = evaluator.evaluate(
                        question_id=q.question_id,
                        question=q.question,
                        actual_answer=answer,
                        expected_answer=q.expected_answer,
                        question_type=q.question_type
                    )
                    case_results.append(result)
                    
                    status = "✅" if result.passed else "❌"
                    print(f"   {status} {q.question_id}: {result.semantic_similarity:.2f} / {result.llm_judge_score:.2f}")
                
                all_results.extend(case_results)
                
                # Cleanup
                await client.delete(f"{BASE_URL}/chats/{chat_id}")
                await client.delete(f"{BASE_URL}/documents/{doc_id}")
                
            except Exception as e:
                print(f"❌ Error: {e}")
    
    # Final summary
    if all_results:
        passed = sum(1 for r in all_results if r.passed)
        total = len(all_results)
        print(f"\n{'='*60}")
        print(f"FINAL RESULTS: {passed}/{total} ({passed/total*100:.0f}%)")
        print(f"{'='*60}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_all_tests())

