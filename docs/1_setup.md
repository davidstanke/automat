# Setup

### 📌 Prerequisites

Ensure you have the following CLI tools installed on your system:
- **Google Cloud SDK (`gcloud`)**: [Install Guide](https://cloud.google.com/sdk/docs/install)
- **Google `agents-cli`**: Install via `pip install google-agents-cli` or `uv tool install google-agents-cli`
- **`uv` Package Manager**: [Install Guide](https://docs.astral.sh/uv/)

Authenticate `gcloud` before running the setup scripts. `--update-adc` writes
Application Default Credentials in the same pass, which is what the agents and
the Google client libraries use:
```bash
gcloud auth login --update-adc
```

---

### 🛠️ Project Setup

Run the following shell scripts in order from the repository root.

#### Step 1: Configure Environment Variables (`01-setup-env.sh`)
```bash
./scripts/01-setup-env.sh
```

* **Main Takeaway**: Checks CLI prerequisites (`gcloud`, `agents-cli`, `uv`), prompts for your GCP project credentials, configures `gcloud` defaults, and generates the root `.env` file.
* **Environment Variables Configured**:
  | Variable | Description | Default / Example |
  | :--- | :--- | :--- |
  | `GOOGLE_GENAI_USE_VERTEXAI` | Forces Google GenAI SDK to route via Gemini Enterprise Agent Platform (GEAP) rather than Google AI Studio | `"true"` |
  | `GOOGLE_CLOUD_PROJECT_ID` | Your target Google Cloud Project ID | `"your-gcp-project-id"` |
  | `GOOGLE_CLOUD_LOCATION` | Primary GCP deployment region (Cloud Run, Reasoning Engine) | `"us-central1"` |
  | `GOOGLE_GENAI_LOCATION` | Location for Vertex AI Gemini model inference API calls | `"global"` |
  | `GOOGLE_GENAI_MODEL` | Gemini model used by all agents | `"gemini-3.6-flash"` |
  | `BIGQUERY_LOCATION` | Location of the BigQuery `catering` dataset | `"US"` |

* **Optional Variables** (not prompted for):
  | Variable | Description | Example |
  | :--- | :--- | :--- |
  | `BIGQUERY_MCP_COMMAND` | BigQuery MCP server command used by `sched_agent` | `"$PWD/agents/sched_agent/scripts/mock-bigquery-mcp"` |
  | `STRATEGY_DOCS_BUCKET` | GCS bucket holding the strategy PDFs read by `strat_agent` | `"your-gcp-project-id-strategy-docs"` |
  | `LOG_LEVEL` | Verbosity of the orchestrator's own logs. `INFO` adds a line per A2A event naming the agent that authored it and whether it was withheld | `"WARNING"` |
  | `STRATEGY_AGENT_URL` | Agent card URL of `strat_agent`, used by the orchestrator over A2A | resolved at deploy time |
  | `SCHEDULING_AGENT_URL` | Agent card URL of `sched_agent`, used by the orchestrator over A2A | resolved at deploy time |
  | `GOOGLE_CLOUD_AGENT_ENGINE_ID` | Engine holding **this** agent's sessions (and Memory Bank for `sched_agent`). Injected on Agent Runtime; must be set explicitly on Cloud Run | resolved at deploy time |

---

#### Step 2: Enable APIs and Provision Resources (`02-init-api.sh`)
```bash
./scripts/02-init-api.sh
```

* **Main Takeaway**: Enables the required Google Cloud APIs and sets the default compute region for your GCP project.
* **Enabled APIs Summary**:
  | API Service | Purpose |
  | :--- | :--- |
  | `aiplatform.googleapis.com` | Gemini Enterprise Agent Platform (GEAP) Agent Runtime & Reasoning Engines |
  | `run.googleapis.com` | Cloud Run serverless container hosting for agents |
  | `artifactregistry.googleapis.com` | Container image storage repository |
  | `cloudbuild.googleapis.com` | Cloud Build automated container image compilation |
  | `compute.googleapis.com` | Provides the default compute service account Cloud Run runs as |
  | `bigquery.googleapis.com` | The `catering` dataset queried over MCP by `sched_agent` |
  | `apphub.googleapis.com` | Backs the Dashboard tab on an Agent Platform deployment |
  | `discoveryengine.googleapis.com` | Gemini Enterprise Discovery Engine & agent publishing |
  | `iam.googleapis.com` | Identity and Access Management service |
  | `cloudresourcemanager.googleapis.com` | GCP Project metadata & policy management |
  | `storage.googleapis.com` | Google Cloud Storage buckets for PDF documents and artifacts |
  | `serviceusage.googleapis.com` | Service usage API management |
  | `servicecontrol.googleapis.com` | Control plane reporting for GCP services |

---

#### Step 3: Configure IAM Permissions (`03-setup-iam.sh`)
```bash
./scripts/03-setup-iam.sh
```

* **Main Takeaway**: Grants necessary project-level IAM roles to Google Cloud runtime service accounts and the local developer user account so agents, container runtimes, build pipelines, and local development tools can execute seamlessly.
* **Service Accounts & Granted IAM Roles**:

  ##### 1. Gemini Enterprise Agent Platform (GEAP) Reasoning Engine Service Agent
  `service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com`
  - **`roles/aiplatform.user`** (*Agent Platform User*): Allows Reasoning Engine to execute models, manage sessions, and interact with Memory Bank.
  - **`roles/aiplatform.reasoningEngineServiceAgent`** (*Reasoning Engine Service Agent*): Standard Reasoning Engine operational role.
  - **`roles/bigquery.admin`** (*BigQuery Admin*): Query and interact with the `catering` BigQuery dataset.

  ##### 2. Compute Service Account (Cloud Run Runtime)
  `${PROJECT_NUMBER}-compute@developer.gserviceaccount.com`
  - **`roles/storage.admin`** (*Storage Admin*): Access strategy document PDFs and GCS log artifacts.
  - **`roles/artifactregistry.admin`** (*Artifact Registry Admin*): Pull container images for Cloud Run.
  - **`roles/logging.logWriter`** (*Logs Writer*): Write agent trace logs and telemetry to Cloud Logging.
  - **`roles/run.invoker`** (*Cloud Run Invoker*): Allows Cloud Run agent instances to invoke peer A2A Cloud Run services.
  - **`roles/bigquery.admin`** (*BigQuery Admin*): Query and manage BigQuery datasets from Cloud Run.
  - **`roles/aiplatform.user`** (*Agent Platform User*): Manage sessions on the orchestrator's Agent Engine.

  ##### 3. Cloud Build Service Account
  `${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com`
  - **`roles/artifactregistry.admin`** (*Artifact Registry Admin*): Push built container images to Artifact Registry.

  ##### 4. Local ADC Active Developer Account
  `${USER_ACCOUNT}`
  - **`roles/bigquery.admin`** (*BigQuery Admin*): Query the `catering` dataset locally using Application Default Credentials (ADC).

  ##### 5. Agent Identity Principal Set (Agent Runtime Identity & Workload Federation)
  `principalSet://agents.global.org-${ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/${PROJECT_NUMBER}`
  - **`roles/aiplatform.user`** (*Agent Platform User*): Enables inter-agent A2A communication and session access between Agent Runtime instances.
  - **`roles/serviceusage.serviceUsageConsumer`** (*Service Usage Consumer*): Allows agents deployed with `--agent-identity` to consume GCP APIs.
  - **`roles/storage.objectViewer`** (*Storage Object Viewer*): Read access to strategy PDFs and other artifacts in Cloud Storage.
  - **`roles/bigquery.admin`** (*BigQuery Admin*): Query and manage BigQuery datasets via MCP when running on Agent Runtime.

  ##### 6. Discovery Engine Service Account (Gemini Enterprise Invocations)
  `service-${PROJECT_NUMBER}@gcp-sa-discoveryengine.iam.gserviceaccount.com`
  - **`roles/aiplatform.user`** (*Agent Platform User*): Allows Gemini Enterprise to invoke deployed Reasoning Engines via Vertex AI streaming query API.

  > **Note on Organization ID (`ORG_ID`):**
  > - `03-setup-iam.sh` attempts to resolve `ORG_ID` automatically via `gcloud projects get-ancestors`.
  > - **If resolution is restricted:** If your IAM roles prevent querying ancestor hierarchy, find your Org ID in the GCP Console top project picker dropdown and run: `ORG_ID=<your-org-id> ./scripts/03-setup-iam.sh`.
  > - **Standalone projects:** If your GCP project does not belong to a GCP Organization (e.g. personal account), this binding is skipped automatically and the Reasoning Engine SA bindings (Item 1) handle basic access.

---

| [🏠 Return to README](../README.md) | [📚 Getting Started](../README.md#getting-started) | [Next: 2. Local Testing ➡️](2_local.md) |
| :--- | :---: | ---: |
