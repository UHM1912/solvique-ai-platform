from types import ModuleType, SimpleNamespace
import shutil
import uuid
from pathlib import Path

import pytest

from config import validate_storage_configuration
import src.conversation_store as store
from src.services.report_service import get_report_asset_or_404
from src.reporting.report_files import (
    ChartAssetService,
    GCSReportAssetStorage,
    LocalReportAssetStorage,
)


@pytest.fixture
def tmp_path():
    # The managed host's system temp directory is inaccessible to this checkout.
    path = Path.cwd() / f".storage-test-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


@pytest.fixture
def sqlite_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(store, "_db_initialized", False)
    yield
    monkeypatch.setattr(store, "_db_initialized", False)


def test_conversation_crud_and_message_order(sqlite_store):
    conv = store.ensure_conversation("conversation-1", "A useful first question")
    assert conv["title"] == "A useful first question"
    first = store.add_message(conversation_id=conv["id"], role="user", content="hello")
    second = store.add_message(
        conversation_id=conv["id"], role="assistant", content="world", results=[{"n": 1}]
    )

    detail = store.get_conversation(conv["id"])
    assert [message["id"] for message in detail["messages"]] == [first["id"], second["id"]]
    assert detail["messages"][1]["dataframe"] == [{"n": 1}]
    assert store.list_conversations()[0]["id"] == conv["id"]
    assert store.delete_conversation(conv["id"]) is True
    assert store.get_conversation(conv["id"]) is None
    assert store.delete_conversation(conv["id"]) is False


def test_sqlite_transaction_rolls_back_on_error(sqlite_store):
    store.init_db()
    with pytest.raises(RuntimeError):
        with store.db_connection() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                ("rolled-back", "test", "now", "now"),
            )
            raise RuntimeError("abort transaction")
    assert store.get_conversation("rolled-back") is None


def test_postgres_adapter_preserves_parameterized_query_values():
    class Connection:
        query = None
        params = None

        def execute(self, query, params):
            self.query, self.params = query, params
            return "cursor"

    connection = Connection()
    adapter = store._PostgresConnection(connection)
    assert adapter.execute("SELECT * FROM messages WHERE id = ?", ("safe",)) == "cursor"
    assert connection.query == "SELECT * FROM messages WHERE id = %s"
    assert connection.params == ("safe",)


def test_local_asset_storage_rejects_traversal_and_reads(tmp_path):
    storage = LocalReportAssetStorage(tmp_path / "assets")
    key = storage.save_bytes(b"image-data", "conversation/message/asset.png")
    assert storage.read_bytes(key) == b"image-data"
    with pytest.raises(ValueError):
        storage.save_bytes(b"bad", "../escape.png")
    with pytest.raises(ValueError):
        storage.read_bytes("../../secret")


def test_gcs_asset_storage_upload_read_delete_and_missing(monkeypatch):
    class Missing(Exception):
        pass

    class Blob:
        def __init__(self, name, bucket):
            self.name, self.bucket = name, bucket

        def upload_from_string(self, data, content_type):
            self.bucket.objects[self.name] = data

        def download_as_bytes(self):
            if self.name not in self.bucket.objects:
                raise Missing()
            return self.bucket.objects[self.name]

        def delete(self):
            if self.name not in self.bucket.objects:
                raise Missing()
            del self.bucket.objects[self.name]

    class Bucket:
        objects = {}

        def blob(self, name):
            return Blob(name, self)

    bucket = Bucket()
    fake_storage = SimpleNamespace(Client=lambda: SimpleNamespace(bucket=lambda _: bucket))
    google = ModuleType("google")
    cloud = ModuleType("google.cloud")
    api_core = ModuleType("google.api_core")
    exceptions = ModuleType("google.api_core.exceptions")
    cloud.storage = fake_storage
    exceptions.NotFound = Missing
    api_core.exceptions = exceptions
    google.cloud = cloud
    for name, module in (("google", google), ("google.cloud", cloud),
                         ("google.api_core", api_core),
                         ("google.api_core.exceptions", exceptions)):
        monkeypatch.setitem(__import__("sys").modules, name, module)

    storage = GCSReportAssetStorage("private-bucket")
    key = storage.save_bytes(b"png", "a/b/asset.png")
    assert storage.read_bytes(key) == b"png"
    with pytest.raises(FileNotFoundError):
        storage.read_bytes("absent.png")
    with pytest.raises(ValueError):
        storage.save_bytes(b"bad", "a/../secret")
    storage.delete_object(key)
    assert key not in bucket.objects


def test_chart_generation_records_persistent_object_reference(monkeypatch):
    captured = {}

    class Storage:
        def save_bytes(self, data, object_path):
            captured["bytes"] = data
            captured["path"] = object_path
            return object_path

    monkeypatch.setattr("src.reporting.report_files.pio.to_image", lambda *args, **kwargs: b"png")
    monkeypatch.setattr(
        "src.reporting.report_files.add_report_asset",
        lambda **fields: fields,
    )
    service = ChartAssetService(Storage())
    result = service.create_chart_asset(
        conversation_id="conversation-1",
        message_id="message-1",
        figure_json='{"data": [], "layout": {}}',
    )
    assert captured["bytes"] == b"png"
    assert result["object_path"].endswith(f"/{result['id']}.png")
    assert captured["path"] == result["object_path"]


def test_invalid_asset_id_is_rejected_before_database_lookup():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        get_report_asset_or_404("../../secret")
    assert error.value.status_code == 400


def test_production_storage_configuration_validation():
    with pytest.raises(RuntimeError, match="STORAGE_BACKEND"):
        validate_storage_configuration({"K_SERVICE": "api"})
    with pytest.raises(RuntimeError, match="GCS_BUCKET_NAME"):
        validate_storage_configuration({
            "K_SERVICE": "api",
            "STORAGE_BACKEND": "postgres",
            "REPORT_ASSET_BACKEND": "gcs",
            "DATABASE_URL": "postgresql://example",
        })
    validate_storage_configuration({
        "K_SERVICE": "api",
        "STORAGE_BACKEND": "postgres",
        "REPORT_ASSET_BACKEND": "gcs",
        "DATABASE_URL": "postgresql://example",
        "GCS_BUCKET_NAME": "private-bucket",
    })

