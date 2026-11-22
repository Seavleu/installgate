#!/bin/sh
# Deploy the InstallGate UI (Next.js) to Cloud Run. Run deploy-cloudrun.sh first.
# Usage: scripts/deploy-cloudrun-ui.sh
set -eu
cd "$(dirname "$0")/.."

PROJECT="${GCP_PROJECT:-project-0820b947-3086-458b-9d4}"
REGION="${GCP_REGION:-asia-northeast3}"
SERVICE="${CR_UI_SERVICE:-installgate-ui}"
API_SERVICE="${CR_SERVICE:-installgate-api}"

gcloud config set project "$PROJECT" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
API_URL="$(gcloud run services describe "$API_SERVICE" --region "$REGION" --format='value(status.url)')"
SITE_URL="https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/cloud-run-source-deploy/${SERVICE}:$(date +%Y%m%d%H%M%S)"

# ui/Dockerfile copies from the repo root (ui/ and contracts/), so build with root context.
TMP="$(mktemp)"
cat >"$TMP" <<YAML
steps:
  - name: gcr.io/cloud-builders/docker
    args: ["build", "-f", "ui/Dockerfile", "-t", "$IMAGE", "."]
images: ["$IMAGE"]
YAML
gcloud builds submit --config "$TMP" --region "$REGION" .
rm -f "$TMP"

gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --port 3000 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 3 \
  --memory 512Mi \
  --set-env-vars "API_URL=${API_URL},PUBLIC_SITE_URL=${SITE_URL}"

echo "UI: $SITE_URL"
curl -fsS -o /dev/null -w "HTTP %{http_code}\n" "$SITE_URL/"
