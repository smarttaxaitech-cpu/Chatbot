from pathlib import Path
import json
from datetime import datetime

# This file is at: backend/scripts/setup_rag_structure.py
# So backend root is one level up from this file.
BACKEND_DIR = Path(__file__).resolve().parents[1]

RAG_BASE = BACKEND_DIR / "rag_sources" / "irs_2025"
RAW_PDFS = RAG_BASE / "raw_pdfs"
TEXT_DIR = RAG_BASE / "text"
CHUNKS_DIR = RAG_BASE / "chunks"
MANIFEST_FILE = RAG_BASE / "manifest.json"

def main():
    # Create folders
    RAW_PDFS.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    # Create manifest.json if it doesn't exist
    if not MANIFEST_FILE.exists():
        manifest_data = {
            "version": "2025",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "documents": []
        }
        MANIFEST_FILE.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    print("✅ Created Layer 4 structure at:", RAG_BASE)

if __name__ == "__main__":
    main()