"""
Answer evaluation module for RAG pipeline testing.

Provides multiple strategies for evaluating LLM-generated answers:
1. Semantic Similarity - Using sentence embeddings
2. LLM-as-Judge - Using GPT to evaluate correctness

Handles different question types:
- extractive: Direct extraction from document (stricter evaluation)
- abstractive: Summary/synthesis (more lenient)
- unanswerable: Should indicate info not available
"""

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from sentence_transformers import SentenceTransformer
from openai import OpenAI


# Thresholds for different question types
SIMILARITY_THRESHOLDS = {
    "extractive": 0.70,    # Stricter for direct extraction
    "abstractive": 0.60,   # More lenient for summaries
    "unanswerable": 0.50,  # Check if answer indicates "not found"
    "table": 0.65,         # Table extraction (numbers/facts)
    "conflict": 0.50,      # Conflicting info (should acknowledge conflict)
}

# Phrases that indicate unanswerable
UNANSWERABLE_INDICATORS = [
    "not mentioned",
    "not found",
    "not available",
    "not provided",
    "cannot be determined",
    "cannot be answered",
    "no information",
    "doesn't mention",
    "does not mention",
    "not in the document",
    "not stated",
    "unclear",
    "not specified",
    "unanswerable",
]

# Phrases that indicate conflicting information
CONFLICT_INDICATORS = [
    "conflicting",
    "contradiction",
    "contradictory",
    "inconsistent",
    "disagree",
    "both say",
    "one says",
    "on one hand",
    "on the other hand",
    "however",
    "unclear",
    "ambiguous",
    "cannot be determined",
]


@dataclass
class EvaluationResult:
    """Result of answer evaluation."""
    question_id: str
    question: str
    question_type: str
    actual_answer: str
    expected_answer: str
    
    # Evaluation scores (0.0 to 1.0)
    semantic_similarity: float
    llm_judge_score: float
    llm_judge_reasoning: str
    
    # Overall result
    passed: bool
    failure_reasons: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for reporting."""
        return {
            "question_id": self.question_id,
            "question": self.question,
            "type": self.question_type,
            "expected": self.expected_answer,
            "actual": self.actual_answer[:200] + "..." if len(self.actual_answer) > 200 else self.actual_answer,
            "semantic_similarity": round(self.semantic_similarity, 3),
            "llm_judge_score": round(self.llm_judge_score, 2),
            "llm_reasoning": self.llm_judge_reasoning,
            "passed": self.passed,
            "failure_reasons": self.failure_reasons,
        }


class AnswerEvaluator:
    """Evaluates LLM-generated answers using multiple strategies."""
    
    def __init__(self):
        # Lazy load embedding model
        self._embedding_model = None
        self._openai_client = None
    
    @property
    def embedding_model(self) -> SentenceTransformer:
        """Lazy load embedding model."""
        if self._embedding_model is None:
            print("Loading embedding model for evaluation...")
            self._embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._embedding_model
    
    @property
    def openai_client(self) -> Optional[OpenAI]:
        """Lazy load OpenAI client."""
        if self._openai_client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self._openai_client = OpenAI(api_key=api_key)
        return self._openai_client
    
    def compute_semantic_similarity(self, text1: str, text2: str) -> float:
        """
        Compute cosine similarity between two texts using embeddings.
        
        Returns:
            Float between 0 and 1, where 1 means identical meaning.
        """
        embeddings = self.embedding_model.encode([text1, text2])
        
        # Cosine similarity
        dot_product = embeddings[0] @ embeddings[1]
        norm1 = (embeddings[0] @ embeddings[0]) ** 0.5
        norm2 = (embeddings[1] @ embeddings[1]) ** 0.5
        
        similarity = dot_product / (norm1 * norm2)
        return float(max(0.0, min(1.0, similarity)))
    
    def check_unanswerable(self, answer: str) -> bool:
        """
        Check if the answer indicates the question is unanswerable.
        
        Returns:
            True if the answer suggests the info is not available.
        """
        answer_lower = answer.lower()
        
        for indicator in UNANSWERABLE_INDICATORS:
            if indicator in answer_lower:
                return True
        
        return False
    
    def check_conflict_acknowledged(self, answer: str) -> bool:
        """
        Check if the answer acknowledges conflicting information.
        
        Returns:
            True if the answer suggests there's conflicting info.
        """
        answer_lower = answer.lower()
        
        for indicator in CONFLICT_INDICATORS:
            if indicator in answer_lower:
                return True
        
        return False
    
    def llm_judge(
        self, 
        question: str, 
        actual_answer: str, 
        expected_answer: str,
        question_type: str
    ) -> Tuple[float, str]:
        """
        Use LLM as a judge to evaluate answer correctness.
        
        Returns:
            Tuple of (score 0-1, reasoning string)
        """
        if not self.openai_client:
            return 0.5, "LLM judge unavailable (no OPENAI_API_KEY)"
        
        type_guidance = {
            "extractive": "The answer should contain the specific facts from the expected answer.",
            "abstractive": "The answer should capture the key points, even if worded differently.",
            "unanswerable": "The answer should indicate that the information is not available in the document.",
            "table": "The answer should contain the exact values/numbers from the table in the expected answer.",
            "conflict": "The answer should acknowledge that there is conflicting information in the document.",
        }
        
        prompt = f"""You are evaluating a RAG (Retrieval Augmented Generation) system's answer.

QUESTION TYPE: {question_type}
EVALUATION GUIDANCE: {type_guidance.get(question_type, type_guidance["extractive"])}

QUESTION: {question}

EXPECTED ANSWER: {expected_answer}

ACTUAL ANSWER: {actual_answer}

Evaluate if the ACTUAL ANSWER correctly addresses the question based on the EXPECTED ANSWER.

For 'unanswerable' questions, the actual answer should indicate the information is not available.

Scoring:
- 1.0: Fully correct and complete
- 0.8: Mostly correct with minor omissions
- 0.6: Partially correct
- 0.4: Has some relevant info but significant issues
- 0.2: Mostly incorrect
- 0.0: Completely wrong or irrelevant

Respond in EXACTLY this format (two lines only):
SCORE: [number between 0.0 and 1.0]
REASONING: [one sentence explanation]"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse score
            score_match = re.search(r'SCORE:\s*([\d.]+)', content)
            score = float(score_match.group(1)) if score_match else 0.5
            score = max(0.0, min(1.0, score))
            
            # Parse reasoning
            reasoning_match = re.search(r'REASONING:\s*(.+)', content, re.DOTALL)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else "No reasoning provided"
            
            return score, reasoning
            
        except Exception as e:
            return 0.5, f"LLM judge error: {str(e)}"
    
    def evaluate(
        self,
        question_id: str,
        question: str,
        actual_answer: str,
        expected_answer: str,
        question_type: str = "extractive"
    ) -> EvaluationResult:
        """
        Comprehensive evaluation of an answer.
        
        Uses multiple strategies and combines them based on question type.
        
        Args:
            question_id: Unique identifier for the question
            question: The question that was asked
            actual_answer: The answer from the RAG system
            expected_answer: The expected/reference answer
            question_type: One of "extractive", "abstractive", "unanswerable"
            
        Returns:
            EvaluationResult with scores and pass/fail determination
        """
        failure_reasons = []
        threshold = SIMILARITY_THRESHOLDS.get(question_type, 0.65)
        
        # Special handling for unanswerable questions
        if question_type == "unanswerable":
            is_unanswerable_response = self.check_unanswerable(actual_answer)
            
            # Semantic similarity (should be low for "not found" vs actual content)
            semantic_sim = self.compute_semantic_similarity(actual_answer, expected_answer)
            
            # LLM judge
            llm_score, llm_reasoning = self.llm_judge(
                question, actual_answer, expected_answer, question_type
            )
            
            # For unanswerable, pass if answer indicates "not found" OR LLM says it's good
            passed = is_unanswerable_response or llm_score >= 0.6
            
            if not passed:
                failure_reasons.append(
                    "Answer should indicate information is not available in document"
                )
            
            return EvaluationResult(
                question_id=question_id,
                question=question,
                question_type=question_type,
                actual_answer=actual_answer,
                expected_answer=expected_answer,
                semantic_similarity=semantic_sim,
                llm_judge_score=llm_score,
                llm_judge_reasoning=llm_reasoning,
                passed=passed,
                failure_reasons=failure_reasons
            )
        
        # Special handling for conflict questions
        if question_type == "conflict":
            acknowledges_conflict = self.check_conflict_acknowledged(actual_answer)
            
            semantic_sim = self.compute_semantic_similarity(actual_answer, expected_answer)
            
            llm_score, llm_reasoning = self.llm_judge(
                question, actual_answer, expected_answer, question_type
            )
            
            # For conflict, pass if answer acknowledges conflict OR LLM says it's good
            passed = acknowledges_conflict or llm_score >= 0.6
            
            if not passed:
                failure_reasons.append(
                    "Answer should acknowledge conflicting information in the document"
                )
            
            return EvaluationResult(
                question_id=question_id,
                question=question,
                question_type=question_type,
                actual_answer=actual_answer,
                expected_answer=expected_answer,
                semantic_similarity=semantic_sim,
                llm_judge_score=llm_score,
                llm_judge_reasoning=llm_reasoning,
                passed=passed,
                failure_reasons=failure_reasons
            )
        
        # Standard evaluation for extractive/abstractive
        
        # 1. Semantic similarity
        semantic_sim = self.compute_semantic_similarity(actual_answer, expected_answer)
        if semantic_sim < threshold:
            failure_reasons.append(
                f"Semantic similarity {semantic_sim:.2f} below threshold {threshold}"
            )
        
        # 2. LLM-as-judge
        llm_score, llm_reasoning = self.llm_judge(
            question, actual_answer, expected_answer, question_type
        )
        if llm_score < 0.5:
            failure_reasons.append(f"LLM judge score {llm_score:.2f} below 0.5")
        
        # Overall pass: need at least one strong signal
        # - High semantic similarity OR
        # - Good LLM judge score
        passed = (semantic_sim >= threshold) or (llm_score >= 0.6)
        
        # Clear failure reasons if passed
        if passed:
            failure_reasons = []
        
        return EvaluationResult(
            question_id=question_id,
            question=question,
            question_type=question_type,
            actual_answer=actual_answer,
            expected_answer=expected_answer,
            semantic_similarity=semantic_sim,
            llm_judge_score=llm_score,
            llm_judge_reasoning=llm_reasoning,
            passed=passed,
            failure_reasons=failure_reasons
        )


# Singleton instance
_evaluator_instance = None


def get_evaluator() -> AnswerEvaluator:
    """Get singleton evaluator instance."""
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = AnswerEvaluator()
    return _evaluator_instance

