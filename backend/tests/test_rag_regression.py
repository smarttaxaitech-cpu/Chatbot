import json
from pathlib import Path
from typing import Any, Dict, List

from app.rag.answer import generate_answer

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "rag_questions.json"


def load_cases() -> List[Dict[str, Any]]:
    with FIXTURE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def text_contains_all(text: str, phrases: List[str]) -> bool:
    t = (text or "").lower()
    return all(p.lower() in t for p in phrases)


def cites_contain_sources(citations: List[dict], must_contain: List[str]) -> bool:
    joined = " ".join(
        (c.get("source", "") + " " + c.get("section", "")) for c in citations
    ).lower()
    return all(x.lower() in joined for x in must_contain)


def test_rag_regression_cases():
    cases = load_cases()

    for case in cases:
        out = generate_answer(case["question"], top_k=6)

        # block expectations
        if case.get("must_block"):
            assert out.get("confidence_score", 0) == 0.0, case["id"]
            assert "cannot confirm" in (out.get("answer_text", "").lower()), case["id"]
            assert len(out.get("citations", [])) == 0, case["id"]
            continue

        # must include phrases
        must_include = case.get("must_include", [])
        assert text_contains_all(out.get("answer_text", ""), must_include), case["id"]

        # must cite sources
        must_cite = case.get("must_cite_source_contains", [])
        assert cites_contain_sources(out.get("citations", []), must_cite), case["id"]

        # always: citations should exist for non-block answers
        assert len(out.get("citations", [])) >= 1, case["id"]
