# 🧠 Corporate Strategy Agent

An agentic application built using the Google Agent Development Kit (ADK) that inspects corporate documents (PDFs) and synthesizes the implied corporate strategy into a terse, high-quality statement using bulleted assertions.

The agent is exposed via the open **Agent-to-Agent (A2A)** protocol, allowing other distributed agents to call, delegate, and collaborate with it.


---

## 🏛️ Architecture & Document Storage

- **Local Development**: Reads strategy `.pdf` files from the local directory `agents/strat_agent/data/docs/`.
- **Google Cloud Storage (GCS) Integration**: optional. When `STRATEGY_DOCS_BUCKET` is set, `strat_agent` retrieves the strategy PDFs from that bucket (`gs://$GOOGLE_CLOUD_PROJECT_ID-strategy-docs/`) instead of the bundled copies. The switch is the variable alone; the code path is the same either way.

---

## 🛠️ Configuration

The agent is dynamically self-configuring and switches its document source based on environment variables:

1. **Local Development (Default)**:
   Reads `.pdf` files from the local directory `agents/strat_agent/data/docs/`.
2. **Production (Google Cloud)**:
   If `STRATEGY_DOCS_BUCKET` is specified, the agent connects via the Google Cloud SDK client to read strategy PDFs directly from the GCS bucket.

### `.env` Parameters

Configuration lives in the `.env` file at the repository root, shared by all three
agents — see `.env.example` for the full set. The one variable specific to this agent
is optional:

```env
# (Optional) GCS bucket for production document storage
export STRATEGY_DOCS_BUCKET="your-google-cloud-project-id-strategy-docs"
```

`PORT` belongs in neither file: `main.py` defaults to 8081, and Agent Runtime injects
it at deploy time. Setting it at the root would apply to all three agents at once.

---

## 🚀 Execution & Local Testing

Run from the repository root. `uv` synchronizes the agent's dependencies and starts
the A2A server:

```bash
uv --directory agents/strat_agent run main.py
```

The server listens on `0.0.0.0:8081` (or the configured `PORT`). Each agent carries
its own `pyproject.toml`, so `--directory` is what selects the environment — a bare
`uv run` or `uv sync` from the root fails with `No pyproject.toml found`.

---

## 🛰️ A2A Integration

When running, the agent automatically advertises its capabilities via an **Agent Card** at:

```
http://localhost:8081/a2a/app/.well-known/agent-card.json
```

Other agents reach it through the ADK's `RemoteA2aAgent`, which is attached as a
sub-agent and invoked by the calling agent's model rather than called directly.
`agents/luncher_agent/app/agent.py` wires it up this way:

```python
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

strategy_agent = RemoteA2aAgent(
    name="strategy_agent",
    description=(
        "Analyzes GeniCo corporate strategy and product initiative roadmaps. "
        "Consult this agent for strategic context and launch schedules."
    ),
    agent_card="http://localhost:8081/a2a/app/.well-known/agent-card.json",
    timeout=120.0,
)
```

---

## ☁️ Agent Runtime Deployment

`agents-cli deploy` builds the container and wires the runtime; root `README.md`
§3 has the sequence. Two things are specific to this agent:

- **`STRATEGY_DOCS_BUCKET` is optional.** Unset, the agent reads the PDFs in
  `data/docs/`, baked into the image. Never pass it empty — Agent Runtime
  rejects an env var with no value and fails the deploy.
- **When set**, the Agent Runtime service agent
  `service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com` needs
  `roles/storage.objectViewer` on the bucket; root README §3 step 1b grants it.
  A bucket that is empty or unreadable raises rather than degrading.
