import json
import sqlite3
import uuid
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional
from config import (
    CLOUD_SQL_CONNECTION_NAME, DATABASE_URL, DB_CONNECT_TIMEOUT, DB_HOST, DB_NAME,
    DB_PASSWORD, DB_POOL_MAX_SIZE, DB_POOL_MIN_SIZE, DB_PORT, DB_USER,
    SOLVIQUE_DATA_DIR, STORAGE_BACKEND,
)
from src.logging_config import get_logger

logger = get_logger(__name__)


DATA_DIR = SOLVIQUE_DATA_DIR
_new_db_path = DATA_DIR / "solvique_conversations.db"
_legacy_db_path = DATA_DIR / "uqe_conversations.db"
# Keep existing conversations available during the filename migration.
DB_PATH = _new_db_path if _new_db_path.exists() or not _legacy_db_path.exists() else _legacy_db_path
_db_initialized = False
_init_lock = threading.RLock()
_postgres_pool = None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id                TEXT PRIMARY KEY,
    conversation_id   TEXT NOT NULL,
    role              TEXT NOT NULL,
    content           TEXT,
    tool              TEXT,
    sql_query         TEXT,
    results_json      TEXT,
    citations_json    TEXT,
    doc_citations_json    TEXT,
    web_citations_json    TEXT,
    chart_specs_json  TEXT,
    metadata_json     TEXT,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
    ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS report_assets (
    id                TEXT PRIMARY KEY,
    conversation_id   TEXT NOT NULL,
    message_id        TEXT NOT NULL,
    object_path       TEXT NOT NULL UNIQUE,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

CREATE INDEX IF NOT EXISTS idx_report_assets_conversation_created
    ON report_assets(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_report_assets_message
    ON report_assets(message_id);
"""


def utc_now() -> str:
    return datetime.utcnow().isoformat()


def json_dumps(value: Any) -> Optional[str]:
    return json.dumps(value, default=str) if value is not None else None


def json_loads(value: Optional[str]) -> Any:
    try:
        return json.loads(value) if value else None
    except json.JSONDecodeError:
        return value


@contextmanager
def db_connection():
    if STORAGE_BACKEND == "postgres":
        pool = _get_postgres_pool()
        with pool.connection() as raw_conn:
            yield _PostgresConnection(raw_conn)
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


class _PostgresConnection:
    """Small DB-API adapter preserving the store's existing qmark queries."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        return self.connection.execute(query.replace("?", "%s"), params)


def _get_postgres_pool():
    global _postgres_pool
    if _postgres_pool is None:
        with _init_lock:
            if _postgres_pool is None:
                try:
                    from psycopg.rows import dict_row
                    from psycopg_pool import ConnectionPool
                except ImportError as exc:
                    raise RuntimeError("PostgreSQL storage requires psycopg and psycopg-pool") from exc

                if DATABASE_URL:
                    conninfo = DATABASE_URL
                else:
                    if not (DB_NAME and DB_USER):
                        raise RuntimeError(
                            "PostgreSQL storage requires DATABASE_URL or DB_NAME and DB_USER"
                        )
                    host = DB_HOST
                    if CLOUD_SQL_CONNECTION_NAME:
                        host = f"/cloudsql/{CLOUD_SQL_CONNECTION_NAME}"
                    if not host:
                        raise RuntimeError(
                            "Set DB_HOST or CLOUD_SQL_CONNECTION_NAME for PostgreSQL storage"
                        )
                    values = {"host": host, "port": DB_PORT, "dbname": DB_NAME, "user": DB_USER}
                    if DB_PASSWORD:
                        values["password"] = DB_PASSWORD
                    values["connect_timeout"] = DB_CONNECT_TIMEOUT
                    from psycopg.conninfo import make_conninfo
                    conninfo = make_conninfo(**values)
                _postgres_pool = ConnectionPool(
                    conninfo=conninfo,
                    min_size=DB_POOL_MIN_SIZE,
                    max_size=DB_POOL_MAX_SIZE,
                    timeout=DB_CONNECT_TIMEOUT,
                    kwargs={"row_factory": dict_row},
                    open=True,
                )
    return _postgres_pool


def close_db() -> None:
    """Close the process-local pool during application shutdown."""
    global _postgres_pool, _db_initialized
    if _postgres_pool is not None:
        _postgres_pool.close()
        _postgres_pool = None
    _db_initialized = False


def init_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    with _init_lock:
        if _db_initialized:
            return
        with db_connection() as conn:
            if STORAGE_BACKEND == "postgres":
                # Serialize first-run DDL across simultaneously starting Cloud Run instances.
                conn.execute("SELECT pg_advisory_xact_lock(hashtext('solvique_storage_schema_v1'))")
                for statement in SCHEMA_SQL.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                logger.info("PostgreSQL conversation schema initialized")
            else:
                conn.executescript(SCHEMA_SQL)
                logger.info("Conversation database initialized at %s", DB_PATH)
        _db_initialized = True


def _row_dict(row: sqlite3.Row, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: row[field] for field in fields}


def message_row_to_api(row: sqlite3.Row) -> dict[str, Any]:
    return {
        **_row_dict(row, ("id", "role", "tool", "sql_query", "created_at")),
        "content": row["content"] or "",
        "dataframe": json_loads(row["results_json"]),
        "citations": json_loads(row["citations_json"]),
        "doc_citations": json_loads(row["doc_citations_json"]),  # ← add
        "web_citations": json_loads(row["web_citations_json"]),  # ← add
        "chart_specs": json_loads(row["chart_specs_json"]),
        "metadata": json_loads(row["metadata_json"]),
    }


def report_asset_row_to_api(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def ensure_conversation(
    conversation_id: Optional[str], first_message: Optional[str] = None
) -> dict[str, Any]:
    init_db()
    conv_id = conversation_id or str(uuid.uuid4())
    now = utc_now()
    with db_connection() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
        if row:
            return dict(row)

        title = (first_message or "New conversation").strip()[:60] or "New conversation"
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
            (conv_id, title, now, now),
        )
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
        if row:
            return dict(row)
    return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}


def touch_conversation(conversation_id: str, title: Optional[str] = None) -> None:
    with db_connection() as conn:
        clean_title = title.strip()[:60] if title else None
        if clean_title:
            conn.execute(
                """
                UPDATE conversations
                SET updated_at = ?, title = ?
                WHERE id = ?
                """,
                (utc_now(), clean_title, conversation_id),
            )
        else:
            conn.execute(
                """
                UPDATE conversations
                SET updated_at = ?
                WHERE id = ?
                """,
                (utc_now(), conversation_id),
            )


def add_message(
    *,
    conversation_id: str,
    role: str,
    content: Optional[str],
    tool: Optional[str] = None,
    sql_query: Optional[str] = None,
    results: Any = None,
    citations: Any = None,
    doc_citations: Any = None,  # ← add
    web_citations: Any = None,  # ← add
    chart_specs: Any = None,
    metadata: Any = None,
) -> dict[str, Any]:
    init_db()
    message_id, now = str(uuid.uuid4()), utc_now()
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO messages (
                id, conversation_id, role, content, tool, sql_query,
                results_json, citations_json, doc_citations_json, web_citations_json, chart_specs_json, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conversation_id,
                role,
                content,
                tool,
                sql_query,
                json_dumps(results),
                json_dumps(citations),
                json_dumps(doc_citations),  # ← add
                json_dumps(web_citations),
                json_dumps(chart_specs),
                json_dumps(metadata),
                now,
            ),
        )
        logger.info(
            "Message saved: conversation_id=%s, message_id=%s, role=%s, tool=%s",
            conversation_id,
            message_id,
            role,
            tool,
        )

    touch_conversation(conversation_id)
    return {
        "id": message_id,
        "role": role,
        "content": content or "",
        "tool": tool,
        "sql_query": sql_query,
        "dataframe": results,
        "citations": citations,
        "doc_citations": doc_citations,  # ← add
        "web_citations": web_citations,
        "chart_specs": chart_specs,
        "metadata": metadata,
        "created_at": now,
        "conversation_id": conversation_id,
    }


def list_conversations() -> list[dict[str, Any]]:
    init_db()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        logger.debug("Listed conversations: count=%s", len(rows))
    return [
        {"id": row["id"], "title": row["title"], "created": row["created_at"]}
        for row in rows
    ]


def get_conversation(conversation_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with db_connection() as conn:
        conv = conn.execute(
            "SELECT id, title, created_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if not conv:
            return None
        messages = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, id ASC",
            (conversation_id,),
        ).fetchall()
    logger.debug(
        "Retrieved conversation: conversation_id=%s, message_count=%s",
        conversation_id,
        len(messages),
    )
    return {
        "id": conv["id"],
        "created": conv["created_at"],
        "messages": [message_row_to_api(row) for row in messages],
    }


def get_recent_messages(conversation_id: str, limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
        logger.debug(
            "Retrieved recent messages: conversation_id=%s, count=%s",
            conversation_id,
            len(rows),
        )
    return [message_row_to_api(row) for row in reversed(rows)]


def get_message_by_id(message_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        logger.debug("Retrieved message: message_id=%s", message_id)
    if not row:
        return None
    return {**message_row_to_api(row), "conversation_id": row["conversation_id"]}


def delete_conversation(conversation_id: str) -> bool:
    init_db()
    with db_connection() as conn:
        if not conn.execute(
            "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone():
            return False
        for table in ("report_assets", "messages", "conversations"):
            conn.execute(
                f"DELETE FROM {table} WHERE {'id' if table == 'conversations' else 'conversation_id'} = ?",
                (conversation_id,),
            )
    logger.info("Conversation deleted: conversation_id=%s", conversation_id)
    return True


def update_message_visualization(
    *,
    message_id: str,
    chart_specs: Any,
    metadata_updates: dict[str, Any] | None = None,
) -> Optional[dict[str, Any]]:
    init_db()
    with db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        if not row:
            return None

        metadata = {
            **(json_loads(row["metadata_json"]) or {}),
            **(metadata_updates or {}),
        }
        conn.execute(
            "UPDATE messages SET chart_specs_json = ?, metadata_json = ? WHERE id = ?",
            (json_dumps(chart_specs), json_dumps(metadata), message_id),
        )
        logger.info(
            "Message visualization updated: message_id=%s, chart_specs_updated=%s, metadata_updates=%s",
            message_id,
            bool(chart_specs),
            bool(metadata_updates),
        )
    return get_message_by_id(message_id)


def update_message_metadata(
    *,
    message_id: str,
    metadata: dict[str, Any],
) -> Optional[dict[str, Any]]:
    init_db()
    with db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        if not row:
            return None

        conn.execute(
            "UPDATE messages SET metadata_json = ? WHERE id = ?",
            (json_dumps(metadata), message_id),
        )
        logger.info(
            "Message metadata updated: message_id=%s, metadata_updated=%s",
            message_id,
            bool(metadata),
        )
    return get_message_by_id(message_id)


def add_report_asset(
    *,
    id: str,
    conversation_id: str,
    message_id: str,
    object_path: str,
) -> dict[str, Any]:
    init_db()
    now = utc_now()
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO report_assets (
                id, conversation_id, message_id, object_path, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                id,
                conversation_id,
                message_id,
                object_path,
                now,
            ),
        )
        logger.info(
            "Report asset saved: asset_id=%s, conversation_id=%s, message_id=%s",
            id,
            conversation_id,
            message_id,
        )
    return {
        "id": id,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "object_path": object_path,
        "created_at": now,
    }


def list_report_assets(conversation_id: str) -> list[dict[str, Any]]:
    init_db()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM report_assets WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        logger.debug(
            "Listed report assets: conversation_id=%s, count=%s",
            conversation_id,
            len(rows),
        )
    return [report_asset_row_to_api(row) for row in rows]


def get_report_asset(asset_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM report_assets WHERE id = ?", (asset_id,)
        ).fetchone()
        logger.debug("Retrieved report asset: asset_id=%s", asset_id)
    return report_asset_row_to_api(row) if row else None


def delete_report_assets_for_message(message_id: str) -> list[str]:
    init_db()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT object_path FROM report_assets WHERE message_id = ?", (message_id,)
        ).fetchall()
        conn.execute("DELETE FROM report_assets WHERE message_id = ?", (message_id,))
        logger.info(
            "Deleted report assets for message: message_id=%s, count=%s",
            message_id,
            len(rows),
        )
    return [row["object_path"] for row in rows]


def list_report_asset_paths_for_conversation(conversation_id: str) -> list[str]:
    init_db()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT object_path FROM report_assets WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchall()
    logger.debug(
        "Listed report asset paths for conversation: conversation_id=%s, count=%s",
        conversation_id,
        len(rows),
    )
    return [row["object_path"] for row in rows]
