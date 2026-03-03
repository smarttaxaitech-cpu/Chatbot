import os
from typing import List, Dict, Any, Optional
import psycopg
from pgvector.psycopg import register_vector
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
SIM_THRESHOLD = float(os.getenv("RAG_SIM_THRESHOLD", "0.55"))

client = OpenAI(api_key=OPENAI_API_KEY)

def embed_query(text: str) -> list[float]:
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return resp.data[0].embedding

def retrieve_top_chunks(
    question: str,
    top_k: int = 5,
    source_whitelist: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    expanded_query = question + " IRS tax deduction rule publication guidance"
    q_emb = embed_query(expanded_query)

    fetch_k = max(top_k * 6, 30)

    base_sql = """
    SELECT
      c.id,
      c.source,
      c.section,
      c.page_start,
      c.page_end,
      c.text,
      1 - (e.embedding <=> (%s)::vector(1536)) AS similarity
    FROM rag_embeddings e
    JOIN rag_chunks c ON c.id = e.chunk_id
    """

    params: list[Any] = [q_emb]

    # Optional source routing
    if source_whitelist:
        placeholders = ",".join(["%s"] * len(source_whitelist))
        base_sql += f" WHERE c.source IN ({placeholders})"
        params.extend(source_whitelist)

    base_sql += """
    ORDER BY e.embedding <=> (%s)::vector(1536)
    LIMIT %s;
    """

    params.extend([q_emb, fetch_k])

    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(base_sql, params)
            rows = cur.fetchall()

    # Similarity filter AFTER fetch
    rows = [r for r in rows if float(r[6]) >= SIM_THRESHOLD]
    rows = rows[:top_k]

    results: List[Dict[str, Any]] = []
    for r in rows:
        results.append({
            "chunk_id": r[0],
            "source": r[1],
            "section": r[2] or "",
            "page_start": r[3],
            "page_end": r[4],
            "text": r[5],
            "similarity": float(r[6]),
        })

    return results