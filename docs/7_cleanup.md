# Cleanup

To delete deployed cloud resources and prevent ongoing charges, run the cleanup commands using your environment variables:

```bash
source .env

# 1. Delete Agent Registrations from Gemini Enterprise (Optional)
PROJECT_NUMBER=$(gcloud projects describe "$GOOGLE_CLOUD_PROJECT_ID" --format="value(projectNumber)")
TOKEN=$(gcloud auth print-access-token)

# 2. Delete Agent Runtime engines (luncher-agent, strat-agent, sched-agent, cater-agent)
API="https://${GOOGLE_CLOUD_LOCATION}-aiplatform.googleapis.com/v1/projects/${GOOGLE_CLOUD_PROJECT_ID}/locations/${GOOGLE_CLOUD_LOCATION}/reasoningEngines"

for NAME in luncher-agent strat-agent sched-agent cater-agent; do
  ENGINE=$(curl -s -H "Authorization: Bearer ${TOKEN}" "$API" \
    | jq -r --arg n "$NAME" '.reasoningEngines[]? | select(.displayName==$n) | .name')
  if [ -z "$ENGINE" ]; then echo "skip: no engine named $NAME"; continue; fi
  echo "deleting $NAME ($ENGINE)"
  curl -s -X DELETE -H "Authorization: Bearer ${TOKEN}" \
    "https://${GOOGLE_CLOUD_LOCATION}-aiplatform.googleapis.com/v1/${ENGINE}?force=true"
done

# 3. Delete Agent Registry Services
for SVC in luncher-agent-service strat-agent-service sched-agent-service cater-agent-service telemetry-service logging-service agentregistry-service aiplatform-re-service; do
  echo "deleting Agent Registry service: $SVC"
  gcloud agent-registry services delete "$SVC" \
    --project="${GOOGLE_CLOUD_PROJECT_ID}" \
    --location="${GOOGLE_CLOUD_LOCATION}" \
    --quiet 2>/dev/null || true
done

# 4. Delete Agent Gateways & Security Policies
gcloud network-security authz-policies delete luncher-gateway-aisecurity-authzpolicy \
  --location="${GOOGLE_CLOUD_LOCATION}" --project="${GOOGLE_CLOUD_PROJECT_ID}" --quiet 2>/dev/null || true

gcloud network-security authz-policies delete luncher-gateway-iap-authzpolicy \
  --location="${GOOGLE_CLOUD_LOCATION}" --project="${GOOGLE_CLOUD_PROJECT_ID}" --quiet 2>/dev/null || true

gcloud beta service-extensions authz-extensions delete luncher-gateway-aisecurity-authzextension \
  --location="${GOOGLE_CLOUD_LOCATION}" --project="${GOOGLE_CLOUD_PROJECT_ID}" --quiet 2>/dev/null || true

gcloud beta service-extensions authz-extensions delete luncher-gateway-iap-authzextension \
  --location="${GOOGLE_CLOUD_LOCATION}" --project="${GOOGLE_CLOUD_PROJECT_ID}" --quiet 2>/dev/null || true

curl -s -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "https://networkservices.googleapis.com/v1/projects/${GOOGLE_CLOUD_PROJECT_ID}/locations/${GOOGLE_CLOUD_LOCATION}/agentGateways/luncher-gateway" 2>/dev/null || true

# 5. Delete Model Armor Template
curl -s -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "https://modelarmor.googleapis.com/v1/projects/${GOOGLE_CLOUD_PROJECT_ID}/locations/us/templates/luncher-armor-policy" 2>/dev/null || true
```

---

| [⬅️ Previous: 6. Enterprise Hardening](6_gateway_registry.md) | [📚 Getting Started](../README.md#getting-started) | [🏠 Return to README ➡️](../README.md) |
| :--- | :---: | ---: |
