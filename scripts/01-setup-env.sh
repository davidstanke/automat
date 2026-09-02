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

echo "========================================"
echo "  Checking CLI Prerequisites..."
echo "========================================"

# 1. Check gcloud CLI
if command -v gcloud >/dev/null 2>&1; then
    echo "[✓] gcloud CLI found: $(gcloud --version 2>&1 | head -n 1)"
else
    echo "[!] ERROR: gcloud CLI is not installed."
    echo "    Please install Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# 2. Check agents-cli
if command -v agents-cli >/dev/null 2>&1; then
    echo "[✓] agents-cli found: $(agents-cli --version 2>&1 || echo 'Installed')"
else
    echo "[!] WARNING: agents-cli is not found in PATH."
    echo "    You can install it via uv/pip: pip install agents-cli"
fi

# 3. Check uv
if command -v uv >/dev/null 2>&1; then
    echo "[✓] uv package manager found: $(uv --version 2>&1)"
else
    echo "[!] WARNING: uv package manager not found. Recommended for Python environment management."
fi

echo ""
echo "========================================"
echo "  Configuring GCP Project & Region"
echo "========================================"

_GOOGLE_CLOUD_PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "")
_GOOGLE_CLOUD_LOCATION=$(gcloud config get-value compute/region 2>/dev/null || echo "")
_GOOGLE_CLOUD_LOCATION=${_GOOGLE_CLOUD_LOCATION:-us-central1}
_GOOGLE_GENAI_LOCATION=${GOOGLE_GENAI_LOCATION:-global}
_BIGQUERY_LOCATION=${BIGQUERY_LOCATION:-US}
# `|| true`: pipefail would abort the script when .env.example is not present.
_EXAMPLE_MODEL=$(sed -n 's/^export GOOGLE_GENAI_MODEL="\([^"]*\)".*/\1/p' .env.example 2>/dev/null | head -n 1 || true)
_GOOGLE_GENAI_MODEL=${GOOGLE_GENAI_MODEL:-${_EXAMPLE_MODEL:-gemini-3.6-flash}}

read -r -p "Enter GCP Project ID [${_GOOGLE_CLOUD_PROJECT_ID}]: " GOOGLE_CLOUD_PROJECT_ID || true
read -r -p "Enter GCP Deployment Location/Region [${_GOOGLE_CLOUD_LOCATION}]: " GOOGLE_CLOUD_LOCATION || true
read -r -p "Enter Gemini Model Location [${_GOOGLE_GENAI_LOCATION}]: " GOOGLE_GENAI_LOCATION || true
read -r -p "Enter Gemini Model [${_GOOGLE_GENAI_MODEL}]: " GOOGLE_GENAI_MODEL || true
read -r -p "Enter BigQuery Location [${_BIGQUERY_LOCATION}]: " BIGQUERY_LOCATION || true

GOOGLE_CLOUD_PROJECT_ID="${GOOGLE_CLOUD_PROJECT_ID:-${_GOOGLE_CLOUD_PROJECT_ID}}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-${_GOOGLE_CLOUD_LOCATION}}"
GOOGLE_GENAI_LOCATION="${GOOGLE_GENAI_LOCATION:-${_GOOGLE_GENAI_LOCATION}}"
GOOGLE_GENAI_MODEL="${GOOGLE_GENAI_MODEL:-${_GOOGLE_GENAI_MODEL}}"
BIGQUERY_LOCATION="${BIGQUERY_LOCATION:-${_BIGQUERY_LOCATION}}"

if [ -z "$GOOGLE_CLOUD_PROJECT_ID" ]; then
  echo "Error: GCP project ID must not be empty. Please run 'gcloud config set project [PROJECT_ID]' or specify one."
  exit 1
fi

echo "Setting gcloud defaults..."
# --verbosity=error prevents informational/success messages from printing to stderr
if ! gcloud config set project "${GOOGLE_CLOUD_PROJECT_ID}" --verbosity=error > /dev/null; then
  # gcloud itself automatically prints the failure message to stderr if an error occurs
  exit 1
fi

cat << EOF > .env
export GOOGLE_GENAI_USE_VERTEXAI="true"
export GOOGLE_CLOUD_PROJECT_ID="${GOOGLE_CLOUD_PROJECT_ID}"
export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION}"
export GOOGLE_GENAI_LOCATION="${GOOGLE_GENAI_LOCATION}"
export GOOGLE_GENAI_MODEL="${GOOGLE_GENAI_MODEL}"
export BIGQUERY_LOCATION="${BIGQUERY_LOCATION}"

# Prevent google.auth.exceptions.MutualTLSChannelError by disabling mTLS auto-discovery:
export GOOGLE_API_USE_CLIENT_CERTIFICATE="false"
export GOOGLE_API_USE_MTLS_ENDPOINT="never"

# Optional:
# export BIGQUERY_MCP_COMMAND="${PWD}/agents/sched_agent/scripts/mock-bigquery-mcp"

# Runtime wiring (STRATEGY_AGENT_URL, SCHEDULING_AGENT_URL, APP_URL,
# GOOGLE_CLOUD_AGENT_ENGINE_ID) is passed by \`agents-cli deploy\`, not set here.
# See .env.example.
EOF

cat << EOF

----------------------------------------
------ GOOGLE CLOUD ENVIRONMENT --------
----------------------------------------

GOOGLE_GENAI_USE_VERTEXAI="true"
GOOGLE_CLOUD_PROJECT_ID="${GOOGLE_CLOUD_PROJECT_ID}"
GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION}"
GOOGLE_GENAI_LOCATION="${GOOGLE_GENAI_LOCATION}"
GOOGLE_GENAI_MODEL="${GOOGLE_GENAI_MODEL}"
BIGQUERY_LOCATION="${BIGQUERY_LOCATION}"

----------------------------------------
Environment configuration written to .env
EOF
