from google import genai
import json
from dotenv import load_dotenv
import os
import sys
from pathlib import Path
from google.genai import types
import faiss
import numpy as np
from ...config import EMBEDDING_MODEL

load_dotenv()

# Initializing the vector store
dimension = 2048  # dimension of the embedding
index = faiss.IndexFlatIP(dimension)

try:
    api_key = os.getenv("GEMINI_API_KEY")
except Exception as e:
    print(f"No Google API key found: {e}")
    sys.exit()

INPUT_DIR = Path("./rag_chunks")
METADATA_FILE = Path("../tool_utils/sql_tool_utils/metadata.json")
meta_data = []

client = genai.Client(api_key=api_key)

# Embedding each file in the rag_chunks  and storing it in the vector store
for file in os.listdir(INPUT_DIR):
    if file.endswith(".json"):
        file_path = os.path.join(INPUT_DIR, file)
        with open(file_path, "r") as f:
            data = json.load(f)
            text = json.dumps(data)
            result = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=2048),
            )
            embeddings = []
            for emb_obj in result.embeddings:
                embeddings.append(emb_obj.values)

            # Storing all the json files content in the metadata list
            meta_data.append(data)
            embedding = np.array(embeddings, dtype="float32")
            faiss.normalize_L2(embedding)
            index.add(embedding)

# Creating the metadata.json file with the contents from all the files
with open(METADATA_FILE, "w", encoding="utf-8") as f:
    json.dump(meta_data, f, indent=2, ensure_ascii=False)

# Storing the vector store
faiss.write_index(index, "../tool_utils/sql_tool_utils/my_faiss_index.faiss")
print("my_faiss_index.faiss is created")
