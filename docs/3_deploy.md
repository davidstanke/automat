# Deploying agents to Google Cloud

Once tested locally, deploy your agents to **Gemini Enterprise Agent Platform (GEAP) Agent Runtime** and interact with them in the Cloud Console. All deployment commands below execute directly from the repository root.

## Multi-Agent Agent Descriptions

The system consists of 4 specialized agents cooperating over the **Agent-to-Agent (A2A)** protocol. In this section 3 of the 4 specialized agents will be deployed and the 4th agent (`cater_agent`) will be built up from scratch:

| Agent | Directory / Name | Role & Description | Deployment Target | Connecting Tools / Subagents |
| :--- | :--- | :--- | :--- | :--- |
| 👑 **Luncher Orchestrator** | `luncher_agent` | **Primary Workflow Coordinator**: Orchestrates end-to-end lunch planning across sub-agents in a 2-stage pipeline (parallel gathering then synthesis). | **Agent Runtime** (`agents-cli deploy` with `--agent-identity`) | • **Subagents**: `strategy_agent`, `scheduling_agent`, `cater_agent` (via `parallel_info_gatherer`)<br>• **Internal Agent**: `lunch_synthesizer`<br>• **Tools**: `format_lunch_proposal_tool` |
| 🎯 **Strategy Agent** | `strat_agent` | **Corporate Strategy Analyst**: Analyzes company strategy documents and product launch roadmaps (OmniChef, VisionSphere) to provide contextual justifications. | **Agent Runtime** (`agents-cli deploy` with `--agent-identity`) | • **Tools**: `inspect_strategy_documents` (reads PDFs from GCS bucket `gs://${STRATEGY_DOCS_BUCKET}` or local directory)<br>• **Subagent of**: `luncher_agent` |
| 📅 **Scheduling Agent** | `sched_agent` | **Meeting & Calendar Coordinator**: Evaluates team schedules, detects overlaps, proposes ranked time slots, and manages team bookings. | **Agent Runtime** (`agents-cli deploy` with `--agent-identity`) | • **Tools**: `get_team_members`, `book_meeting`, `get_bookings`, `cancel_booking`, `cancel_all_bookings`<br>• **Storage**: Reasoning Engine Memory Bank (team bookings)<br>• **Subagent of**: `luncher_agent` |
| 🥪 **Catering Agent** *(Upcoming)* | `cater_agent` | **Catering & Dietary Coordinator**: Suggests balanced, themed lunch menus and records/filters team dietary preferences. *(To be built from scratch).* | **Agent Runtime** (`agents-cli deploy` with `--agent-identity`) | • **Tools**: `fetch_catering_data` (BigQuery `catering.menu_items` via MCP `execute_sql`), dietary preference memory tools<br>• **Storage**: Reasoning Engine Memory Bank (dietary preferences)<br>• **Subagent of**: `luncher_agent` |

> **NOTE**
>
> **Catering Agent Development:** We will come back to the Catering Agent (`cater_agent`) and build it up from scratch in a dedicated implementation phase (see [Adding the catering agent](cater_agent.md)).

> **NOTE**
>
> Why agents deploy to Agent Runtime:
>
> - **Injected Memory Bank Engine:** `sched_agent` and `cater_agent` store team bookings and dietary preferences in Memory Bank (`reasoningEngines/<ENGINE_ID>`). Agent Runtime automatically injects `GOOGLE_CLOUD_AGENT_ENGINE_ID`, so the host *is* the memory host without needing separate engine infrastructure.
> - **Agent Identity (`--agent-identity`):** Deploys agents with Workload Identity Federation. Under Agent Identity, cross-agent A2A requests authenticate securely via `GenaiApiTransport` (through `vertexai.Client()._api_client.request()`) rather than unbound bearer tokens, while granting each agent runtime permissions to GCP resources (GCS, BigQuery, and Reasoning Engines) via the project's Principal Set.
> - **Orchestrator Hosting:** `luncher_agent` deploys directly to Agent Runtime, serving both ADK reasoning engine routes and A2A endpoints seamlessly.

---

## Deploying the agents to GEAP Agent Runtime

### Step 1: Load the environment

Every deployed agent gets these environment variables in their runtime. `BASE_ENV` configures project and model connectivity, while `AGENT_SETTINGS_ENV` enables runtime telemetry and prompt/response logging required for GEAP Cloud evaluations.

```bash
source .env

BASE_ENV="GOOGLE_GENAI_MODEL=${GOOGLE_GENAI_MODEL},GOOGLE_GENAI_LOCATION=${GOOGLE_GENAI_LOCATION},GOOGLE_CLOUD_PROJECT_ID=${GOOGLE_CLOUD_PROJECT_ID},GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION}"

AGENT_SETTINGS_ENV="GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true,OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true,OTEL_SEMCONV_STABILITY_OPT_IN=default"
```

### Step 2 (Optional): Serve the strategy PDFs from Cloud Storage

`strat_agent` reads the PDFs bundled in-memory, `agents/strat_agent/data/docs/`, unless `STRATEGY_DOCS_BUCKET` names a bucket. Same image, same code; one variable picks the branch. Skippable.

```bash
export STRATEGY_DOCS_BUCKET="${GOOGLE_CLOUD_PROJECT_ID}-strategy-docs"

gcloud storage buckets create "gs://${STRATEGY_DOCS_BUCKET}" \
  --project "$GOOGLE_CLOUD_PROJECT_ID" --location "$GOOGLE_CLOUD_LOCATION"

gcloud storage cp agents/strat_agent/data/docs/*.pdf "gs://${STRATEGY_DOCS_BUCKET}/"

gcloud storage buckets add-iam-policy-binding "gs://${STRATEGY_DOCS_BUCKET}" \
  --member "serviceAccount:service-$(gcloud projects describe "$GOOGLE_CLOUD_PROJECT_ID" --format='value(projectNumber)')@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role roles/storage.objectViewer

gcloud storage ls "gs://${STRATEGY_DOCS_BUCKET}"
```

The grant goes to the **Agent Runtime service agent** (`gcp-sa-aiplatform-re`),
which `03-setup-iam.sh` provisions — so run this after it. The `ls` should list
eight PDFs. The strategy deploy below picks the variable up on its own.

### Step 3: Deploy the Strategy Agent (`strat_agent`) to Agent Runtime.

```bash
uv --directory agents/strat_agent run agents-cli deploy \
  --project "$GOOGLE_CLOUD_PROJECT_ID" \
  --region "$GOOGLE_CLOUD_LOCATION" \
  --agent-identity \
  --update-env-vars "$BASE_ENV,$AGENT_SETTINGS_ENV${STRATEGY_DOCS_BUCKET:+,STRATEGY_DOCS_BUCKET=$STRATEGY_DOCS_BUCKET}"
```

> **NOTE**
>
> `${VAR:+…}` appends `STRATEGY_DOCS_BUCKET` only when set, so one command covers
> both paths. Agent Runtime rejects an env var with an empty value:
> `400 INVALID_ARGUMENT … env[4].value; Required field is not set`.

### Step 4: Deploy the Scheduling Agent (`sched_agent`) to Agent Runtime

```bash
uv --directory agents/sched_agent run agents-cli deploy \
  --project "$GOOGLE_CLOUD_PROJECT_ID" \
  --region "$GOOGLE_CLOUD_LOCATION" \
  --agent-identity \
  --no-wait \
  --update-env-vars "$BASE_ENV,$AGENT_SETTINGS_ENV,BIGQUERY_LOCATION=${BIGQUERY_LOCATION}"
```

> **NOTE**
>
> This engine also hosts the bookings Memory Bank. Takes 5-10 min; add `--no-wait` and poll `agents-cli deploy --status` if the command may time out.

### Step 5: Deploy the orchestrating Luncher Agent (`luncher_agent`) to Agent Runtime

Pass the deployed sub-agents' Reasoning Engine unique IDs so the orchestrator configures their Agent Runtime A2A endpoints.

Each agent's deploy step writes its engine ID to `agents/<agent_name>/deployment_metadata.json` under `"remote_agent_runtime_id"` (the numeric ID at the end of `projects/.../reasoningEngines/<ENGINE_ID>`).

Extract them automatically using `jq` and deploy:

```bash
STRAT_ENGINE_ID=$(jq -r '.remote_agent_runtime_id | split("/") | last' agents/strat_agent/deployment_metadata.json 2>/dev/null || echo "")
SCHED_ENGINE_ID=$(jq -r '.remote_agent_runtime_id | split("/") | last' agents/sched_agent/deployment_metadata.json 2>/dev/null || echo "")

uv --directory agents/luncher_agent run agents-cli deploy \
  --project "$GOOGLE_CLOUD_PROJECT_ID" \
  --region "$GOOGLE_CLOUD_LOCATION" \
  --agent-identity \
  --update-env-vars "$BASE_ENV,$AGENT_SETTINGS_ENV${STRAT_ENGINE_ID:+,STRATEGY_AGENT_ENGINE_ID=$STRAT_ENGINE_ID}${SCHED_ENGINE_ID:+,SCHEDULING_AGENT_ENGINE_ID=$SCHED_ENGINE_ID}"
```

> **NOTE**
>
> **Manual Alternative:** You can also copy the numeric ID directly from each agent's `deployment_metadata.json` (or the console / CLI output from Steps 3 & 4):
> ```bash
> STRAT_ENGINE_ID="9876543210987654321"
> SCHED_ENGINE_ID="1234567890123456789"
> ```

### Step 6: Manual testing of deployed agents
Test the orchestrator agent (which will also invoke the other agents):

- visit [Deployments on Agent Runtime](https://console.cloud.google.com/agent-platform/runtimes) and navigate to "luncher-agent"
- Click "Playground"
- enter a prompt like `Schedule a lunch meeting for Monday`

> **NOTE**
>
> We will come back to `cater_agent` and build it up from scratch following [`cater_agent.md`](cater_agent.md) before executing this step

---

| [⬅️ Previous: 2. Local Testing](2_local.md) | [📚 Getting Started](../README.md#getting-started) | [Next: 4. Extending Luncher with a catering agent ➡️](4_cater_agent.md) |
| :--- | :---: | ---: |
