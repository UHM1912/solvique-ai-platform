import json
import logging
import os
import threading
from time import perf_counter

import faiss
import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

from config import EMBEDDING_MODEL


load_dotenv(".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_INDEX_FILE = os.path.join(_BASE_DIR, "my_faiss_index.faiss")
_META_FILE = os.path.join(_BASE_DIR, "metadata.json")
_thread_local = threading.local()


def _get_embedding_client():
    if not hasattr(_thread_local, "client"):
        _thread_local.client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _thread_local.client


def load_index_and_metadata():
    if not os.environ.get("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY is required for Gemini document retrieval.")

    if not os.path.exists(_INDEX_FILE):
        message = f"RAG FAISS index file not found: {_INDEX_FILE}"
        logger.warning(message)
        raise FileNotFoundError(message)

    try:
        start = perf_counter()
        index = faiss.read_index(_INDEX_FILE)
        logger.info(
            f"RAG tool: FAISS index loaded. "
            f"Total vectors: {index.ntotal}. "
            f"Duration: {perf_counter() - start:.3f}s"
        )
    except Exception as e:
        logger.warning(f"RAG tool: Failed to load FAISS index: {e}")
        raise RuntimeError(f"Failed to load RAG FAISS index from {_INDEX_FILE}") from e

    try:
        with open(_META_FILE, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        logger.info("RAG tool: Metadata file loaded.")
    except Exception as e:
        logger.warning(f"RAG tool: Failed to load metadata file: {e}")
        raise RuntimeError(f"Failed to load RAG metadata from {_META_FILE}") from e

    return index, metadata


def get_chunks(index, metadata, prompt: str, k: int = 8):
    try:
        start = perf_counter()
        client = _get_embedding_client()
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=prompt,
            config=types.EmbedContentConfig(output_dimensionality=2048),
        )
        logger.info(
            f"RAG tool: User prompt embedded. Duration: {perf_counter() - start:.3f}s"
        )
    except Exception as e:
        logger.warning(f"RAG tool: Embedding failed: {e}")
        raise

    query_vec = np.array(result.embeddings[0].values, dtype="float32").reshape(1, -1)
    faiss.normalize_L2(query_vec)

    scores, ids = index.search(query_vec, k)
    logger.info(
        f"RAG tool: Vector search complete. Duration: {perf_counter() - start:.3f}s"
    )

    results = []
    for rank, idx in enumerate(ids[0]):
        if int(idx) == -1:
            continue
        results.append(
            {
                "score": float(scores[0][rank]),
                "chunk": metadata[int(idx)],
            }
        )

    return results


def fetch_relevant_chunks(user_query: str, k: int = 5):
    """Embed the user query and return the top-k matching document chunks."""
    index, metadata = load_index_and_metadata()
    return get_chunks(index, metadata, user_query, k=k)
