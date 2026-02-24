from typing import List, Literal, Optional, Dict, Any
from datetime import datetime
import uuid
import json
import os
import math

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import OpenAI

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

Role = Literal["user", "assistant"]


class HistoryItem(BaseModel):
    role: Role
    content: str


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    history: List[HistoryItem] = Field(default_factory=list)


class ChatResponse(BaseModel):
    conversation_id: str
    answer_text: str
    deductibility_type: str
    category_tag: str
    spending_timing: str
    followup_question: Optional[str] = None
    confidence_score: float
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
# CHAT (LLM only)
# -------------------------
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())

    with get_conn() as conn:
        with conn.cursor() as cur:
            ensure_conversation(cur, conversation_id)
            insert_message(cur, conversation_id, "user", req.message)

            msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
            for h in req.history[-10:]:
                msgs.append({"role": h.role, "content": h.content})
            msgs.append({"role": "user", "content": req.message})

            try:
                resp = client.chat.completions.create(
                    model="gpt-5.2",
                    messages=msgs,
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )
                raw = (resp.choices[0].message.content or "{}").strip()
                data = json.loads(raw)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

            answer_text = str(data.get("answer_text", "")).strip()
            deductibility_type = str(
                data.get("deductibility_type", "unclear")).lower()
            category_tag = str(data.get("category_tag", "general")).lower()
            spending_timing = str(
                data.get("spending_timing", "unclear")).lower()
            followup_question = data.get("followup_question") or None
            confidence_score = float(data.get("confidence_score", 0.5))

            assistant_message_id = insert_message(
                cur,
                conversation_id,
                "assistant",
                answer_text,
                deductibility_type=deductibility_type,
                category_tag=category_tag,
                spending_timing=spending_timing,
                followup_question=followup_question,
                confidence_score=confidence_score,
            )

            conn.commit()

    return ChatResponse(
        conversation_id=conversation_id,
        answer_text=answer_text,
        deductibility_type=deductibility_type,
        category_tag=category_tag,
        spending_timing=spending_timing,
        followup_question=followup_question,
        confidence_score=confidence_score,
        disclaimer=None,
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
            status_code=400,
            detail=f"Could not read CSV: {str(e)}"
        )

    if "description" not in df.columns or "amount" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="CSV must contain description and amount columns"
        )

    df["category"] = df["description"].astype(str).apply(_guess_category)

    with get_conn() as conn:
        with conn.cursor() as cur:
            ensure_conversation(cur, conversation_id)

            # ✅ CLEAR OLD EXPENSES FOR THIS CONVERSATION
            cur.execute(
                """
                DELETE FROM expenses
                WHERE conversation_id = %s
                """,
                (conversation_id,)
            )

            # ✅ INSERT NEW ROWS
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

            # 🔥 DELETE existing income first
            cur.execute(
                """
                DELETE FROM income_sources
                WHERE conversation_id = %s
                """,
                (req.conversation_id,)
            )

            # Insert new income
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
@app.post("/calc/estimate", response_model=CalcEstimateResponse)
def calc_estimate(req: CalcEstimateRequest):
    try:
        # auto-load expenses if empty
        if (not req.expenses) and req.conversation_id:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    rows = get_expenses_for_conversation(
                        cur, req.conversation_id)

            expenses_list: List[ExpenseItem] = []
            for r in rows:
                if isinstance(r, dict):
                    expenses_list.append(
                        ExpenseItem(
                            category=r["category"],
                            amount=float(r["amount"]),
                            description=r.get("description"),
                        )
                    )
                else:
                    expenses_list.append(
                        ExpenseItem(
                            category=r[0],
                            amount=float(r[1]),
                            description=r[2],
                        )
                    )
            req.expenses = expenses_list

        # auto-load income if empty
        if (not req.income_sources) and req.conversation_id:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    rows = get_income_sources_for_conversation(
                        cur, req.conversation_id)

            income_list: List[IncomeSource] = []
            for r in rows:
                if isinstance(r, dict):
                    income_list.append(
                        IncomeSource(
                            type=r["type"],
                            amount=float(r["amount"]),
                            description=r.get("description"),
                        )
                    )
                else:
                    income_list.append(
                        IncomeSource(
                            type=r[0],
                            amount=float(r[1]),
                            description=r[2],
                        )
                    )
            req.income_sources = income_list

        return estimate_tax(req)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Calc error: {repr(e)}")


# -------------------------
# GENERATE REPORT (FROM DB)
# -------------------------
@app.post("/generate-report/{conversation_id}")
def generate_report(conversation_id: str):
    # Load expenses
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

    # Load income
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
        "deductions_by_category": [
            {"category": d.category, "amount": d.amount}
            for d in calc_res.deductions_by_category
        ],
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
                text=r["text"]),
            )
        else:
            out.append(MessageOut(
                id=str(r[0]),
                conversation_id=str(r[1]),
                role=r[2],
                text=r[3],
                created_at=r[4],
            ))
    return out
