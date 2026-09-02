#!/bin/bash
set -euo pipefail

# Copyright 2026 Antigravity
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

if [ ! -f .env ]; then
  echo "Error: .env file not found. Please run scripts/01-setup-env.sh first."
  exit 1
fi

# Source environment variables
# shellcheck source=/dev/null
source .env

GOOGLE_CLOUD_PROJECT_ID="${GOOGLE_CLOUD_PROJECT_ID:-}"

if [ -z "${GOOGLE_CLOUD_PROJECT_ID:-}" ]; then
  echo "Error: GOOGLE_CLOUD_PROJECT_ID is not set in .env."
  exit 1
fi

echo "Setting up GCP IAM service account permissions for project ${GOOGLE_CLOUD_PROJECT_ID}..."

PROJECT_NUMBER=$(gcloud projects describe "$GOOGLE_CLOUD_PROJECT_ID" --format="value(projectNumber)")

FAILED=0
DEFERRED=0

# The aiplatform and discoveryengine service agents are created lazily on first API use.
# Creating them up front means the bindings below have something to attach to.
gcloud beta services identity create --service=aiplatform.googleapis.com \
  --project="$GOOGLE_CLOUD_PROJECT_ID" >/dev/null 2>&1 || true
gcloud beta services identity create --service=discoveryengine.googleapis.com \
  --project="$GOOGLE_CLOUD_PROJECT_ID" >/dev/null 2>&1 || true

# A refused grant must be visible here; unreported it surfaces later as a 403.
bind() {
  local member="$1" role="$2" err
  local max_retries=5
  local count=0
  local delay=2

  while true; do
    if err=$(gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT_ID" \
        --member="$member" --role "roles/${role}" --condition=None 2>&1 >/dev/null); then
      echo "  ok   roles/${role}"
      return 0
    elif echo "$err" | grep -q "does not exist"; then
      # The Agent Runtime service agent appears only after the first engine deploy.
      echo "  defer roles/${role} (service agent not created yet)"
      DEFERRED=$((DEFERRED + 1))
      return 0
    elif echo "$err" | grep -q -i "conflict"; then
      count=$((count + 1))
      if [ "$count" -ge "$max_retries" ]; then
        echo "  FAIL roles/${role}: $(echo "$err" | tail -1)"
        FAILED=$((FAILED + 1))
        return 1
      fi
      sleep "$delay"
      delay=$((delay * 2))
    else
      echo "  FAIL roles/${role}: $(echo "$err" | tail -1)"
      FAILED=$((FAILED + 1))
      return 1
    fi
  done
}

# 1. Reasoning Engine Service Account
RE_SA="service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
echo "Binding explicit roles to Reasoning Engine SA: ${RE_SA}..."

RE_ROLES=(
    "aiplatform.user"                        # models, sessions, Memory Bank
    "aiplatform.reasoningEngineServiceAgent" # Agent Runtime operational role
    "bigquery.admin"                         # catering dataset queries
    "networkservices.admin"                  # Agent Gateway usage and routing
    "agentregistry.user"                     # Agent Registry registration and lookups
)

for role in "${RE_ROLES[@]}"; do
  bind "serviceAccount:${RE_SA}" "$role"
done

# 2. Compute Service Account (Cloud Run runtime)
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
echo "Binding roles to Compute SA: ${COMPUTE_SA}..."
COMPUTE_ROLES=(
    "storage.admin"
    "artifactregistry.admin"
    "logging.logWriter"
    "run.invoker"
    "bigquery.admin"                         # BigQuery Admin access
    "aiplatform.user"                        # sessions on the orchestrator's engine
)

for role in "${COMPUTE_ROLES[@]}"; do
  bind "serviceAccount:${COMPUTE_SA}" "$role"
done

# 3. Cloud Build Service Account
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
echo "Binding artifactregistry.admin to Cloud Build SA: ${CLOUDBUILD_SA}..."
bind "serviceAccount:${CLOUDBUILD_SA}" "artifactregistry.admin"

# 4. Local ADC Active User Account
USER_ACCOUNT=$(gcloud config get-value account 2>/dev/null || echo "")
if [ -n "${USER_ACCOUNT}" ]; then
  echo "Binding roles/bigquery.admin to local developer user account (${USER_ACCOUNT}) for ADC access..."
  bind "user:${USER_ACCOUNT}" "bigquery.admin"
else
  echo "Warning: Could not detect active gcloud user account for local ADC IAM binding."
fi

# 5. Agent Identity Principal Set (for cross-agent A2A communication, GCS storage access, BigQuery on Agent Runtime)
ORG_ID="${ORG_ID:-$(gcloud projects get-ancestors "$GOOGLE_CLOUD_PROJECT_ID" --format="json" 2>/dev/null | python3 -c "import json, sys; print(next((a['id'] for a in json.load(sys.stdin) if a.get('type') == 'organization'), ''))" 2>/dev/null || echo "")}"
if [ -n "${ORG_ID}" ]; then
  AGENT_PRINCIPAL_SET="principalSet://agents.global.org-${ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/${PROJECT_NUMBER}"
  echo "Binding roles to Agent Identity Principal Set: ${AGENT_PRINCIPAL_SET}..."
  bind "${AGENT_PRINCIPAL_SET}" "aiplatform.user"
  bind "${AGENT_PRINCIPAL_SET}" "serviceusage.serviceUsageConsumer"
  bind "${AGENT_PRINCIPAL_SET}" "storage.objectViewer"
  bind "${AGENT_PRINCIPAL_SET}" "bigquery.admin"
else
  echo "Notice: Could not automatically resolve Organization ID for ${GOOGLE_CLOUD_PROJECT_ID}."
  echo "        If your project belongs to a GCP Organization, you can re-run with: ORG_ID=<org_id> ./scripts/03-setup-iam.sh"
fi

# 6. Discovery Engine Service Account (for Gemini Enterprise -> Agent Runtime / Reasoning Engine invocations)
DE_SA="service-${PROJECT_NUMBER}@gcp-sa-discoveryengine.iam.gserviceaccount.com"
echo "Binding roles to Discovery Engine SA: ${DE_SA}..."
bind "serviceAccount:${DE_SA}" "aiplatform.user"
bind "serviceAccount:${DE_SA}" "networkservices.viewer"
bind "serviceAccount:${DE_SA}" "agentregistry.user"

if [ "$FAILED" -gt 0 ]; then
  echo "IAM setup incomplete: ${FAILED} binding(s) failed. Deploys will 403 until fixed."
  exit 1
fi

if [ "$DEFERRED" -gt 0 ]; then
  echo
  echo "${DEFERRED} binding(s) deferred: the Agent Runtime service agent does not exist"
  echo "until the first agent is deployed. Re-run this script after Step 1 of the"
  echo "deployment section to apply them."
fi

echo "IAM bindings applied."

