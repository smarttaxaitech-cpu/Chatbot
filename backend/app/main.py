# app/main.py

import re
from app.routes.rag import router as rag_router

from typing import List, Literal, Optional, Dict, Any
from datetime import datetime
import uuid
import json
import os

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import OpenAI

from app.logging.logger import log_event
from app.analytics.tagger import tag_question, needs_clarification, build_clarifying_question

from services.tax_engine import calculate_tax_estimate

# ---- RAG plumbing (your real modules) ----
from app.rag.retrieve import retrieve_top_chunks as retrieve_chunks
from app.rag.guardrails import rag_quality_gate, should_block_question
from app.rag.answer import build_context as format_chunks_for_prompt
from app.rag.answer import make_citations as build_citations

from services.deduction_rules import evaluate_deductibility

from .prompt import SYSTEM_PROMPT
from .calc import (
    CalcEstimateRequest,
    CalcEstimateResponse,
    ExpenseItem,
    IncomeSource,
    CalcAssumptions,
    estimate_tax,
)
from .report_generator import generate_pdf

from .db import (
    get_conn,
    ensure_conversation,
    insert_message,
    insert_feedback,
    # expenses
    insert_expense,
    get_expenses_for_conversation,
    # income
    insert_income_source,
    get_income_sources_for_conversation,
)


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


load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

app = FastAPI()

origins = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# keep if you still expose separate /rag routes
# app.include_router(rag_router)

Role = Literal["user", "assistant"]


# -------------------------
# Helpers
# -------------------------
def hallucination_detected(text: str) -> bool:
    """
    Post-answer guardrail: block uncertain / non-grounded language.
    Keep it conservative for MVP.
    """
    t = (text or "").lower()
    bad = [
        "it depends",
        "might be",
        "may be",
        "possibly",
        "not sure",
        "consult a cpa",
        "talk to a cpa",
        "i recommend speaking",
        "i can't guarantee",
        "unclear",
    ]
    return any(b in t for b in bad)


def remove_advisory_sentences(text: str) -> str:
    """
    Remove sentences that contain recommendation,
    referral, or tailoring language.
    """

    if not text:
        return text

    sentences = re.split(r'(?<=[.!?])\s+', text)

    advisory_triggers = [
        "you should",
        "you need to",
        "you must",
        "hire",
        "consult",
        "talk to",
        "speak with",
        "seek advice",
        "pay for",
        "get a cpa",
        "consider hiring",
        "recommendation",
        "to tailor",
        "if you tell me",
        "to give a more",
        "let me know your",
        "based on your situation",
        "what you can do",
        "if you paste",
        "if you provide",
        "send me",
        "paste the exact",
    ]

    clean = []

    for sentence in sentences:
        lower = sentence.lower()
        if not any(trigger in lower for trigger in advisory_triggers):
            clean.append(sentence)

    return " ".join(clean).strip()


def strip_llm_disclaimer(text: str) -> str:
    """
    Remove any LLM-generated liability/disclaimer language.
    Marketing-safe mode.
    """

    if not text:
        return text

    sentences = re.split(r'(?<=[.!?])\s+', text)

    blocked_keywords = [
        "disclaimer",
        "not legal advice",
        "not tax advice",
        "not personalized tax advice",
        "general tax information",
        "this is general tax information",
        "not accounting advice",
        "educational purposes",
        "professional-client relationship",
        "consult",
        "qualified professional",
        "cpa",
        "attorney",
        "tax professional",
        "disclaim",
        "liability",
        "no guarantee",
        "guarantee",
        "fully protected",
        "audit protection",
        "you are responsible",
        "not a cpa",
        "not an attorney",
        "does not prevent",
        "cannot guarantee",
    ]

    clean = []

    for sentence in sentences:
        lower = sentence.lower()
        if not any(keyword in lower for keyword in blocked_keywords):
            clean.append(sentence)

    return " ".join(clean).strip()


def is_legal_reference_question(text: str) -> bool:
    """
    Detect if the user is asking for a specific legal code,
    subsection, statute, or citation.
    """
    if not text:
        return False

    t = text.lower()

    legal_triggers = [
        "irc",
        "internal revenue code",
        "subsection",
        "code section",
        "section ",
        "§",
        "statute",
        "regulation",
        "cfr",
        "citation",
        "exact subsection",
        "code reference",
    ]

    return any(trigger in t for trigger in legal_triggers)


# -------------------------
# Models
# -------------------------
class HistoryItem(BaseModel):
    role: Role
    content: str


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    history: List[HistoryItem] = Field(default_factory=list)


class Citation(BaseModel):
    source: str
    section: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    snippet: str


class ChatResponse(BaseModel):
    conversation_id: str
    answer_text: str
    deductibility_type: str
    category_tag: str
    spending_timing: str
    followup_question: Optional[str] = None
    confidence_score: float

    citations: List[Citation] = Field(default_factory=list)
    blocked: bool = False
    block_reason: Optional[str] = None

    disclaimer: Optional[str] = None
    assistant_message_id: str
    summary: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    rating: Literal["up", "down"]
    comment: Optional[str] = None


class ConversationOut(BaseModel):
    id: str
    created_at: datetime
    last_activity_at: datetime


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    text: str
    created_at: datetime


class IncomeAddRequest(BaseModel):
    conversation_id: str
    income_sources: List[IncomeSource]


@app.get("/health")
def health():
    return {"status": "ok"}


# -------------------------
# CHAT (Strict RAG)
# -------------------------
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())
    data: Dict[str, Any] = {}

    blocked = False
    block_reason = None

    # ---- metadata (Requirement #6)
    meta = tag_question(req.message)
    category_tag = meta["category_tag"]
    spending_timing = meta["spending_timing"]

    # ---- Deterministic deductibility override (MVP accuracy layer)
    # ---- Deterministic deductibility override (MVP accuracy layer)
    deduction_categories = [
        "equipment",
        "software",
        "meals",
        "home_office",
        "vehicle",
        "travel",
    ]

    if category_tag in deduction_categories and not is_legal_reference_question(req.message):

        result = evaluate_deductibility(
            category=category_tag,
            amount=0,  # MVP: no amount parsing yet
            business_use_percent=None,
        )

        answer_text = (
            f"Deductibility: {result['deductible'].capitalize()}\n\n"
            f"IRS Rule: {result['rule']}\n\n"
            f"Confidence: {result['confidence'].capitalize()}"
        )
        answer_text = remove_advisory_sentences(answer_text)

        answer_text = strip_llm_disclaimer(answer_text)

        confidence_score = 1.0 if result["confidence"] == "high" else 0.6
        citations = []
        blocked = False
        block_reason = None

        with get_conn() as conn:
            with conn.cursor() as cur:
                ensure_conversation(cur, conversation_id)
                insert_message(cur, conversation_id, "user", req.message)

                assistant_message_id = insert_message(
                    cur,
                    conversation_id,
                    "assistant",
                    answer_text,
                    deductibility_type=result["deductible"],
                    category_tag=category_tag,
                    spending_timing=spending_timing,
                    followup_question=None,
                    confidence_score=confidence_score,
                )
                conn.commit()

        log_event({
            "type": "bot_message",
            "conversation_id": conversation_id,
            "question": req.message,
            "answer_text": answer_text,
            "blocked": False,
            "confidence": confidence_score,
            "citations_count": 0,
            "category_tag": category_tag,
            "spending_timing": spending_timing,
            "deterministic_override": True,
        })

        return ChatResponse(
            conversation_id=conversation_id,
            answer_text=answer_text,
            deductibility_type=result["deductible"],
            category_tag=category_tag,
            spending_timing=spending_timing,
            followup_question=None,
            confidence_score=confidence_score,
            citations=[],
            blocked=False,
            block_reason=None,
            disclaimer="This is general IRS-based tax information for educational purposes.",
            assistant_message_id=assistant_message_id,
            summary=None,
        )

    # ---- log user message (Requirement #5)
    log_event({
        "type": "user_message",
        "conversation_id": conversation_id,
        "text": req.message,
        "category_tag": category_tag,
        "spending_timing": spending_timing,
    })

    # 0) Smart clarifying question (Requirement #3)
    if needs_clarification(req.message):
        answer_text = build_clarifying_question(req.message)
        answer_text = remove_advisory_sentences(answer_text)

        answer_text = strip_llm_disclaimer(answer_text)
        confidence_score = 0.0
        citations = []
        blocked = False
        block_reason = None

        # minimal structured fields
        data = {
            "deductibility_type": "unclear",
            "category_tag": category_tag,
            "spending_timing": spending_timing,
            "followup_question": answer_text,
        }

        with get_conn() as conn:
            with conn.cursor() as cur:
                ensure_conversation(cur, conversation_id)
                insert_message(cur, conversation_id, "user", req.message)

                assistant_message_id = insert_message(
                    cur,
                    conversation_id,
                    "assistant",
                    answer_text,
                    deductibility_type="unclear",
                    category_tag=category_tag,
                    spending_timing=spending_timing,
                    followup_question=answer_text,
                    confidence_score=0.0,
                )
                conn.commit()

        log_event({
            "type": "bot_message",
            "conversation_id": conversation_id,
            "question": req.message,
            "answer_text": answer_text,
            "followup_question": answer_text,
            "blocked": False,
            "confidence": 0.0,
            "citations_count": 0,
        })

        return ChatResponse(
            conversation_id=conversation_id,
            answer_text=answer_text,
            deductibility_type="unclear",
            category_tag=category_tag,
            spending_timing=spending_timing,
            followup_question=answer_text,
            confidence_score=0.0,
            citations=[],
            blocked=False,
            block_reason=None,
            disclaimer="This is general IRS-based tax information for educational purposes.",
            assistant_message_id=assistant_message_id,
            summary=None,
        )

    # 1) Block obviously irrelevant/personal questions BEFORE retrieval/LLM
    if should_block_question(req.message):
        answer_text = "I can only help with U.S. freelancer and small business tax questions."
        confidence_score = 0.0
        citations = []
        blocked = True
        block_reason = "blocked_question"

        log_event({
            "type": "rag_blocked_pre",
            "conversation_id": conversation_id,
            "question": req.message,
            "reason": block_reason,
        })

    else:
        # 2) Retrieve
        chunks = retrieve_chunks(req.message, top_k=5)

        log_event({
            "type": "rag_retrieve",
            "conversation_id": conversation_id,
            "question": req.message,
            "retrieved_count": len(chunks),
            "top_similarity": float(chunks[0].get("similarity", 0.0)) if chunks else 0.0,
        })

        # 3) Retrieval quality gate (Level 5)
        allowed, reason = rag_quality_gate(req.message, chunks)

        if not allowed:
            answer_text = "I don’t have enough IRS reference support to answer that confidently."
            confidence_score = 0.0
            citations = []
            blocked = False
            block_reason = reason

            log_event({
                "type": "rag_blocked_gate",
                "conversation_id": conversation_id,
                "question": req.message,
                "reason": reason,
                "retrieved_count": len(chunks),
                "top_similarity": float(chunks[0].get("similarity", 0.0)) if chunks else 0.0,
            })

        else:
            # 4) Build strict context + citations
            context_text = format_chunks_for_prompt(chunks)
            citations = build_citations(chunks)

            msgs = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "system",
                    "content": context_text
                }
            ]

            for h in req.history[-10:]:
                msgs.append({"role": h.role, "content": h.content})

            msgs.append({"role": "user", "content": req.message})

            # 5) Call LLM (JSON response)
            try:
                resp = client.chat.completions.create(
                    model="gpt-5.2",
                    messages=msgs,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                raw = (resp.choices[0].message.content or "{}").strip()
                data = json.loads(raw)
            except Exception as e:
                log_event({
                    "type": "llm_error",
                    "conversation_id": conversation_id,
                    "question": req.message,
                    "error": str(e),
                })
                raise HTTPException(status_code=400, detail=str(e))

            answer_text = clean_text(str(data.get("answer_text", "")).strip())
            answer_text = strip_llm_disclaimer(answer_text)

            # ---- Advisory language guard (Marketing-safe mode)
            # ---- Advisory language guard (Marketing-safe mode)

            # ---- Advisory language guard (Marketing-safe mode)
            # ---- Advisory removal (Marketing-safe mode)
            answer_text = remove_advisory_sentences(answer_text)

            # ---- Confidence tied to retrieval similarity
            top_similarity = float(
                chunks[0].get("similarity", 0.0)
            ) if chunks else 0.0

            if top_similarity >= 0.85:
                confidence_score = 0.95
            elif top_similarity >= 0.70:
                confidence_score = 0.75
            elif top_similarity >= 0.55:
                confidence_score = 0.6
            else:
                confidence_score = 0.35

            # ---- Post-answer hallucination guard
            if hallucination_detected(answer_text):
                confidence_score = 0.3

            # ---- Force metadata fields (Requirement #6)
            data["category_tag"] = str(
                data.get("category_tag") or category_tag
            ).lower()

            data["spending_timing"] = str(
                data.get("spending_timing") or spending_timing
            ).lower()

    # ---- Persist conversation/messages ----
    with get_conn() as conn:
        with conn.cursor() as cur:
            ensure_conversation(cur, conversation_id)
            insert_message(cur, conversation_id, "user", req.message)

            assistant_message_id = insert_message(
                cur,
                conversation_id,
                "assistant",
                answer_text,
                deductibility_type=str(
                    data.get("deductibility_type", "unclear")).lower()
                if not blocked else "unclear",
                category_tag=(
                    data.get("category_tag") or category_tag
                ).lower()
                if not blocked else category_tag,
                spending_timing=(
                    data.get("spending_timing") or spending_timing
                ).lower()
                if not blocked else spending_timing,
                followup_question=(data.get("followup_question") or None)
                if not blocked else None,
                confidence_score=confidence_score,
            )
            conn.commit()

    answer_text = remove_advisory_sentences(answer_text)

    answer_text = strip_llm_disclaimer(answer_text)

    # ---- Log final bot message (Requirement #5) ----
    log_event({
        "type": "bot_message",
        "conversation_id": conversation_id,
        "question": req.message,
        "answer_text": answer_text,
        "blocked": blocked,
        "block_reason": block_reason,
        "confidence": confidence_score,
        "citations_count": len(citations or []),
        "category_tag": str(data.get("category_tag", category_tag)).lower(),
        "spending_timing": str(data.get("spending_timing", spending_timing)).lower(),
    })

    return ChatResponse(
        conversation_id=conversation_id,
        answer_text=answer_text,
        deductibility_type=str(
            data.get("deductibility_type", "unclear")).lower()
        if not blocked else "unclear",
        category_tag=(data.get("category_tag") or category_tag).lower()
        if not blocked else category_tag,
        spending_timing=(
            data.get("spending_timing") or spending_timing
        ).lower()
        if not blocked else spending_timing,
        followup_question=(data.get("followup_question") or None)
        if not blocked else None,
        confidence_score=confidence_score,
        citations=citations,
        blocked=blocked,
        block_reason=block_reason,
        disclaimer="This is general IRS-based tax information for educational purposes.",
        assistant_message_id=assistant_message_id,
        summary=None,
    )


# -------------------------
# EXPENSE CSV UPLOAD
# -------------------------
def _guess_category(desc: str) -> str:
    d = (desc or "").lower()
    if any(k in d for k in ["car", "vehicle", "mileage", "gas", "auto", "uber", "lyft"]):
        return "vehicle"
    if any(k in d for k in ["rent", "studio", "office", "utilities", "home office"]):
        return "home_office"
    if any(k in d for k in ["laptop", "computer", "phone", "camera", "equipment", "printer", "monitor"]):
        return "equipment"
    if any(k in d for k in ["software", "subscription", "saas", "adobe", "lightroom", "hosting"]):
        return "software"
    if any(k in d for k in ["ads", "advertising", "marketing", "promotion"]):
        return "advertising"
    if any(k in d for k in ["contractor", "assistant", "freelancer i hired"]):
        return "contractors"
    if any(k in d for k in ["meal", "meals", "lunch", "dinner", "coffee"]):
        return "meals"
    if any(k in d for k in ["travel", "flight", "hotel", "conference"]):
        return "travel"
    return "business_expense"


@app.post("/expenses/upload")
async def upload_expenses(conversation_id: str, file: UploadFile = File(...)):
    try:
        df = pd.read_csv(file.file)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Could not read CSV: {str(e)}")

    if "description" not in df.columns or "amount" not in df.columns:
        raise HTTPException(
            status_code=400, detail="CSV must contain description and amount columns")

    df["category"] = df["description"].astype(str).apply(_guess_category)

    with get_conn() as conn:
        with conn.cursor() as cur:
            ensure_conversation(cur, conversation_id)

            cur.execute(
                """
                DELETE FROM expenses
                WHERE conversation_id = %s
                """,
                (conversation_id,)
            )

            for _, row in df.iterrows():
                insert_expense(
                    cur,
                    conversation_id,
                    str(row["category"]),
                    float(row["amount"]),
                    str(row["description"]),
                )

            conn.commit()

    totals = df.groupby("category")["amount"].sum().to_dict()
    return {
        "total_uploaded": float(df["amount"].sum()),
        "category_breakdown": {k: float(v) for k, v in totals.items()},
    }


# -------------------------
# INCOME ADD (STRUCTURED)
# -------------------------
@app.post("/income/add")
def add_income(req: IncomeAddRequest):
    with get_conn() as conn:
        with conn.cursor() as cur:
            ensure_conversation(cur, req.conversation_id)

            cur.execute(
                """
                DELETE FROM income_sources
                WHERE conversation_id = %s
                """,
                (req.conversation_id,)
            )

            for inc in req.income_sources:
                insert_income_source(
                    cur,
                    req.conversation_id,
                    inc.type,
                    float(inc.amount),
                    inc.description,
                )

            conn.commit()

    return {"status": "ok", "count": len(req.income_sources)}


# -------------------------
# TAX ESTIMATE (DETERMINISTIC)
# -------------------------
@app.post("/calc/estimate")
def calc_estimate(req: CalcEstimateRequest):
    income = 0

    if req.income_sources:
        income = sum(i.amount for i in req.income_sources)
    elif hasattr(req, "income") and req.income:
        income = req.income

    if income < 0:
        raise HTTPException(status_code=400, detail="Income must be >= 0")

    if income == 0:
        return {
            "total_income": 0.0,
            "total_expenses": 0.0,
            "allowed_expenses": 0.0,
            "net_business_income": 0.0,
            "se_tax_deduction": 0.0,
            "qbi_deduction": 0.0,
            "taxable_income": 0.0,
            "income_tax": 0.0,
            "self_employment_tax": 0.0,
            "total_tax": 0.0,
            "deductions_by_category": {},
        }

    expenses_list = []

    if req.expenses:
        expenses_list = [{"category": e.category, "amount": e.amount}
                         for e in req.expenses]
    else:
        with get_conn() as conn:
            with conn.cursor() as cur:
                rows = get_expenses_for_conversation(cur, req.conversation_id)

        for r in rows:
            if isinstance(r, dict):
                expenses_list.append(
                    {"category": r["category"], "amount": float(r["amount"])})
            else:
                expenses_list.append({"category": r[0], "amount": float(r[1])})

    result = calculate_tax_estimate(
        income=income,
        expenses=expenses_list,
        filing_status="single",
        home_office_sqft=req.home_office_sqft,
        vehicle_business_use_percent=req.vehicle_business_use_percent
    )
    return result


# -------------------------
# GENERATE REPORT (FROM DB)
# -------------------------
@app.post("/generate-report/{conversation_id}")
def generate_report(conversation_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            expense_rows = get_expenses_for_conversation(cur, conversation_id)

    if not expense_rows:
        raise HTTPException(status_code=404, detail="No expenses found")

    expenses: List[ExpenseItem] = []
    for r in expense_rows:
        if isinstance(r, dict):
            expenses.append(
                ExpenseItem(
                    category=r["category"],
                    amount=float(r["amount"]),
                    description=r.get("description"),
                )
            )
        else:
            expenses.append(
                ExpenseItem(
                    category=r[0],
                    amount=float(r[1]),
                    description=r[2],
                )
            )

    with get_conn() as conn:
        with conn.cursor() as cur:
            income_rows = get_income_sources_for_conversation(
                cur, conversation_id)

    if not income_rows:
        raise HTTPException(
            status_code=404, detail="No income found for this conversation")

    income_sources: List[IncomeSource] = []
    for r in income_rows:
        if isinstance(r, dict):
            income_sources.append(
                IncomeSource(
                    type=r["type"],
                    amount=float(r["amount"]),
                    description=r.get("description"),
                )
            )
        else:
            income_sources.append(
                IncomeSource(
                    type=r[0],
                    amount=float(r[1]),
                    description=r[2],
                )
            )

    calc_req = CalcEstimateRequest(
        conversation_id=conversation_id,
        income_sources=income_sources,
        expenses=expenses,
        assumptions=CalcAssumptions(assumed_marginal_rate=0.22),
    )

    calc_res = estimate_tax(calc_req)

    summary = {
        "total_income": calc_res.total_income,
        "total_expenses": calc_res.total_expenses,
        "net_business_income": calc_res.net_business_income,
        "self_employment_tax": calc_res.self_employment_tax,
        "income_tax_estimate": calc_res.income_tax_estimate,
        "total_estimated_tax": calc_res.total_estimated_tax,
        "deductions_by_category": [{"category": d.category, "amount": d.amount} for d in calc_res.deductions_by_category],
        "assumptions_used": calc_res.assumptions_used,
        "disclaimer": calc_res.disclaimer,
    }

    file_path = "smarttax_report.pdf"
    generate_pdf(summary, file_path)

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename="SmartTax_Report.pdf",
    )


# -------------------------
# FEEDBACK
# -------------------------
@app.post("/feedback")
def feedback(req: FeedbackRequest):
    log_event({
        "type": "feedback",
        "conversation_id": req.conversation_id,
        "message_id": req.message_id,
        "rating": req.rating,
        "comment": req.comment,
    })

    with get_conn() as conn:
        with conn.cursor() as cur:
            ensure_conversation(cur, req.conversation_id)
            insert_feedback(
                cur,
                conversation_id=req.conversation_id,
                message_id=req.message_id,
                rating=req.rating,
                comment=req.comment,
            )
            conn.commit()
    return {"status": "ok"}


# -------------------------
# CONVERSATIONS + MESSAGES
# -------------------------
@app.get("/conversations", response_model=List[ConversationOut])
def list_conversations(limit: int = 50, offset: int = 0):
    q = """
    SELECT
      c.id,
      c.created_at,
      GREATEST(
        c.created_at,
        COALESCE(MAX(m.created_at), 'epoch'::timestamptz),
        COALESCE(MAX(f.created_at), 'epoch'::timestamptz)
      ) AS last_activity_at
    FROM conversations c
    LEFT JOIN messages  m ON m.conversation_id = c.id
    LEFT JOIN feedback  f ON f.conversation_id = c.id
    GROUP BY c.id, c.created_at
    ORDER BY last_activity_at DESC
    LIMIT %s OFFSET %s;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(q, (limit, offset))
            rows = cur.fetchall()

    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append(ConversationOut(
                id=str(r["id"]),
                created_at=r["created_at"],
                last_activity_at=r["last_activity_at"],
            ))
        else:
            out.append(ConversationOut(
                id=str(r[0]),
                created_at=r[1],
                last_activity_at=r[2],
            ))
    return out


@app.get("/conversations/{conversation_id}/messages", response_model=List[MessageOut])
def list_messages(conversation_id: str):
    q = """
    SELECT id, conversation_id, role, text, created_at
    FROM messages
    WHERE conversation_id = %s
    ORDER BY created_at ASC, id ASC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(q, (conversation_id,))
            rows = cur.fetchall()

    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append(MessageOut(
                id=str(r["id"]),
                conversation_id=str(r["conversation_id"]),
                role=r["role"],
                text=r["text"],
                created_at=r["created_at"],
            ))
        else:
            out.append(MessageOut(
                id=str(r[0]),
                conversation_id=str(r[1]),
                role=r[2],
                text=r[3],
                created_at=r[4],
            ))
    return out
