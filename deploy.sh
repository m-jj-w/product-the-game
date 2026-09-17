#!/usr/bin/env bash
# Deploy Product: The Game to Cloud Run + Firebase Hosting, in the same
# GCP project (mjjw-ai-projects) TalkingLog already lives in.
#
# One-time setup, before the first run of this script (not repeated by
# it -- these aren't idempotent the way the deploy itself is):
#
#   firebase hosting:sites:create product-the-game-mjjw --project mjjw-ai-projects
#
#   openssl rand -base64 18 | gcloud secrets create product-the-game-password \
#     --project mjjw-ai-projects --data-file=-
#   # retrieve it yourself afterward, it's never printed here or in chat:
#   gcloud secrets versions access latest --secret=product-the-game-password \
#     --project mjjw-ai-projects
#
# Every run after that: just ./deploy.sh

set -euo pipefail

PROJECT="mjjw-ai-projects"
REGION="us-east1"
SERVICE="product-the-game"

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --project "$PROJECT" \
  --allow-unauthenticated \
  --set-env-vars="AUTH_USERNAME=play,GOOGLE_CLOUD_PROJECT=$PROJECT" \
  --set-secrets="AUTH_PASSWORD=product-the-game-password:latest"

firebase deploy --only "hosting:$SERVICE" --project "$PROJECT"

echo
echo "Deployed. Live at: https://product-the-game-mjjw.web.app"
