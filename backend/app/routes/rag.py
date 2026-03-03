from fastapi import APIRouter
from pydantic import BaseModel
from app.rag.retrieve import retrieve_top_chunks

router = APIRouter(prefix="/rag", tags=["rag"])

class RetrieveReq(BaseModel):
    question: str
    top_k: int = 5

@router.post("/retrieve")
def rag_retrieve(req: RetrieveReq):
    chunks = retrieve_top_chunks(req.question, req.top_k)
    return {"question": req.question, "top_k": req.top_k, "chunks": chunks}

from app.rag.answer import generate_answer

@router.post("/answer")
def rag_answer(req: RetrieveReq):
    return generate_answer(req.question, req.top_k)