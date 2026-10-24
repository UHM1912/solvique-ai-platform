@echo off
rem ==============================================================================
rem Solvique Frontend — Cloud Run Deployment Script (Windows Batch)
rem Target: solvique-personal GCP Project (asia-south1)
rem ==============================================================================
setlocal EnableDelayedExpansion

set PROJECT_ID=solvique-personal
set REGION=asia-south1
set SERVICE_NAME=solvique-frontend
set REPO_NAME=solvique-images
set IMAGE_TAG=%REGION%-docker.pkg.dev/%PROJECT_ID%/%REPO_NAME%/%SERVICE_NAME%:latest

echo === Deploying Solvique Frontend to Cloud Run ===
echo Project:        %PROJECT_ID%
echo Region:         %REGION%
echo Service:        %SERVICE_NAME%
echo Image:          %IMAGE_TAG%

rem 1. Ensure Artifact Registry repository exists
call gcloud artifacts repositories describe %REPO_NAME% --project=%PROJECT_ID% --location=%REGION% >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Creating Artifact Registry repository %REPO_NAME%...
    call gcloud artifacts repositories create %REPO_NAME% --project=%PROJECT_ID% --location=%REGION% --repository-format=docker --description="Docker repository for Solvique images"
)

rem 2. Build image via Google Cloud Build
echo Building container image with Cloud Build...
call gcloud builds submit ..\solvique-frontend --project=%PROJECT_ID% --tag=%IMAGE_TAG%
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
    --allow-unauthenticated ^
    --memory=512Mi ^
    --cpu=1 ^
    --timeout=60

echo === Deployment Complete ===
call gcloud run services describe %SERVICE_NAME% --project=%PROJECT_ID% --region=%REGION% --format="value(status.url)"

