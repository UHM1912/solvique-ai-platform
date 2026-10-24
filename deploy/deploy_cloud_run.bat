@echo off
rem ==============================================================================
rem Solvique Backend — Cloud Run Deployment Script (Windows Batch)
rem Target: solvique-personal GCP Project (asia-south1)
rem ==============================================================================
setlocal EnableDelayedExpansion

set PROJECT_ID=solvique-personal
set REGION=asia-south1
set SERVICE_NAME=solvique-backend
set REPO_NAME=solvique-images
set IMAGE_TAG=%REGION%-docker.pkg.dev/%PROJECT_ID%/%REPO_NAME%/%SERVICE_NAME%:latest
set SERVICE_ACCOUNT=solvique-backend-sa@%PROJECT_ID%.iam.gserviceaccount.com
set CLOUD_SQL_INSTANCE=solvique-personal:asia-south1:solvique-postgres
set GCS_BUCKET_NAME=solvique-personal-report-assets-65499697760

echo === Deploying Solvique Backend to Cloud Run ===
echo Project:            %PROJECT_ID%
echo Region:             %REGION%
echo Service:            %SERVICE_NAME%
echo Runtime SA:         %SERVICE_ACCOUNT%
echo Cloud SQL:          %CLOUD_SQL_INSTANCE%
echo Report Bucket:      %GCS_BUCKET_NAME%

rem 1. Ensure Artifact Registry repository exists
call gcloud artifacts repositories describe %REPO_NAME% --project=%PROJECT_ID% --location=%REGION% >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Creating Artifact Registry repository %REPO_NAME%...
    call gcloud artifacts repositories create %REPO_NAME% --project=%PROJECT_ID% --location=%REGION% --repository-format=docker --description="Docker repository for Solvique images"
)

rem 2. Build image via Google Cloud Build
echo Building container image with Cloud Build...
call gcloud builds submit ..\solvique-backend --project=%PROJECT_ID% --tag=%IMAGE_TAG%
if %ERRORLEVEL% NEQ 0 (
    echo Cloud Build failed. Exiting...
    exit /b %ERRORLEVEL%
)

rem 3. Deploy to Cloud Run
echo Deploying container image to Cloud Run...
call gcloud run deploy %SERVICE_NAME% ^
    --project=%PROJECT_ID% ^
    --region=%REGION% ^
    --image=%IMAGE_TAG% ^
    --service-account=%SERVICE_ACCOUNT% ^
    --allow-unauthenticated ^
    --add-cloudsql-instances=%CLOUD_SQL_INSTANCE% ^
    --set-env-vars="STORAGE_BACKEND=postgres,REPORT_ASSET_BACKEND=gcs,CLOUD_SQL_CONNECTION_NAME=%CLOUD_SQL_INSTANCE%,DB_NAME=solvique_db,DB_USER=solvique_app,GCS_BUCKET_NAME=%GCS_BUCKET_NAME%,big_query_project_id=%PROJECT_ID%,big_query_dataset=ecommerce,TAVILY_API_KEY=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" ^
    --set-secrets="DB_PASSWORD=solvique-db-password:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest" ^
    --memory=2Gi ^
    --cpu=2 ^
    --timeout=300

echo === Deployment Complete ===
call gcloud run services describe %SERVICE_NAME% --project=%PROJECT_ID% --region=%REGION% --format="value(status.url)"

