#!/bin/sh
# Deploy the InstallGate API to Google Cloud Run (Seoul).
# Needs: gcloud installed and logged in, billing enabled on the project.
# Secrets are read from your local .env, stored in Secret Manager, and never printed.
# Usage: scripts/deploy-cloudrun.sh
set -eu
cd "$(dirname "$0")/.."

PROJECT="${GCP_PROJECT:-project-0820b947-3086-458b-9d4}"
REGION="${GCP_REGION:-asia-northeast3}"
SERVICE="${CR_SERVICE:-installgate-api}"

gcloud config set project "$PROJECT" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com

set -a
. ./.env
set +a

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

push_secret() {
  name="$1"
  value="$2"
  [ -n "$value" ] || { echo "$name is empty in .env" >&2; exit 1; }
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    printf %s "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
  else
    printf %s "$value" | gcloud secrets create "$name" --data-file=- >/dev/null
  fi
  gcloud secrets add-iam-policy-binding "$name" \
    --member="serviceAccount:$RUN_SA" --role=roles/secretmanager.secretAccessor >/dev/null
}
push_secret NEBIUS_API_KEY "${NEBIUS_API_KEY:-}"
push_secret TAVILY_API_KEY "${TAVILY_API_KEY:-}"

# --port 8000: the image listens on 8000, not Cloud Run's default 8080.
# --min-instances 0: scale to zero when idle (cold start of a few seconds). Use 1 to stay warm.
# --max-instances 1: one instance keeps the in-memory spend cap and rate limit exact.
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --port 8000 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --memory 512Mi \
  --set-secrets "NEBIUS_API_KEY=NEBIUS_API_KEY:latest,TAVILY_API_KEY=TAVILY_API_KEY:latest" \
  --set-env-vars "^@^NEBIUS_BASE_URL=${NEBIUS_BASE_URL}@MODEL_NANO=${MODEL_NANO}@MODEL_SUPER=${MODEL_SUPER}@MODEL_ULTRA=${MODEL_ULTRA}@DAILY_SPEND_CAP_USD=${DAILY_SPEND_CAP_USD}@ULTRA_ENABLED=${ULTRA_ENABLED}@RATE_LIMIT_PER_MINUTE=${RATE_LIMIT_PER_MINUTE:-30}@RATE_LIMIT_TRUST_PROXY=true@CACHE_PATH=/tmp/installgate.sqlite@LOG_LEVEL=${LOG_LEVEL:-INFO}"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo "API: $URL"
curl -fsS "$URL/health" && echo
echo "Next: scripts/deploy-cloudrun-ui.sh"
