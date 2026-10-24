from google import genai
from google.genai import types
from dotenv import load_dotenv
from pathlib import Path

import faiss
import json
import numpy as np
import os
import sys

from config import EMBEDDING_MODEL

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "chunks"
METADATA_FILE = BASE_DIR / "metadata.json"
INDEX_FILE = BASE_DIR / "my_faiss_index.faiss"


DIMENSION = 2048  # dimension of the embedding


def chunk_to_embedding_text(chunk: dict) -> str:
    return (
        f"Filename: {chunk.get('filename', '')}\n"
        f"Filetype: {chunk.get('filetype', '')}\n"
        f"Chunk: {chunk.get('chunk_no', '')} of {chunk.get('total_chunks', '')}\n"
        f"Heading: {chunk.get('heading', '')}\n\n"
        f"{chunk.get('content', '')}"
    )


def load_chunks() -> list[dict]:
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"Chunks directory not found: {INPUT_DIR}")

    chunks = []

    for file_path in sorted(INPUT_DIR.glob("*.json")):
        with file_path.open("r", encoding="utf-8") as file:
            chunks.append(json.load(file))

    return chunks


def main() -> None:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("No GOOGLE_API_KEY or GEMINI_API_KEY found.")
        sys.exit(1)

    chunks = load_chunks()

    if not chunks:
        print(f"No chunk JSON files found in: {INPUT_DIR}")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    index = faiss.IndexFlatIP(DIMENSION)
    metadata = []

    for chunk in chunks:
        text = chunk_to_embedding_text(chunk)

        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=DIMENSION),
        )

        embedding = np.array(
            [result.embeddings[0].values],
            dtype="float32",
        )

        faiss.normalize_L2(embedding)
        index.add(embedding)
        metadata.append(chunk)

    METADATA_FILE.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    faiss.write_index(index, str(INDEX_FILE))

    print(f"Embedded {len(metadata)} chunks")
    print(f"Metadata saved: {METADATA_FILE}")
    print(f"Index saved: {INDEX_FILE}")


if __name__ == "__main__":
    main()
