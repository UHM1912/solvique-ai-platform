# Solvique — Enterprise AI Analytics & Intelligence Platform

Solvique is an autonomous enterprise analytics and decision intelligence platform that translates natural language inquiries into validated BigQuery SQL queries, trains predictive forecasting and classification models, performs deep document RAG, and generates executive-ready visual reports.

---

## Architecture Overview

```
                      ┌────────────────────────────────────────┐
                      │          Solvique Angular UI           │
                      │  (Studio, Reports, Assistant Views)    │
                      └──────────────────┬─────────────────────┘
                                         │ HTTP REST / JSON
                                         ▼
                      ┌────────────────────────────────────────┐
                      │          Solvique Backend API          │
                      │          (FastAPI on Port 8000)        │
                      └──────────────────┬─────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
┌─────────────────┐            ┌──────────────────┐             ┌──────────────────┐
│   LangGraph     │            │    BigQuery      │             │     Prophet /    │
│ Intent Routing  │            │  Analytics DB    │             │   Scikit-Learn   │
│ (Gemini 2.5/3)  │            │(solvique-personal)             │    ML Engine     │
└─────────────────┘            └──────────────────┘             └──────────────────┘
```

---

## Directory Structure

```
.
├── UQE_BACKEND/                    # FastAPI Analytics Engine & LangGraph Agent
│   ├── api.py                      # FastAPI application definition and REST endpoints
│   ├── config.py                   # Central configuration (anchored absolute paths)
│   ├── graph.py                    # LangGraph multi-agent workflow definition
│   ├── main.py                     # Local development entry point (uvicorn)
│   ├── pyproject.toml              # Python project metadata (solvique-backend)
│   ├── Dockerfile                  # Production container definition for Cloud Run
│   ├── .dockerignore               # Container packaging exclusion rules
│   ├── .env.example                # Sanitized environment template
│   ├── data/                       # Application state, schemas, and assets
│   │   ├── schema.sql              # DDL for 8 Olist e-commerce BigQuery tables
│   │   ├── seed_data.sql           # Initial dataset verification seed records
│   │   ├── sql_rag_sources/        # Domain reference documents
│   │   ├── rag_sources/            # Client reference documents (excluded from releases)
│   │   └── solvique_conversations.db # Local conversation store (excluded from releases)
│   ├── src/                        # Modular source code
│   │   ├── logging_config/         # Standardized structured logging
│   │   ├── ml_tool_utils/          # Predictive modeling & registry
│   │   ├── rag_tool_utils/         # FAISS vector store & document chunking
│   │   ├── reporting/              # Document generator (.docx export)
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── services/               # Chat, conversation, and visualizer services
│   │   ├── sql_tool_utils/         # BigQuery SQL execution & schema embeddings
│   │   ├── tools/                  # Tool definitions for LangGraph
│   │   └── visualization_tool/     # Plotly interactive charting engine
│   └── tests/                      # Unit and integration test suites
│
├── solvique-frontend/               # Angular 19 Enterprise Web Interface
│   ├── src/                        # Angular source components, services, and styles
│   ├── package.json                # Frontend dependencies and build scripts
│   ├── Dockerfile                  # Multi-stage production container (Nginx)
│   └── nginx.conf.template         # Nginx SPA routing and Cloud Run port configuration
│
├── deploy/                         # Cloud Deployment Automation
│   ├── deploy_cloud_run.sh         # Backend deployment script (Linux / macOS / Cloud Shell)
│   ├── deploy_cloud_run.bat        # Backend deployment script (Windows Batch)
│   ├── deploy_frontend.sh          # Frontend deployment script (Linux / macOS / Cloud Shell)
│   └── deploy_frontend.bat         # Frontend deployment script (Windows Batch)
│
└── .gitignore                      # Workspace-level Git security rules
```

---

## Google Cloud Platform Configuration

- **Project ID**: `solvique-personal`
- **Location**: `US`
- **Dataset**: `ecommerce` (Brazilian Olist e-commerce dataset: `orders`, `customers`, `products`, `sellers`, `order_items`, `order_payments`, `order_reviews`, `geolocation`)
- **Runtime Service Account**: `solvique-backend-sa@solvique-personal.iam.gserviceaccount.com`
  - **Project-Level Role**: `roles/bigquery.jobUser` (Required for running query jobs)
  - **Dataset-Level Role**: `READER` on `solvique-personal:ecommerce` (Scoped least-privilege data access; no broad project `dataViewer`)

---

## Cloud Run & Data Persistence Considerations

> [!NOTE]
> Cloud Run instances use an ephemeral in-memory filesystem. Any data written to `/app/data/solvique_conversations.db` or `/app/data/report_assets/` inside a container instance is lost when the instance restarts or scales down. Existing local `uqe_conversations.db` files remain supported and are used when the new database filename is absent.
>
> **For Production Cloud Run Deployments:**
> 1. **Option A (Cloud Storage FUSE Mount)**: Mount a Cloud Storage bucket directly to `/app/data` in Cloud Run.
> 2. **Option B (Managed Database)**: Migrate the conversation store to Cloud SQL (PostgreSQL) or Cloud Firestore.

---

## Full Olist Dataset Import Instructions

To load the full ~100k row Olist Kaggle dataset into BigQuery without downloading via code:
1. Download the public dataset from [Kaggle Olist E-Commerce Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).
2. Extract the CSV files to a local directory.
3. Run the following `bq load` commands targeting `solvique-personal:ecommerce`:

```bash
# Orders
bq load --source_format=CSV --skip_leading_rows=1 solvique-personal:ecommerce.orders olist_orders_dataset.csv

# Customers
bq load --source_format=CSV --skip_leading_rows=1 solvique-personal:ecommerce.customers olist_customers_dataset.csv

# Products
bq load --source_format=CSV --skip_leading_rows=1 solvique-personal:ecommerce.products olist_products_dataset.csv

# Sellers
bq load --source_format=CSV --skip_leading_rows=1 solvique-personal:ecommerce.sellers olist_sellers_dataset.csv

# Order Items
bq load --source_format=CSV --skip_leading_rows=1 solvique-personal:ecommerce.order_items olist_order_items_dataset.csv

# Payments
bq load --source_format=CSV --skip_leading_rows=1 solvique-personal:ecommerce.order_payments olist_order_payments_dataset.csv

# Reviews
bq load --source_format=CSV --skip_leading_rows=1 solvique-personal:ecommerce.order_reviews olist_order_reviews_dataset.csv

# Geolocation
bq load --source_format=CSV --skip_leading_rows=1 solvique-personal:ecommerce.geolocation olist_geolocation_dataset.csv
```
