import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Conversation and report storage are selected independently so local development
# remains self contained while Cloud Run can use Cloud SQL and Cloud Storage.
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "sqlite").strip().lower()
REPORT_ASSET_BACKEND = os.getenv("REPORT_ASSET_BACKEND", "local").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or None
CLOUD_SQL_CONNECTION_NAME = os.getenv("CLOUD_SQL_CONNECTION_NAME", "").strip() or None
DB_NAME = os.getenv("DB_NAME", "").strip() or None
DB_USER = os.getenv("DB_USER", "").strip() or None
DB_PASSWORD = os.getenv("DB_PASSWORD", "").strip() or None
DB_HOST = os.getenv("DB_HOST", "").strip() or None
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "5"))
DB_CONNECT_TIMEOUT = float(os.getenv("DB_CONNECT_TIMEOUT", "10"))
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")


def validate_storage_configuration(values: dict[str, str] | None = None) -> None:
    if values is None:
        values = os.environ
    production = bool(values.get("K_SERVICE"))
    if production and not values.get("STORAGE_BACKEND"):
        raise RuntimeError("Set STORAGE_BACKEND explicitly for Cloud Run")
    if production and not values.get("REPORT_ASSET_BACKEND"):
        raise RuntimeError("Set REPORT_ASSET_BACKEND explicitly for Cloud Run")

    storage = values.get("STORAGE_BACKEND", "sqlite").strip().lower()
    assets = values.get("REPORT_ASSET_BACKEND", "local").strip().lower()
    if storage not in {"sqlite", "postgres"}:
        raise ValueError("STORAGE_BACKEND must be 'sqlite' or 'postgres'")
    if assets not in {"local", "gcs"}:
        raise ValueError("REPORT_ASSET_BACKEND must be 'local' or 'gcs'")
    if storage == "postgres":
        if not values.get("DATABASE_URL"):
            if not (values.get("DB_NAME") and values.get("DB_USER")):
                raise RuntimeError("PostgreSQL requires DATABASE_URL or DB_NAME and DB_USER")
            if not (values.get("DB_HOST") or values.get("CLOUD_SQL_CONNECTION_NAME")):
                raise RuntimeError("PostgreSQL requires DB_HOST or CLOUD_SQL_CONNECTION_NAME")
    if assets == "gcs" and not values.get("GCS_BUCKET_NAME"):
        raise RuntimeError("GCS report storage requires GCS_BUCKET_NAME")
    pool_min = int(values.get("DB_POOL_MIN_SIZE", "1"))
    pool_max = int(values.get("DB_POOL_MAX_SIZE", "5"))
    if pool_min < 0 or pool_max < 1 or pool_min > pool_max:
        raise ValueError("Database pool sizes must satisfy 0 <= min <= max and max >= 1")


validate_storage_configuration()

# Anchor base directory to this backend package directory
_BASE_DIR = Path(__file__).resolve().parent

# LLM & Embedding Models
MODEL = os.getenv("MODEL", "gemini-2.5-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")

# BigQuery & GCP Configuration
BIGQUERY_PROJECT_ID = os.getenv("big_query_project_id") or os.getenv("GOOGLE_CLOUD_PROJECT", "solvique-personal")
BIGQUERY_DATASET = os.getenv("big_query_dataset", "ecommerce")

# Web Search
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Application Data & Report Asset Directories
# Stable resolution: Relative paths always resolve against _BASE_DIR, not cwd.
_raw_data_dir = os.getenv("SOLVIQUE_DATA_DIR") or os.getenv("UQE_DATA_DIR") or "data"
_data_path = Path(_raw_data_dir)
SOLVIQUE_DATA_DIR = _data_path.resolve() if _data_path.is_absolute() else (_BASE_DIR / _data_path).resolve()

_raw_report_root = os.getenv("REPORT_ASSET_ROOT")
if _raw_report_root:
    _p = Path(_raw_report_root)
    REPORT_ASSET_ROOT = _p.resolve() if _p.is_absolute() else (_BASE_DIR / _p).resolve()
else:
    REPORT_ASSET_ROOT = (SOLVIQUE_DATA_DIR / "report_assets").resolve()

_raw_log_path = os.getenv("LOG_FILE_PATH", "logs/app.log")
_log_p = Path(_raw_log_path)
LOG_FILE_PATH: str = str(_log_p.resolve() if _log_p.is_absolute() else (_BASE_DIR / _log_p).resolve())
