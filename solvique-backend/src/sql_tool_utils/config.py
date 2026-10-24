import os
from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
METADATA_FILE = os.path.join(_BASE_DIR, "metadata.json")
INDEX = os.path.join(_BASE_DIR, "my_faiss_index.faiss")

# BigQuery Configuration
project_id = os.getenv("big_query_project_id") or os.getenv("GOOGLE_CLOUD_PROJECT", "solvique-personal")
dataset = os.getenv("big_query_dataset", "ecommerce")
