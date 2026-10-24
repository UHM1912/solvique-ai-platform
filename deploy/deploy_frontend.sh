#!/usr/bin/env bash
# ==============================================================================
# Solvique Frontend — Cloud Run Deployment Script
# Target: solvique-personal GCP Project (asia-south1)
# ==============================================================================
set -euo pipefail

PROJECT_ID="solvique-personal"
REGION="asia-south1"
SERVICE_NAME="solvique-frontend"
REPO_NAME="solvique-images"
IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"

echo "=== Deploying Solvique Frontend to Cloud Run ==="
echo "Project:        ${PROJECT_ID}"
echo "Region:         ${REGION}"
echo "Service:        ${SERVICE_NAME}"
echo "Image:          ${IMAGE_TAG}"

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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gcloud builds submit "${SCRIPT_DIR}/../solvique-frontend" \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE_TAG}"

# 3. Deploy to Cloud Run
echo "Deploying container image to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE_TAG}" \
  --allow-unauthenticated \
  --memory=512Mi \
  --cpu=1 \
  --timeout=60

echo "=== Deployment Complete ==="
gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT_ID}" --region="${REGION}" --format="value(status.url)"
