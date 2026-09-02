#!/bin/bash
set -euo pipefail

# Configuration
PROJECT_ID="${PROJECT_ID:-${GOOGLE_CLOUD_PROJECT_ID:-automat-507412}}"
REGION="${REGION:-${GOOGLE_CLOUD_LOCATION:-us-central1}}"
SERVICE_NAME="${SERVICE_NAME:-sdlc-implementer-agent}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-sdlc-agent-runner@${PROJECT_ID}.iam.gserviceaccount.com}"
MODEL="${GOOGLE_GENAI_MODEL:-gemini-3.7-flash}"
MODEL_LOCATION="${GOOGLE_GENAI_LOCATION:-global}"

echo "============================================================"
echo "  Deploying SDLC Implementer Agent to Cloud Run"
echo "  Project:         ${PROJECT_ID}"
echo "  Region:          ${REGION}"
echo "  Service Name:    ${SERVICE_NAME}"
echo "  Service Account: ${SERVICE_ACCOUNT}"
echo "============================================================"

# Ensure gcloud project is set
gcloud config set project "${PROJECT_ID}" --verbosity=error

# Deploy container to Cloud Run using gcloud run deploy --source
gcloud run deploy "${SERVICE_NAME}" \
  --source="sdlc-agents/implementer" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --service-account="${SERVICE_ACCOUNT}" \
  --memory="4Gi" \
  --cpu="2" \
  --timeout="3600" \
  --concurrency=10 \
  --min-instances=0 \
  --max-instances=5 \
  --no-allow-unauthenticated \
  --quiet \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_GENAI_MODEL=${MODEL},GOOGLE_CLOUD_PROJECT_ID=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},GOOGLE_GENAI_LOCATION=${MODEL_LOCATION}"

# Ensure GitHub Actions SA has run.invoker on this service
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:github-actions-sdlc@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --quiet >/dev/null 2>&1 || true

# Get Service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)")

echo ""
echo "============================================================"
echo "  Deployment Complete!"
echo "  Implementer Service URL: ${SERVICE_URL}"
echo "============================================================"
