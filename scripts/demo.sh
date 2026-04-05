#!/usr/bin/env bash
# demo.sh — One-command control for Alpha Agent demo
#
# Usage:
#   ./scripts/demo.sh start   — SSH to AutoDL, start all services, go live
#   ./scripts/demo.sh stop    — Kill services on AutoDL, revert to static
#   ./scripts/demo.sh status  — Check if live or static
#   ./scripts/demo.sh update  — Regenerate static report and upload to KV
set -euo pipefail

AUTODL_HOST="autodl"
AUTODL_SSH="sshpass -p cUermfx6OOrg ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no -p 38394 root@connect.westd.seetacloud.com"
LIVE_URL="https://alpha.bobbyzhong.com"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJ_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

_check_live() {
    local mode
    mode=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 3 "$LIVE_URL" 2>/dev/null || echo "000")
    local header
    header=$(curl -sf -I --max-time 3 "$LIVE_URL" 2>/dev/null | grep -i "x-alpha-mode" | tr -d '\r' || echo "")
    echo "$mode|$header"
}

case "${1:-help}" in
    start)
        echo "=== Starting Alpha Agent Demo ==="
        echo ""
        echo "[1/3] Syncing code to AutoDL..."
        rsync -avz --exclude='data/parquet/' --exclude='*.pyc' --exclude='__pycache__' --exclude='.git/' --exclude='.wrangler/' \
            -e "sshpass -p cUermfx6OOrg ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no -p 38394" \
            "$PROJ_DIR/" root@connect.westd.seetacloud.com:/root/alpha-agent/

        echo ""
        echo "[2/3] Starting services on AutoDL..."
        $AUTODL_SSH "bash /root/alpha-agent/scripts/autodl-setup.sh"

        echo ""
        echo "[3/3] Waiting for tunnel to come up..."
        for i in $(seq 1 15); do
            result=$(_check_live)
            if echo "$result" | grep -qi "live"; then
                echo ""
                echo "LIVE at $LIVE_URL"
                exit 0
            fi
            printf "."
            sleep 2
        done
        echo ""
        echo "WARNING: Tunnel not detected yet. Services may still be starting."
        echo "Check: $LIVE_URL"
        echo "Or run: ./scripts/demo.sh status"
        ;;

    stop)
        echo "=== Stopping Alpha Agent Demo ==="
        $AUTODL_SSH "pkill -f cloudflared || true; pkill -f streamlit || true; pkill -f 'ollama serve' || true"
        echo "Services stopped. Site will fall back to static report."
        echo ""
        echo "IMPORTANT: Go to AutoDL console and STOP the instance to save costs!"
        echo "https://www.autodl.com/console"
        ;;

    status)
        echo "=== Alpha Agent Status ==="
        result=$(_check_live)
        code=$(echo "$result" | cut -d'|' -f1)
        header=$(echo "$result" | cut -d'|' -f2)

        if echo "$header" | grep -qi "live"; then
            echo "Mode: LIVE (Streamlit via Cloudflare Tunnel)"
        elif [ "$code" = "200" ]; then
            echo "Mode: STATIC (serving pre-generated report)"
        elif [ "$code" = "503" ]; then
            echo "Mode: OFFLINE (no static report uploaded)"
        else
            echo "Mode: UNREACHABLE (HTTP $code)"
        fi
        echo "URL: $LIVE_URL"
        ;;

    update)
        echo "=== Updating Static Report ==="
        bash "$SCRIPT_DIR/upload-report.sh"
        ;;

    *)
        echo "Usage: $0 {start|stop|status|update}"
        echo ""
        echo "  start   — Boot AutoDL services and go live"
        echo "  stop    — Kill services, revert to static page"
        echo "  status  — Check current mode (live/static/offline)"
        echo "  update  — Regenerate and upload static report"
        exit 1
        ;;
esac
