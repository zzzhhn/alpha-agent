#!/usr/bin/env bash
# Deploy to Vercel preview + verify per spec §6.8 (CLAUDE.md 部署地面真相三板斧)
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "==> deploying to vercel preview"
DEPLOY_OUT=$(vercel deploy --yes 2>&1)
URL=$(echo "$DEPLOY_OUT" | grep -oE 'https://[a-z0-9.-]+\.vercel\.app' | head -1)
if [[ -z "$URL" ]]; then
    echo "ERROR: failed to extract URL from vercel deploy output:"
    echo "$DEPLOY_OUT"
    exit 1
fi
echo "==> preview URL: $URL"

echo "==> 1. backend liveness (Content-Type JSON)"
HEALTH_CT=$(curl -fsI "$URL/api/_health" | grep -i 'content-type' | tr -d '\r')
if ! echo "$HEALTH_CT" | grep -qi 'application/json'; then
    echo "FAIL: $URL/api/_health did not return JSON. Got: $HEALTH_CT"
    exit 1
fi

echo "==> 2. route completeness (openapi paths)"
PATH_COUNT=$(curl -fs "$URL/api/openapi.json" | jq '.paths | keys | length')
if [[ "$PATH_COUNT" -lt 6 ]]; then
    echo "FAIL: expected >=6 OpenAPI paths, got $PATH_COUNT"
    exit 1
fi

echo "==> 3. picks.lean smoke"
curl -fs "$URL/api/picks/lean?limit=1" | jq -e '.picks' > /dev/null

echo "==> 4. health.signals smoke (10 rows)"
ROWS=$(curl -fs "$URL/api/_health/signals" | jq '.signals | length')
[[ "$ROWS" -eq 10 ]] || { echo "FAIL: expected 10 signal rows, got $ROWS"; exit 1; }

echo "M2 deploy + three-pillar verification PASS at $URL"
