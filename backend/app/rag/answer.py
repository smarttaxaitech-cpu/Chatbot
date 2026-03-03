import os
from typing import Dict, Any, List
from openai import OpenAI
from dotenv import load_dotenv

from app.rag.retrieve import retrieve_top_chunks
from app.rag.guardrails import rag_quality_gate
from app.logging.logger import log_event

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

client = OpenAI(api_key=OPENAI_API_KEY)


def clean_text(s: str) -> str:
    if not s:
        return ""
    return (
        s.replace("â€™", "'")
         .replace("â€˜", "'")
         .replace("â€œ", '"')
         .replace("â€�", '"')
         .replace("â€“", "-")
         .replace("â€”", "-")
         .replace("â€¢", "•")
         .replace("â€¦", "...")
         .replace("Â", "")
    )


def build_context(chunks: List[dict]) -> str:
    blocks = []
    for c in chunks:
        blocks.append(
            f"SOURCE: {c.get('source', '')}\n"
            f"SECTION: {c.get('section', '')}\n"
            f"PAGES: {c.get('page_start')} - {c.get('page_end')}\n"
            f"TEXT:\n{clean_text(c.get('text', ''))}"
        )
    return "\n\n---\n\n".join(blocks)


def pretty_source(s: str) -> str:
    # Pub463_2024 -> IRS Pub 463 (2024)
    if (s or "").lower().startswith("pub"):
        parts = s.split("_")
        num = parts[0].replace("Pub", "")
        yr = parts[1] if len(parts) > 1 else ""
        return f"IRS Pub {num} ({yr})" if yr else f"IRS Pub {num}"
    return s or ""


def smart_snippet(
    text: str,
    keywords=("deduct", "deduction", "business", "expense", "meals",
              "travel", "home office", "vehicle", "equipment"),
    max_len: int = 260
) -> str:
    t = (text or "").replace("\n", " ")
    lower = t.lower()

    positions = [lower.find(k.lower())
                 for k in keywords if lower.find(k.lower()) != -1]
    idx = min(positions) if positions else 0

    start = max(idx - 60, 0)
    return t[start:start + max_len].strip()


def make_citations(chunks: List[dict], max_cites: int = 2) -> List[Dict[str, Any]]:
    cites: List[Dict[str, Any]] = []
    for c in chunks[:max_cites]:
        snippet = clean_text(smart_snippet(c.get("text", "")))
        cites.append({
            "source": pretty_source(c.get("source", "")),
            "section": c.get("section", "") or "",
            "page_start": c.get("page_start"),
            "page_end": c.get("page_end"),
            "snippet": snippet,
        })
    return cites


def confidence_score(chunks: List[dict]) -> float:
    if not chunks:
        return 0.0

    top_sim = float(chunks[0].get("similarity", 0.0))
    n = len(chunks)

    score = 0.0
    if top_sim >= 0.70:
        score += 0.55
    elif top_sim >= 0.60:
        score += 0.45
    elif top_sim >= 0.55:
        score += 0.35
    else:
        score += 0.20

    if n >= 4:
        score += 0.30
    elif n >= 2:
        score += 0.20
    else:
        score += 0.10

    return round(min(score, 0.92), 2)


def build_retrieval_hint(question: str) -> str:
    q = (question or "").lower()

    if any(k in q for k in ["meal", "meals", "lunch", "dinner", "coffee", "client meal"]):
        return " business meals 50% limit Pub 463"
    if any(k in q for k in ["hotel", "lodging", "airfare", "flight", "travel", "conference"]):
        return " travel lodging airfare business trip Pub 463"
    if any(k in q for k in ["ticket", "tickets", "entertainment", "baseball", "game", "concert", "sports"]):
        return " entertainment expense tickets client not deductible food separately 50% Pub 463"
    if any(k in q for k in ["laptop", "computer", "equipment", "camera", "depreciation", "section 179"]):
        return " business equipment depreciation section 179 Pub 946"
    if any(k in q for k in ["home office", "rent", "utilities", "exclusive", "regular"]):
        return " business use of home home office Pub 587"
    if any(k in q for k in ["car", "vehicle", "mileage", "gas", "uber", "lyft"]):
        return " car expenses standard mileage rate Pub 463"
    return " IRS publication guidance"


def needs_clarification(q: str) -> bool:
    t = (q or "").strip().lower()

    # If user already mentioned a clear topic/expense keyword,
    # DO NOT ask a clarifier (we can answer from IRS docs).
    KNOWN_TOPICS = [
        # meals / entertainment
        "meal", "meals", "lunch", "dinner", "coffee",
        "ticket", "tickets", "entertainment", "baseball", "game", "concert", "sports",

        # travel
        "travel", "trip", "airfare", "flight", "hotel", "lodging", "conference",

        # home office
        "home office", "rent", "utilities", "exclusive", "regular",

        # vehicle
        "car", "vehicle", "mileage", "gas", "uber", "lyft",

        # equipment/software
        "laptop", "computer", "camera", "equipment", "software", "subscription",
        "depreciation", "section 179",
    ]

    if any(k in t for k in KNOWN_TOPICS):
        return False

    # Truly vague patterns → ask 1 follow-up
    vague_phrases = [
        "is this deductible",
        "can i deduct this",
        "write this off",
        "is it deductible",
        "what category",
        "is this a business expense",
    ]
    if any(v in t for v in vague_phrases):
        return True

    # Very short + no topic keywords → unclear
    if len(t.split()) < 5:
        return True

    # Lots of pronouns with no topic → unclear
    if any(x in t.split() for x in ["this", "that", "it"]) and not any(k in t for k in KNOWN_TOPICS):
        return True

    return False


def generate_answer(question: str, top_k: int = 8) -> Dict[str, Any]:
    q_lower = (question or "").lower()

    # -------------------------
    # 0) Smart clarifying question (BEFORE retrieval)
    # -------------------------
    if needs_clarification(question):
        follow = "What is the expense, and is it 100% business use or mixed personal use?"
        log_event({
            "type": "clarifier",
            "question": question,
            "followup_question": follow
        })
        return {
            "answer_text": follow,
            "followup_question": follow,
            "citations": [],
            "confidence_score": 0.4,
            "blocked_reason": None,
        }

    # -------------------------
    # 1) Source routing (reduce noise)
    # -------------------------
    whitelist = None

    if any(k in q_lower for k in ["meal", "meals", "lunch", "dinner", "coffee", "client meal"]):
        whitelist = ["Pub463_2024"]

    elif any(k in q_lower for k in ["ticket", "tickets", "entertainment", "baseball", "game", "concert", "sports"]):
        whitelist = ["Pub463_2024"]

    elif any(k in q_lower for k in ["laptop", "computer", "equipment", "camera", "depreciation", "section 179"]):
        whitelist = ["Pub946_2024"]

    elif any(k in q_lower for k in ["home office", "rent", "utilities", "exclusive", "regular"]):
        whitelist = ["Pub587_2024"]

    elif any(k in q_lower for k in ["hotel", "lodging", "airfare", "flight", "travel", "conference"]):
        whitelist = ["Pub463_2024"]

    elif any(k in q_lower for k in ["car", "vehicle", "mileage", "gas", "uber", "lyft"]):
        whitelist = ["Pub463_2024"]

    # -------------------------
    # 2) First retrieval
    # -------------------------
    chunks = retrieve_top_chunks(question, top_k=top_k)

    # Apply whitelist filtering
    if whitelist and chunks:
        chunks = [c for c in chunks if str(c.get("source", "")) in whitelist]

    # -------------------------
    # 3) Retry once if weak/off-topic
    # -------------------------
    hint = build_retrieval_hint(question)

    looks_weak = (not chunks) or float(
        chunks[0].get("similarity", 0.0) or 0.0) < 0.58

    looks_off = False
    if chunks:
        top_text = str(chunks[0].get("text", "")).lower()

        if any(x in q_lower for x in ["meal", "meals"]) and any(y in top_text for y in ["section 179", "depreciat"]):
            looks_off = True

        if any(x in q_lower for x in ["ticket", "tickets", "entertainment", "baseball", "game"]) and not any(
            y in top_text for y in ["entertainment", "tickets", "food and beverages", "meal"]
        ):
            looks_off = True

    if hint and (looks_weak or looks_off):
        retry_question = question + " " + hint
        chunks = retrieve_top_chunks(retry_question, top_k=top_k)

        if whitelist and chunks:
            chunks = [c for c in chunks if str(
                c.get("source", "")) in whitelist]

    # -------------------------
    # 4) Retrieval quality gate
    # -------------------------
    allowed, reason = rag_quality_gate(question, chunks)
    if not allowed:
        log_event({
            "type": "rag_blocked",
            "question": question,
            "reason": reason,
            "retrieved_count": len(chunks),
            "top_similarity": float(chunks[0].get("similarity", 0.0)) if chunks else 0.0,
        })
        return {
            "answer_text": "I cannot confirm from the provided IRS sources.",
            "citations": [],
            "confidence_score": 0.0,
            "blocked_reason": reason,
        }

    # -------------------------
    # 5) Build context + call LLM
    # -------------------------
    context = build_context(chunks)

    system_prompt = (
        "You are a tax information assistant.\n"
        "RULES:\n"
        "- Only answer using the provided IRS context.\n"
        "- If the context does not contain the answer, say: 'I cannot confirm from the provided IRS sources.'\n"
        "- Use clear IRS language when available (e.g., 'ordinary and necessary').\n"
        "- Do not invent thresholds or percentages not present in context.\n"
        "- Do not compute numbers.\n"
        "- Do not provide legal advice.\n"
        "- Keep the answer short, direct, and practical.\n"
    )

    user_prompt = (
        f"QUESTION:\n{question}\n\n"
        f"IRS CONTEXT:\n{context}\n\n"
        "Return a helpful answer using ONLY the IRS context."
    )

    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    answer_text = clean_text((resp.choices[0].message.content or "").strip())
    answer_lower = answer_text.lower()
    ctx_lower = (context or "").lower()

    # -------------------------
    # 6) Hard grounding check
    # -------------------------
    SUSPICIOUS_TERMS = ["section 179", "179 deduction",
                        "bonus depreciation", "depreciat"]

    ungrounded = [t for t in SUSPICIOUS_TERMS if (
        t in answer_lower and t not in ctx_lower)]
    if ungrounded:
        log_event({
            "type": "rag_blocked",
            "question": question,
            "reason": "ungrounded_terms",
            "ungrounded_terms": ungrounded,
            "retrieved_count": len(chunks),
            "top_similarity": float(chunks[0].get("similarity", 0.0)) if chunks else 0.0,
            "answer_preview": answer_text[:200],
        })
        return {
            "answer_text": "I cannot confirm from the provided IRS sources.",
            "citations": [],
            "confidence_score": 0.0,
            "blocked_reason": "ungrounded_terms",
        }

    # -------------------------
    # 7) Uncertainty blocker
    # -------------------------
    BAD_PHRASES = [
        "consult a cpa",
        "i'm not sure",
        "i cannot determine",
        "might be deductible",
        "could be deductible",
        "it depends",
        "possible exception",
        "rare exception",
    ]

    if any(p in answer_lower for p in BAD_PHRASES):
        log_event({
            "type": "rag_blocked",
            "question": question,
            "reason": "hallucination_blocker",
            "retrieved_count": len(chunks),
            "top_similarity": float(chunks[0].get("similarity", 0.0)) if chunks else 0.0,
            "answer_preview": answer_text[:200],
        })
        return {
            "answer_text": "I cannot confirm from the provided IRS sources.",
            "citations": [],
            "confidence_score": 0.0,
            "blocked_reason": "hallucination_blocker",
        }

    # -------------------------
    # 8) Final response + logging
    # -------------------------
    conf = confidence_score(chunks)
    cites = make_citations(chunks, max_cites=2)

    log_event({
        "type": "rag_answer",
        "question": question,
        "retrieved_count": len(chunks),
        "top_similarity": float(chunks[0].get("similarity", 0.0)) if chunks else 0.0,
        "answer_preview": answer_text[:200],
        "confidence_score": conf,
        "blocked_reason": None,
        "sources": [
            {
                "chunk_id": c.get("chunk_id"),
                "source": c.get("source"),
                "page_start": c.get("page_start"),
                "page_end": c.get("page_end"),
                "similarity": c.get("similarity"),
            } for c in chunks[:5]
        ],
    })

    return {
        "answer_text": answer_text,
        "citations": cites,
        "confidence_score": conf,
        "blocked_reason": None,
    }
