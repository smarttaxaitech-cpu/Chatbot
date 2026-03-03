from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
import re

Chunk = Dict[str, Any]  # expected keys: text, source, section, page_start, page_end, similarity


def retrieve_chunks(question: str, k: int = 5) -> List[Chunk]:
    """
    TODO: Replace with real pgvector query.
    For now, return empty to force refusal (proves gating works).
    """
    return []


def rag_quality_gate(question: str, chunks: List[Chunk]) -> Tuple[bool, str]:
    if not chunks:
        return False, "no_chunks"
    top_sim = float(chunks[0].get("similarity", 0.0))
    if top_sim < 0.55:
        return False, "low_similarity"
    return True, "ok"


def format_chunks_for_prompt(chunks: List[Chunk]) -> str:
    out = []
    for i, c in enumerate(chunks, start=1):
        source = c.get("source", "Unknown Source")
        section = c.get("section") or ""
        p1 = c.get("page_start")
        p2 = c.get("page_end")
        pages = f"p.{p1}" if p1 is not None else ""
        if p2 is not None and p2 != p1:
            pages = f"p.{p1}-{p2}"
        header = f"[{i}] {source} {section} {pages}".strip()
        text = (c.get("text") or "").strip()
        out.append(f"{header}\n{text}")
    return "\n\n".join(out)


def build_citations(chunks: List[Chunk]) -> List[Dict[str, Any]]:
    cites = []
    for c in chunks[:5]:
        cites.append(
            {
                "source": c.get("source", "Unknown Source"),
                "section": c.get("section"),
                "page_start": c.get("page_start"),
                "page_end": c.get("page_end"),
                "snippet": (c.get("text") or "")[:300].strip(),
            }
        )
    return cites


def hallucination_detected(answer_text: str) -> bool:
    t = (answer_text or "").lower()
    bad = [
        "it depends",
        "might be",
        "may be",
        "possibly",
        "consult a cpa",
        "i recommend speaking",
        "not sure",
        "cannot guarantee",
    ]
    return any(b in t for b in bad)