from pathlib import Path
import json
import re
from typing import List, Dict, Any, Optional
import tiktoken

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEXT_DIR = BACKEND_DIR / "rag_sources" / "irs_2025" / "text"
CHUNKS_DIR = BACKEND_DIR / "rag_sources" / "irs_2025" / "chunks"

# Token settings (MVP)
TARGET_TOKENS = 700          # aim
MIN_TOKENS = 450             # avoid too small chunks
MAX_TOKENS = 850             # hard max
OVERLAP_TOKENS = 120         # overlap for continuity

# Embedding model tokenizer (good default)
ENC = tiktoken.get_encoding("cl100k_base")

HEADING_RE = re.compile(r"^(?:[A-Z][A-Za-z0-9 /&(),\-]{6,}|Chapter \d+|Part \d+|Table \d+)\s*$")

def count_tokens(text: str) -> int:
    return len(ENC.encode(text or ""))

def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def split_to_paragraphs(page_text: str) -> List[str]:
    # split by blank lines (best for IRS PDFs)
    parts = [p.strip() for p in re.split(r"\n\s*\n", page_text) if p.strip()]
    return parts

def detect_section(paragraphs: List[str], last_section: Optional[str]) -> Optional[str]:
    """
    Best effort:
    - if a paragraph looks like a heading, treat it as a section title.
    """
    for p in paragraphs[:3]:
        one_line = p.replace("\n", " ").strip()
        if 6 <= len(one_line) <= 90 and HEADING_RE.match(one_line):
            return one_line
    return last_section

def build_chunks(pages: List[Dict[str, Any]], source_name: str) -> List[Dict[str, Any]]:
    """
    pages: list of {"page_number": int, "text": str, ...}
    """
    chunks: List[Dict[str, Any]] = []
    buf: List[str] = []
    buf_tokens = 0

    cur_section: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None

    def flush_chunk():
        nonlocal buf, buf_tokens, page_start, page_end, cur_section

        text = normalize("\n\n".join(buf))
        if not text:
            return

        tok = count_tokens(text)
        # skip tiny chunks
        if tok < 120:
            return

        chunk_id = f"{Path(source_name).stem}_p{page_start}_to_p{page_end}_c{len(chunks)+1:04d}"

        chunks.append({
            "id": chunk_id,
            "source": source_name,
            "section": cur_section or "",
            "page_start": page_start,
            "page_end": page_end,
            "text": text,
            "token_count": tok
        })

        # Overlap handling: keep last OVERLAP_TOKENS tokens as next buffer start
        if OVERLAP_TOKENS > 0:
            tokens = ENC.encode(text)
            overlap = tokens[-OVERLAP_TOKENS:] if len(tokens) > OVERLAP_TOKENS else tokens
            buf = [ENC.decode(overlap)]
            buf_tokens = len(overlap)
            # next chunk continues from same end page
            page_start = page_end
        else:
            buf = []
            buf_tokens = 0
            page_start = None

    for page in pages:
        pno = page.get("page_number")
        ptext = normalize(page.get("text", ""))

        if not ptext:
            continue

        paragraphs = split_to_paragraphs(ptext)
        cur_section = detect_section(paragraphs, cur_section)

        # track pages included
        if page_start is None:
            page_start = pno
        page_end = pno

        for para in paragraphs:
            para = normalize(para)
            if not para:
                continue

            para_tokens = count_tokens(para)

            # If single paragraph is huge, split by sentences
            if para_tokens > MAX_TOKENS:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                for s in sentences:
                    s = normalize(s)
                    if not s:
                        continue
                    s_tokens = count_tokens(s)

                    if buf_tokens + s_tokens > MAX_TOKENS and buf_tokens >= MIN_TOKENS:
                        flush_chunk()

                    buf.append(s)
                    buf_tokens += s_tokens
                continue

            # Normal paragraph
            if buf_tokens + para_tokens > MAX_TOKENS and buf_tokens >= MIN_TOKENS:
                flush_chunk()

            buf.append(para)
            buf_tokens += para_tokens

            # if we are above target, flush (nice chunk size)
            if buf_tokens >= TARGET_TOKENS:
                flush_chunk()

    # flush remaining buffer
    if buf_tokens >= 120:
        # disable overlap for final flush
        global OVERLAP_TOKENS
        old_overlap = OVERLAP_TOKENS
        OVERLAP_TOKENS = 0
        flush_chunk()
        OVERLAP_TOKENS = old_overlap

    return chunks

def write_jsonl(path: Path, rows: List[Dict[str, Any]]):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def main():
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    files = list(TEXT_DIR.glob("*.json"))

    if not files:
        print("❌ No extracted text JSON files found in:", TEXT_DIR)
        return

    for fp in files:
        source_name = fp.stem  # e.g., Pub463_2024
        with open(fp, "r", encoding="utf-8") as f:
            pages = json.load(f)

        chunks = build_chunks(pages, source_name)

        out = CHUNKS_DIR / f"{source_name}.jsonl"
        write_jsonl(out, chunks)

        print(f"✅ {source_name}: pages={len(pages)} chunks={len(chunks)} -> {out.name}")

    print("✅ Chunking complete.")

if __name__ == "__main__":
    main()