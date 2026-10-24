import json
import os
import threading
from pathlib import Path

import faiss
import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

from config import EMBEDDING_MODEL
from src.sql_tool_utils.sql_rag_chunker import chunk_all_documents

load_dotenv(".env")

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "internal_doc_index.faiss"
METADATA_FILE = BASE_DIR / "internal_doc_metadata.json"

_thread_local = threading.local()


def _get_client():
    if not hasattr(_thread_local, "client"):
        _thread_local.client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _thread_local.client


def _embed_text(text: str) -> np.ndarray:
    result = _get_client().models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=2048),
    )
    vector = np.array(result.embeddings[0].values, dtype="float32").reshape(1, -1)
    faiss.normalize_L2(vector)
    return vector


def _chunk_text(chunk: dict) -> str:
    return f"{chunk.get('filename', '')}\n{chunk.get('heading', '')}\n{chunk.get('content', '')}".strip()


def build_internal_doc_index() -> int:
    chunks = chunk_all_documents()
    if not chunks:
        raise ValueError("No chunks generated for SQL internal docs.")

    vectors = np.vstack([_embed_text(_chunk_text(chunk)) for chunk in chunks])
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)

    faiss.write_index(index, str(INDEX_FILE))
    METADATA_FILE.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return len(chunks)


def fetch_internal_doc_chunks(user_query: str, k: int = 5) -> list[dict]:
    if not INDEX_FILE.exists() or not METADATA_FILE.exists():
        raise FileNotFoundError(
            "Internal SQL doc index not found. Run: python -m src.sql_tool_utils.sql_rag_embed"
        )

    index = faiss.read_index(str(INDEX_FILE))
    metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    scores, ids = index.search(_embed_text(user_query), k)

    return [
        {
            "score": float(scores[0][rank]),
            "chunk": metadata[int(idx)],
        }
        for rank, idx in enumerate(ids[0])
        if int(idx) != -1
    ]


if __name__ == "__main__":
    total = build_internal_doc_index()
    print(f"Built SQL internal doc index with {total} chunks")
