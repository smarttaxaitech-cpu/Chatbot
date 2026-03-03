from __future__ import annotations
from typing import List, Dict, Any, Tuple
import os

RAG_MIN_CHUNKS = int(os.getenv("RAG_MIN_CHUNKS", "2"))
RAG_MIN_TOP_SIM = float(os.getenv("RAG_MIN_TOP_SIM", "0.55"))

# simple keyword check to catch obviously personal questions
PERSONAL_KEYWORDS = [
    "wedding", "girlfriend", "boyfriend", "personal", "groceries", "netflix",
    "vacation only", "birthday", "rent for my parents"
]


def should_block_question(question: str) -> bool:
    q = (question or "").lower()
    return any(k in q for k in PERSONAL_KEYWORDS)


def rag_quality_gate(question: str, chunks: List[Dict[str, Any]]) -> Tuple[bool, str]:
    return True, "disabled_for_mvp"
