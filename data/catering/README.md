`catering_menu.json` is newline-delimited JSON that `sched_agent` reads from BigQuery
over MCP. Import it as `<project_id>.catering.menu_items` — the table name the agent's
prompt asks for (`app/agent.py`).

```bash
bq --location=US mk --dataset "${GOOGLE_CLOUD_PROJECT_ID}:catering"
bq load --source_format=NEWLINE_DELIMITED_JSON --autodetect --replace \
  "${GOOGLE_CLOUD_PROJECT_ID}:catering.menu_items" data/catering/catering_menu.json
```

`sched_agent` runs `bigquery-mcp` as a local stdio subprocess inside its own container
and queries BigQuery directly as its runtime service account, so that account is the only
identity that needs access:

```bash
# Cloud Run runtime identity for sched_agent
COMPUTE_SA="$(gcloud projects describe $GOOGLE_CLOUD_PROJECT_ID --format='value(projectNumber)')-compute@developer.gserviceaccount.com"

# Run query jobs
gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT_ID" \
  --member="serviceAccount:${COMPUTE_SA}" --role="roles/bigquery.jobUser" --condition=None

# Read the catering dataset (dataset-scoped, not project-wide)
bq show --format=prettyjson "${GOOGLE_CLOUD_PROJECT_ID}:catering" > /tmp/catering.json
jq --arg sa "$COMPUTE_SA" '.access += [{"role":"READER","userByEmail":$sa}]' \
  /tmp/catering.json > /tmp/catering-updated.json
bq update --source /tmp/catering-updated.json "${GOOGLE_CLOUD_PROJECT_ID}:catering"
```

No public access is required: an earlier version of this file suggested granting query
access to `allUsers`, which would make the menu readable by anyone on the internet.
`roles/mcp.toolUser` is not required either — that role covers calling Google-*managed*
MCP servers, and this MCP server is a subprocess of the agent, not a managed endpoint.
Both were verified unnecessary against a working deployment.
