import os
import json
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI
import psycopg
from pgvector.psycopg import register_vector

# Load environment variables
load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parents[1]
CHUNKS_DIR = BACKEND_DIR / "rag_sources" / "irs_2025" / "chunks"

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in .env")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows

def embed_batch(texts: List[str]) -> List[List[float]]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts
    )
    return [d.embedding for d in response.data]

def main():
    chunk_files = sorted(CHUNKS_DIR.glob("*.jsonl"))

    if not chunk_files:
        print("❌ No chunk files found.")
        return

    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)
        conn.autocommit = False

        total_chunks = 0
        total_embeddings = 0

        for file in chunk_files:
            rows = read_jsonl(file)
            print(f"\n📄 Processing {file.name} ({len(rows)} chunks)")

            # Insert chunks
            with conn.cursor() as cur:
                for c in rows:
                    cur.execute("""
                        INSERT INTO rag_chunks
                        (id, source, section, page_start, page_end, token_count, text)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            source = EXCLUDED.source,
                            section = EXCLUDED.section,
                            page_start = EXCLUDED.page_start,
                            page_end = EXCLUDED.page_end,
                            token_count = EXCLUDED.token_count,
                            text = EXCLUDED.text
                    """, (
                        c["id"],
                        c["source"],
                        c.get("section", ""),
                        c.get("page_start"),
                        c.get("page_end"),
                        c.get("token_count"),
                        c["text"]
                    ))
            conn.commit()
            total_chunks += len(rows)
            print("✅ Chunks stored")

            # Embed in batches
            BATCH_SIZE = 50
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i+BATCH_SIZE]
                texts = [b["text"] for b in batch]
                embeddings = embed_batch(texts)

                with conn.cursor() as cur:
                    for item, emb in zip(batch, embeddings):
                        cur.execute("""
                            INSERT INTO rag_embeddings
                            (chunk_id, embedding, embedding_model)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (chunk_id) DO UPDATE SET
                                embedding = EXCLUDED.embedding,
                                embedding_model = EXCLUDED.embedding_model
                        """, (
                            item["id"],
                            emb,
                            EMBEDDING_MODEL
                        ))

                conn.commit()
                total_embeddings += len(batch)
                print(f"✅ Embedded {total_embeddings} so far")

        print("\n🎉 DONE")
        print("Total chunks:", total_chunks)
        print("Total embeddings:", total_embeddings)

if __name__ == "__main__":
    main()