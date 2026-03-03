from pathlib import Path
from pypdf import PdfReader
import json

BACKEND_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BACKEND_DIR / "rag_sources" / "irs_2025" / "raw_pdfs"
TEXT_DIR = BACKEND_DIR / "rag_sources" / "irs_2025" / "text"

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\x00", "")
    text = text.replace("\r", "")
    return text.strip()

def extract_pdf(pdf_path: Path):
    print(f"Processing: {pdf_path.name}")
    reader = PdfReader(str(pdf_path))
    output_pages = []

    for i, page in enumerate(reader.pages):
        raw_text = page.extract_text()
        cleaned = clean_text(raw_text)

        output_pages.append({
            "source_file": pdf_path.name,
            "page_number": i + 1,
            "text": cleaned
        })

    return output_pages

def main():
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = list(RAW_DIR.glob("*.pdf"))

    if not pdf_files:
        print("No PDFs found.")
        return

    for pdf in pdf_files:
        pages = extract_pdf(pdf)

        output_file = TEXT_DIR / f"{pdf.stem}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(pages, f, indent=2)

        print(f"Saved: {output_file.name}")

    print("✅ Extraction complete.")

if __name__ == "__main__":
    main()