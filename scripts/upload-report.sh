#!/usr/bin/env bash
# upload-report.sh — Generate static HTML report and upload to Cloudflare KV
# Usage: bash scripts/upload-report.sh
set -euo pipefail

# Ensure miniconda + alpha_agent are available (needed on AutoDL)
export PATH="/root/miniconda3/bin:${PATH}"
export PYTHONPATH="${PYTHONPATH:-}"

PROJ_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$PROJ_DIR:$PYTHONPATH"
WORKER_DIR="$PROJ_DIR/worker"
REPORT_FILE="$PROJ_DIR/alpha_agent_report.html"

echo "=== Upload Static Report to Cloudflare KV ==="

# Check if report exists; if not, try to generate
if [ ! -f "$REPORT_FILE" ]; then
    echo "No report found. Generating..."
    cd "$PROJ_DIR"
    python -m alpha_agent research "short-term reversal factors for CSI300" --report
fi

if [ ! -f "$REPORT_FILE" ]; then
    echo "ERROR: Failed to generate report at $REPORT_FILE"
    exit 1
fi

echo "Report: $REPORT_FILE ($(wc -c < "$REPORT_FILE") bytes)"

# Upload to KV
cd "$WORKER_DIR"
npx wrangler kv:key put --binding=STATIC_SITE "report.html" --path="$REPORT_FILE"

echo "Uploaded to Cloudflare KV."
echo "Static page live at https://alpha.bobbyzhong.com"
