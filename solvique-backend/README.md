# Solvique Backend

FastAPI backend for Solvique analytics, including SQL and document retrieval,
machine learning inference, visualizations, and generated reports.

## Run locally

Install the project dependencies with `python -m pip install .`, configure the
environment variables described in `.env.example`, then run:

```powershell
uvicorn api:app --host 0.0.0.0 --port 8080
```

The API exposes health checks at `/health` and `/api/health`. Cloud Run supplies
the listening port through `PORT`.

## Runtime storage

Local development defaults to SQLite and filesystem assets. Cloud Run can use
Cloud SQL for conversations and a private GCS bucket for report images, as
described in [Persistent storage configuration](#persistent-storage-configuration).

## Configuration

See `.env.example` for configuration variable names. In production, provide
Gemini credentials through `GOOGLE_API_KEY` and use the Cloud Run service
identity for Google Cloud APIs such as BigQuery.
# Persistent storage configuration

Local development defaults to `STORAGE_BACKEND=sqlite` and
`REPORT_ASSET_BACKEND=local`. The SQLite database and local report assets use
`SOLVIQUE_DATA_DIR` and `REPORT_ASSET_ROOT` as before.

For Cloud Run, set `STORAGE_BACKEND=postgres` and
`REPORT_ASSET_BACKEND=gcs`. Configure PostgreSQL with either `DATABASE_URL`, or
`DB_NAME`, `DB_USER`, optional `DB_PASSWORD`, and `DB_HOST`/`DB_PORT`. For Cloud
SQL, attach the instance to the Cloud Run service and set
`CLOUD_SQL_CONNECTION_NAME=PROJECT:REGION:INSTANCE`; the app connects through
`/cloudsql/PROJECT:REGION:INSTANCE`. Do not put credentials in the image or
source control. Supply secrets through Secret Manager-backed environment
variables. Pool controls are `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE`, and
`DB_CONNECT_TIMEOUT`.

The application initializes the idempotent schema on startup. The PostgreSQL
database user needs `CONNECT`, schema `USAGE`, and `CREATE` for the schema on
first startup, plus `SELECT`, `INSERT`, `UPDATE`, and `DELETE` on the three
storage tables after creation. A separate migration role can create the schema
and grant table privileges to a narrower runtime role.

Set `GCS_BUCKET_NAME` to an existing private bucket. The Cloud Run service
identity needs object create, read, and delete permissions for report asset
objects. The bucket remains private and access uses Application Default
Credentials. This code does not create cloud resources or change IAM.

Existing SQLite conversations are not automatically copied into PostgreSQL.
Before switching an environment that already contains conversation data,
export/import the `conversations`, `messages`, and `report_assets` rows and copy
referenced report objects to the configured bucket while preserving each
`object_path`. The initial PostgreSQL schema is created automatically; data
migration and live Cloud SQL/GCS integration checks remain deployment steps.
