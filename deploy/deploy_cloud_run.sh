#!/usr/bin/env bash
# ==============================================================================
# Solvique Backend — Cloud Run Deployment Script
# Target: solvique-personal GCP Project (asia-south1)
# ==============================================================================
set -euo pipefail

PROJECT_ID="solvique-personal"
REGION="asia-south1"
SERVICE_NAME="solvique-backend"
REPO_NAME="solvique-images"
IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"
SERVICE_ACCOUNT="solvique-backend-sa@${PROJECT_ID}.iam.gserviceaccount.com"
CLOUD_SQL_INSTANCE="solvique-personal:asia-south1:solvique-postgres"
GCS_BUCKET_NAME="solvique-personal-report-assets-65499697760"

echo "=== Deploying Solvique Backend to Cloud Run ==="
echo "Project:         ${PROJECT_ID}"
echo "Region:          ${REGION}"
echo "Service:         ${SERVICE_NAME}"
echo "Runtime SA:      ${SERVICE_ACCOUNT}"
echo "Cloud SQL:       ${CLOUD_SQL_INSTANCE}"
echo "Report Bucket:   ${GCS_BUCKET_NAME}"

# 1. Ensure Artifact Registry repository exists
gcloud artifacts repositories describe "${REPO_NAME}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${REPO_NAME}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --repository-format=docker \
  --description="Docker repository for Solvique images"

# 2. Build image via Google Cloud Build
echo "Building container image with Cloud Build..."
gcloud builds submit ../solvique-backend \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE_TAG}"

# 3. Deploy to Cloud Run
echo "Deploying container image to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE_TAG}" \
  --service-account="${SERVICE_ACCOUNT}" \
  --allow-unauthenticated \
  --add-cloudsql-instances="${CLOUD_SQL_INSTANCE}" \
  --set-env-vars="STORAGE_BACKEND=postgres,REPORT_ASSET_BACKEND=gcs,CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_INSTANCE},DB_NAME=solvique_db,DB_USER=solvique_app,GCS_BUCKET_NAME=${GCS_BUCKET_NAME},big_query_project_id=${PROJECT_ID},big_query_dataset=ecommerce,TAVILY_API_KEY=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" \
  --set-secrets="DB_PASSWORD=solvique-db-password:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest" \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300

echo "=== Deployment Complete ==="
gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT_ID}" --region="${REGION}" --format="value(status.url)"
