"""Load PDFs from data/books into the local Chroma collection."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from pypdf import PdfReader

from config import BASE_DIR, CHUNK_OVERLAP, CHUNK_SIZE
from rag import collection, embed


def chunks(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    step = CHUNK_SIZE - CHUNK_OVERLAP
    if step <= 0:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
    return [text[start : start + CHUNK_SIZE] for start in range(0, len(text), step)]


def ingest(pdf_path: Path, reset: bool = False) -> int:
    db = collection()
    if reset:
        # Re-ingesting a file replaces only chunks belonging to that file.
        try:
            db.delete(where={"source": pdf_path.name})
        except Exception:
            pass

    ids, docs, metadata = [], [], []
    reader = PdfReader(str(pdf_path))
    for page_number, page in enumerate(reader.pages, start=1):
        for chunk_number, text in enumerate(chunks(page.extract_text() or ""), start=1):
            digest = hashlib.sha1(f"{pdf_path.name}:{page_number}:{chunk_number}:{text}".encode()).hexdigest()
            ids.append(digest)
            docs.append(text)
            metadata.append({"source": pdf_path.name, "page": page_number, "chunk": chunk_number})

    for start in range(0, len(docs), 32):
        end = start + 32
        db.upsert(ids=ids[start:end], documents=docs[start:end], metadatas=metadata[start:end], embeddings=embed(docs[start:end]))
    return len(docs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="replace chunks for PDFs being ingested")
    args = parser.parse_args()
    books_dir = BASE_DIR / "data" / "books"
    pdfs = list(books_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in {books_dir}. Copy your books there first.")
    total = 0
    for pdf in pdfs:
        count = ingest(pdf, reset=args.reset)
        total += count
        print(f"Indexed {count} chunks from {pdf.name}")
    print(f"Done. Chroma now contains {collection().count()} chunks.")


if __name__ == "__main__":
    main()
