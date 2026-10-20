#!/usr/bin/env bash
# Run in an authenticated Cloud Shell, from a clean, reviewed checkout.
set -euo pipefail
cd "$(dirname "$0")/.."
SAQ_RELEASE_SHA=$(git rev-parse HEAD)
if [[ ${1:-} != "$SAQ_RELEASE_SHA" ]]; then
  echo 'Pass the full reviewed checkout SHA as the first argument.' >&2
  exit 1
fi
if [[ -n $(git status --porcelain) ]]; then
  echo 'The release checkout must be clean. Preserve your changes before continuing.' >&2
  exit 1
fi
for SAQ_RELEASE_TOOL in gcloud node npm curl; do
  command -v "$SAQ_RELEASE_TOOL" >/dev/null || { echo "Missing: $SAQ_RELEASE_TOOL" >&2; exit 1; }
done
if [[ -z $(gcloud auth list --filter=status:ACTIVE --format='value(account)') ]]; then
  echo 'Google Cloud login is required in this shell.' >&2
  exit 1
fi
SAQ_RELEASE_PROJECT=saq-qurylys
SAQ_RELEASE_REGION=europe-west1
SAQ_RELEASE_SERVICE=saq-qurylys-api
SAQ_RELEASE_IMAGE="europe-west1-docker.pkg.dev/$SAQ_RELEASE_PROJECT/saq-qurylys/api:release-${SAQ_RELEASE_SHA:0:12}"
SAQ_RELEASE_OLD_REVISION=$(gcloud run services describe "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --format='value(status.latestReadyRevisionName)')
SAQ_RELEASE_API=$(gcloud run services describe "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --format='value(status.url)')

# Build the normal Hosting entry, never the local demonstration configuration.
node deploy/write-hosting-config.mjs "$SAQ_RELEASE_API"
(cd frontend && npm ci && npm run build:hosting)
node --input-type=module - "$SAQ_RELEASE_SHA" <<'JS'
import { writeFile } from 'node:fs/promises'
await writeFile('frontend/dist/release.json', JSON.stringify({ gitSha: process.argv[2], builtAt: new Date().toISOString() }) + '\n')
JS
npx --yes firebase-tools@15.34.0 deploy --only firestore:indexes --project "$SAQ_RELEASE_PROJECT" --non-interactive
echo 'Wait for new Firestore indexes to finish building before checking their queries.'
gcloud builds submit . --project="$SAQ_RELEASE_PROJECT" --config=deploy/cloudbuild.yaml --substitutions="_IMAGE=$SAQ_RELEASE_IMAGE"

# Change only the image and release label. Preserve secrets, model, identity and limits.
gcloud run services update "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --image="$SAQ_RELEASE_IMAGE" --update-labels="saq-git-sha=$SAQ_RELEASE_SHA"
if ! curl --fail --silent --show-error "$SAQ_RELEASE_API/api/v1/health"; then
  gcloud run services update-traffic "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --to-revisions="$SAQ_RELEASE_OLD_REVISION=100"
  echo 'Health failed: API traffic restored to the previous revision.' >&2
  exit 1
fi
SAQ_RELEASE_AUTH_STATUS=$(curl --silent --output /dev/null --write-out '%{http_code}' "$SAQ_RELEASE_API/api/v1/me")
if [[ "$SAQ_RELEASE_AUTH_STATUS" != 401 ]]; then
  gcloud run services update-traffic "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --to-revisions="$SAQ_RELEASE_OLD_REVISION=100"
  echo 'Anonymous access check failed: API traffic restored to the previous revision.' >&2
  exit 1
fi
npx --yes firebase-tools@15.34.0 deploy --only hosting --project "$SAQ_RELEASE_PROJECT" --non-interactive
# Updating a job image does not execute the job or issue a paid search/AI request.
if gcloud run jobs describe saq-qurylys-monitor --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --format='value(metadata.name)' >/dev/null 2>&1; then
  gcloud run jobs update saq-qurylys-monitor --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --image="$SAQ_RELEASE_IMAGE"
fi
echo "Published SHA: $SAQ_RELEASE_SHA"
echo "Previous API revision (rollback): $SAQ_RELEASE_OLD_REVISION"
curl --fail --silent --show-error https://saq-qurylys.web.app/release.json
echo
echo 'Open the site, sign in and verify companies, city map, drone photo and signal PDF.'
