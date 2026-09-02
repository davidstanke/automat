#!/bin/bash
set -euo pipefail

# Configuration with defaults
PROJECT_ID="${PROJECT_ID:-${GOOGLE_CLOUD_PROJECT_ID:-automat-507412}}"
REGION="${REGION:-${GOOGLE_CLOUD_LOCATION:-us-central1}}"
POOL_NAME="${POOL_NAME:-github-pool}"
PROVIDER_NAME="${PROVIDER_NAME:-github-provider}"
SA_NAME="${SA_NAME:-github-actions-sdlc}"
RUNNER_SA_NAME="${RUNNER_SA_NAME:-sdlc-agent-runner}"
GITHUB_REPO="${GITHUB_REPO:-davidstanke/automat}"

echo "============================================================"
echo "  Setting up Workload Identity Federation & IAM for SDLC"
echo "  Project:     ${PROJECT_ID}"
echo "  Region:      ${REGION}"
echo "  GitHub Repo: ${GITHUB_REPO}"
echo "============================================================"

# Ensure project is set
gcloud config set project "${PROJECT_ID}" --verbosity=error

# Get project number
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
echo "Project Number: ${PROJECT_NUMBER}"

bind_role() {
  local member="$1"
  local role="$2"
  local count=0
  local max_retries=10
  local delay=3

  while true; do
    if gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
      --member="${member}" \
      --role="roles/${role}" \
      --condition=None >/dev/null 2>&1; then
      echo "  [✓] Bound roles/${role} to ${member}"
      return 0
    fi
    count=$((count + 1))
    if [ "$count" -ge "$max_retries" ]; then
      echo "  [✗] Failed to bind roles/${role} to ${member} after ${max_retries} attempts."
      return 1
    fi
    echo "  [...] Waiting for IAM propagation (attempt ${count}/${max_retries})..."
    sleep "$delay"
  done
}

# 1. Enable Required APIs
echo "[1/6] Enabling APIs..."
gcloud services enable \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  run.googleapis.com \
  aiplatform.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="${PROJECT_ID}"

# 2. Create/Verify Cloud Run Runtime Service Account
echo "[2/6] Configuring Cloud Run Runtime Service Account (${RUNNER_SA_NAME})..."
if ! gcloud iam service-accounts describe "${RUNNER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${RUNNER_SA_NAME}" \
    --display-name="SDLC Agents Cloud Run Runtime SA" \
    --project="${PROJECT_ID}"
  echo "Created service account: ${RUNNER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
  sleep 3
else
  echo "Service account ${RUNNER_SA_NAME} already exists."
fi

# Grant Vertex AI & Logging to Cloud Run Runtime SA
echo "Granting roles to ${RUNNER_SA_NAME}..."
bind_role "serviceAccount:${RUNNER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" "aiplatform.user"
bind_role "serviceAccount:${RUNNER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" "logging.logWriter"

# 3. Create/Verify GitHub Actions Invoker Service Account
echo "[3/6] Configuring GitHub Actions Invoker Service Account (${SA_NAME})..."
if ! gcloud iam service-accounts describe "${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="GitHub Actions SDLC Invoker SA" \
    --project="${PROJECT_ID}"
  echo "Created service account: ${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
  sleep 3
else
  echo "Service account ${SA_NAME} already exists."
fi

# Grant Cloud Run Invoker to GitHub Actions SA
bind_role "serviceAccount:${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" "run.invoker"

# 4. Create/Verify Workload Identity Pool
echo "[4/6] Configuring Workload Identity Pool (${POOL_NAME})..."
if ! gcloud iam workload-identity-pools describe "${POOL_NAME}" --location=global --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "${POOL_NAME}" \
    --project="${PROJECT_ID}" \
    --location="global" \
    --display-name="GitHub Actions Pool"
  echo "Created pool: ${POOL_NAME}"
else
  echo "Pool ${POOL_NAME} already exists."
fi

# 5. Create/Verify Workload Identity Provider
echo "[5/6] Configuring Workload Identity Provider (${PROVIDER_NAME})..."
if ! gcloud iam workload-identity-pools providers describe "${PROVIDER_NAME}" \
  --workload-identity-pool="${POOL_NAME}" \
  --location=global \
  --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_NAME}" \
    --project="${PROJECT_ID}" \
    --location="global" \
    --workload-identity-pool="${POOL_NAME}" \
    --display-name="GitHub Actions Provider" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
    --attribute-condition="assertion.repository == '${GITHUB_REPO}'"
  echo "Created provider: ${PROVIDER_NAME}"
else
  echo "Provider ${PROVIDER_NAME} already exists."
fi

# 6. Bind IAM Workload Identity User
echo "[6/6] Authorizing repository '${GITHUB_REPO}' to impersonate SA..."
WIF_PRINCIPAL="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_NAME}/attribute.repository/${GITHUB_REPO}"

count=0
while true; do
  if gcloud iam service-accounts add-iam-policy-binding "${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project="${PROJECT_ID}" \
    --role="roles/iam.workloadIdentityUser" \
    --member="${WIF_PRINCIPAL}" >/dev/null 2>&1; then
    echo "  [✓] Bound workloadIdentityUser to ${SA_NAME}"
    break
  fi
  count=$((count + 1))
  if [ "$count" -ge 10 ]; then
    echo "  [✗] Failed to bind workloadIdentityUser after 10 attempts."
    exit 1
  fi
  sleep 3
done

WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_NAME}/providers/${PROVIDER_NAME}"
WIF_SERVICE_ACCOUNT="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo ""
echo "============================================================"
echo "  Workload Identity Federation Setup Complete!"
echo "============================================================"
echo "GCP_PROJECT_ID:       ${PROJECT_ID}"
echo "GCP_REGION:           ${REGION}"
echo "WIF_PROVIDER:         ${WIF_PROVIDER}"
echo "WIF_SERVICE_ACCOUNT:  ${WIF_SERVICE_ACCOUNT}"
echo "RUNNER_SA:            ${RUNNER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
echo "============================================================"
