"""Chroma retrieval and Ollama embeddings. No cloud API is used."""
from __future__ import annotations

from typing import Sequence

import chromadb
import ollama

from config import CHROMA_PATH, COLLECTION_NAME, EMBEDDING_MODEL, OLLAMA_HOST


def ollama_client() -> ollama.Client:
    return ollama.Client(host=OLLAMA_HOST)


def embed(texts: Sequence[str]) -> list[list[float]]:
    """Embed a batch using the model installed in the local Ollama server."""
    response = ollama_client().embed(model=EMBEDDING_MODEL, input=list(texts))
    return response["embeddings"]


def collection():
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return client.get_or_create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def retrieve(query: str, top_k: int) -> list[dict]:
    db = collection()
    if db.count() == 0:
        raise RuntimeError("The knowledge base is empty. Put PDFs in data/books and run ingest_books.py.")
    result = db.query(query_embeddings=embed([query]), n_results=min(top_k, db.count()), include=["documents", "metadatas", "distances"])
    sources = []
    for doc, metadata, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
        sources.append({"text": doc, "source": metadata["source"], "page": metadata["page"], "chunk": metadata["chunk"], "distance": round(float(distance), 4)})
    return sources
