# SDLC Implementer Agent Service

The **Implementer Agent** is an automated multi-agent SDLC pipeline built natively on the **Antigravity SDK (`google-antigravity`)**. It decomposes feature specifications into discrete tasks, creates verification tests, implements code increments, runs verification tests, and opens a Pull Request on GitHub.

---

## 1. Deploy to Google Cloud Run

### Prerequisites
- Google Cloud SDK (`gcloud`) installed and logged in
- Active GCP Project with billing enabled

### Deploy with Script
Run the automated deployment script from the repository root:

```bash
PROJECT_ID="<your-gcp-project-id>" \
REGION="us-central1" \
./scripts/deploy_cloud_run.sh
```

#### What the script configures:
- Enables `run.googleapis.com`, `artifactregistry.googleapis.com`, `cloudbuild.googleapis.com`, and `aiplatform.googleapis.com`.
- Grants `roles/aiplatform.user` to the Cloud Run service account for Vertex AI (`gemini-3.7-flash`).
- Builds the multi-runtime container (Python 3.12, Node.js 20, Git, GitHub CLI) and deploys to Cloud Run (2 vCPU, 4GB RAM, 3600s request timeout, authenticated access).

Note the output **Service URL** (e.g. `https://sdlc-implementer-agent-...a.run.app`).

---

## 2. Configure GitHub Repository

Ensure Workload Identity Federation (WIF) is established between GitHub Actions and your GCP project.

### GitHub Repository Variables
In GitHub under **Settings > Secrets and variables > Actions > Variables**, add:

| Variable Name | Description | Example Value |
|---|---|---|
| `IMPLEMENTER_SERVICE_URL` | Deployed Cloud Run Service URL | `https://sdlc-implementer-agent-xyz-uc.a.run.app` |
| `WIF_PROVIDER` | Workload Identity Provider resource path | `projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| `WIF_SERVICE_ACCOUNT` | Service Account email with Cloud Run Invoker role | `github-actions@my-project.iam.gserviceaccount.com` |
| `GCP_PROJECT_ID` | Google Cloud Project ID | `my-project-id` |
| `GCP_REGION` | Google Cloud Region | `us-central1` |

### Required IAM Roles
Ensure the WIF Service Account (`WIF_SERVICE_ACCOUNT`) has:
- `roles/run.invoker` on the Cloud Run service (or project level).

---

## 3. Invoking the Agent

### A. Automatic Trigger on Branch Push
Whenever you push a feature branch containing a specification in `docs/specs/*.md` (excluding `_implemented/`), the workflow [`.github/workflows/implement-spec.yml`](../../.github/workflows/implement-spec.yml) automatically triggers:

```bash
git checkout -b feature/user-profile
# Add docs/specs/user-profile.md
git commit -m "docs: add user profile specification"
git push -u origin feature/user-profile
```

### B. Manual Dispatch from GitHub Actions
Navigate to **Actions > Implement Feature Spec > Run workflow**, and provide:
- **Spec Path**: `docs/specs/my-feature.md`
- **Branch**: `feature/my-feature` (optional, defaults to current branch)
- **Create PR**: `true`

### C. Direct Client CLI Invocation
To invoke the remote service directly from your workstation:

```bash
sdlc-agents/.venv/bin/python sdlc-agents/implementer/client.py docs/specs/my-feature.md \
  --url "https://sdlc-implementer-agent-xyz-uc.a.run.app" \
  --id-token "$(gcloud auth print-identity-token --audiences=https://sdlc-implementer-agent-xyz-uc.a.run.app)" \
  --github-token "$GITHUB_TOKEN" \
  --repo-url "https://github.com/owner/repo.git" \
  --branch "feature/my-feature"
```
