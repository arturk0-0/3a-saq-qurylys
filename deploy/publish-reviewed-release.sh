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
for SAQ_RELEASE_TOOL in gcloud node npm curl python3; do
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
SAQ_RELEASE_TEMP=$(mktemp -d)
trap 'rm -rf "$SAQ_RELEASE_TEMP"' EXIT
gcloud run services describe "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --format='json(status.traffic)' > "$SAQ_RELEASE_TEMP/traffic.json"
SAQ_RELEASE_OLD_REVISION=$(python3 - "$SAQ_RELEASE_TEMP/traffic.json" <<'PY'
import json,sys
traffic = [r for r in json.load(open(sys.argv[1]))['status']['traffic'] if r.get('percent', 0)]
if len(traffic) != 1 or traffic[0]['percent'] != 100 or not traffic[0].get('revisionName'):
    sys.exit('Release stopped: this helper requires one active revision at 100%; preserve/review split traffic separately.')
print(traffic[0]['revisionName'])
PY
)
SAQ_RELEASE_API=$(gcloud run services describe "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --format='value(status.url)')

# Build the normal Hosting entry, never the local demonstration configuration.
node deploy/write-hosting-config.mjs "$SAQ_RELEASE_API"
(cd frontend && npm ci && npm run build:hosting)
node --input-type=module - "$SAQ_RELEASE_SHA" <<'JS'
import { writeFile } from 'node:fs/promises'
await writeFile('frontend/dist/release.json', JSON.stringify({ gitSha: process.argv[2], builtAt: new Date().toISOString() }) + '\n')
JS
npx --yes firebase-tools@15.34.0 deploy --only firestore:indexes --project "$SAQ_RELEASE_PROJECT" --non-interactive
SAQ_RELEASE_INDEX_READY=false
for SAQ_RELEASE_ATTEMPT in {1..60}; do
  gcloud firestore indexes composite list --project="$SAQ_RELEASE_PROJECT" --database='(default)' --format=json > "$SAQ_RELEASE_TEMP/indexes.json"
  if python3 deploy/check-index-readiness.py "$SAQ_RELEASE_TEMP/indexes.json"; then
    SAQ_RELEASE_INDEX_READY=true
    break
  fi
  sleep 10
done
if [[ "$SAQ_RELEASE_INDEX_READY" != true ]]; then
  echo 'Required indexes are not READY: API and Hosting were not changed. Retry after index creation finishes.' >&2
  exit 1
fi
gcloud builds submit . --project="$SAQ_RELEASE_PROJECT" --config=deploy/cloudbuild.yaml --substitutions="_IMAGE=$SAQ_RELEASE_IMAGE"

# Change only the image and release label. Preserve secrets, model, identity and limits.
gcloud run services update "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --image="$SAQ_RELEASE_IMAGE" --update-labels="saq-git-sha=$SAQ_RELEASE_SHA" --no-traffic
SAQ_RELEASE_NEW_REVISION=$(gcloud run services describe "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --format='value(status.latestReadyRevisionName)')
if [[ -z "$SAQ_RELEASE_NEW_REVISION" || "$SAQ_RELEASE_NEW_REVISION" == "$SAQ_RELEASE_OLD_REVISION" ]]; then
  echo 'New API revision was not identified. Traffic has not been changed.' >&2
  exit 1
fi
if ! gcloud run services update-traffic "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --to-revisions="$SAQ_RELEASE_NEW_REVISION=100"; then
  gcloud run services update-traffic "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --to-revisions="$SAQ_RELEASE_OLD_REVISION=100"
  echo 'Traffic promotion failed: attempted restoration of the previous revision.' >&2
  exit 1
fi
if ! curl --fail --silent --show-error "$SAQ_RELEASE_API/api/v1/health"; then
  gcloud run services update-traffic "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --to-revisions="$SAQ_RELEASE_OLD_REVISION=100"
  echo 'Health failed: API traffic restored to the previous revision.' >&2
  exit 1
fi
if ! SAQ_RELEASE_AUTH_STATUS=$(curl --silent --output /dev/null --write-out '%{http_code}' "$SAQ_RELEASE_API/api/v1/me"); then
  gcloud run services update-traffic "$SAQ_RELEASE_SERVICE" --project="$SAQ_RELEASE_PROJECT" --region="$SAQ_RELEASE_REGION" --to-revisions="$SAQ_RELEASE_OLD_REVISION=100"
  echo 'Auth smoke transport failed: API traffic restored to the previous revision.' >&2
  exit 1
fi
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
curl --fail --silent --show-error -H 'Cache-Control: no-cache' "https://saq-qurylys.web.app/release.json?sha=$SAQ_RELEASE_SHA" > "$SAQ_RELEASE_TEMP/published.json"
python3 - "$SAQ_RELEASE_TEMP/published.json" "$SAQ_RELEASE_SHA" <<'PY'
import json,sys
actual=json.load(open(sys.argv[1]))['gitSha']
if actual != sys.argv[2]:sys.exit('Published Hosting SHA does not match this checkout.')
print('Hosting SHA verified:',actual)
PY
echo
echo 'Open the site, sign in and verify companies, city map, drone photo and signal PDF.'
