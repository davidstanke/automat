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

# ==============================================================================
# BigQuery Dataset & Menu Data Initialization
# ==============================================================================
BIGQUERY_LOCATION="${BIGQUERY_LOCATION:-US}"
DATASET_ID="catering"
TABLE_ID="menu_items"
MENU_DATA_FILE="data/catering/catering_menu.json"

echo "Initializing BigQuery dataset '${DATASET_ID}' in location '${BIGQUERY_LOCATION}'..."
if bq show --dataset "${GOOGLE_CLOUD_PROJECT_ID}:${DATASET_ID}" >/dev/null 2>&1; then
  echo "Dataset '${GOOGLE_CLOUD_PROJECT_ID}:${DATASET_ID}' already exists."
else
  echo "Creating dataset '${GOOGLE_CLOUD_PROJECT_ID}:${DATASET_ID}'..."
  bq mk --dataset \
    --location="${BIGQUERY_LOCATION}" \
    --description="Catering options and menu items" \
    "${GOOGLE_CLOUD_PROJECT_ID}:${DATASET_ID}"
fi

if [ -f "${MENU_DATA_FILE}" ]; then
  echo "Populating BigQuery table '${DATASET_ID}.${TABLE_ID}' from ${MENU_DATA_FILE}..."
  bq load \
    --replace \
    --source_format=NEWLINE_DELIMITED_JSON \
    --autodetect \
    "${GOOGLE_CLOUD_PROJECT_ID}:${DATASET_ID}.${TABLE_ID}" \
    "${MENU_DATA_FILE}"
  echo "BigQuery table '${DATASET_ID}.${TABLE_ID}' successfully populated."
else
  echo "Warning: Catering menu data file '${MENU_DATA_FILE}' not found. Skipping table population."
fi
