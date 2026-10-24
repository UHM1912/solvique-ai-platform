from src.logging_config.logger import get_logger
import os
from time import perf_counter
import json
import numpy as np
import faiss
from dotenv import load_dotenv
from google import genai
from google.genai import types
from .config import METADATA_FILE
from config import EMBEDDING_MODEL

load_dotenv(".env")

logger = get_logger(__name__)

import threading

_thread_local = threading.local()


def get_embedding_client():
    if not hasattr(_thread_local, "client"):
        _thread_local.client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _thread_local.client


def load_model():
    if not os.environ.get("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY is required for Gemini schema retrieval.")

    try:
        start = perf_counter()
        # Loading the faiss index — resolve relative to this file's directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        loaded_index = faiss.read_index(os.path.join(base_dir, "my_faiss_index.faiss"))
        end = perf_counter()
        time_elapsed = end - start
        logger.info(
            f"SQL tool: Index loaded. Total vectors in index: {loaded_index.ntotal}. Execution duration: {time_elapsed} seconds."
        )
    except Exception as e:
        logger.warning(f"SQL tool: Error while loading the vector store: {e}")
        raise RuntimeError("Could not load SQL schema vector store.") from e

    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            _metadata = json.load(f)

        logger.info("SQL tool: Metadata file of the sql tool is loaded")

    except Exception as e:
        logger.warning(f'SQL tool: Couldn"t load metadata file: {e}')
        raise RuntimeError("Could not load SQL schema metadata.") from e

    return loaded_index, _metadata


def get_schema(index, metadata, prompt, k=8):

    try:
        start = perf_counter()
        client = get_embedding_client()  # each thread gets its own client
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=prompt,
            config=types.EmbedContentConfig(output_dimensionality=2048),
        )
        logger.info("SQL tool: User prompt is embedded.")

    except Exception as e:
        logger.warning(
            f"SQL tool: Exception ocurred while embedding the user prompt: {e}"
        )
        raise RuntimeError("Could not embed the SQL schema query.") from e

    embeded_prompt = np.array(result.embeddings[0].values, dtype="float32").reshape(
        1, -1
    )

    faiss.normalize_L2(embeded_prompt)

    scores, ids = index.search(embeded_prompt, k)
    end = perf_counter()
    time_elapsed = end - start

    logger.info("SQL tool: Schema vector store returned relevant schemas.")
    logger.info(
        f"SQL tool: Embedding and vector store search done. Execution duration: {time_elapsed} seconds."
    )

    results = []
    for rank, idx in enumerate(ids[0]):
        if int(idx) == -1:
            continue
        results.append(
            {"score": float(scores[0][rank]), "metadata": metadata[int(idx)]}
        )
    return results


def fetch_tables_schema(user_query: str):
    """Use this tool to get schema of tables in the database."""

    logger.info("SQL tool: Table schema fetching tool invoked.")

    index, metadata = load_model()

    results = get_schema(index, metadata, user_query)

    logger.info("SQL tool: Schemas have been fetched.")

    return results
