#!/usr/bin/env bash
# autodl-setup.sh — Run on AutoDL to start all services
# Usage: bash autodl-setup.sh
set -euo pipefail

# ── Environment ──────────────────────────────────────────────────
export PATH="/root/miniconda3/bin:$PATH"
export PYTHONPATH="/root/alpha-agent:${PYTHONPATH:-}"
# CRITICAL: Override .env so Streamlit/pydantic-settings uses port 6006
export OLLAMA_BASE_URL="http://localhost:6006"

PROJ_DIR="/root/alpha-agent"
LOG_DIR="$PROJ_DIR/logs"
mkdir -p "$LOG_DIR"

echo "=== Alpha Agent AutoDL Setup ==="
echo "  OLLAMA_BASE_URL=$OLLAMA_BASE_URL"
echo ""

# ── 1. Ollama ────────────────────────────────────────────────────
if ! pgrep -x ollama > /dev/null 2>&1; then
    echo "[1/3] Starting Ollama..."
    export OLLAMA_HOST=0.0.0.0:6006
    export OLLAMA_MODELS=/root/autodl-tmp/ollama/models
    nohup ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
    sleep 3
    echo "  Ollama PID: $!"
else
    echo "[1/3] Ollama already running"
fi
curl -sf http://localhost:6006/api/version > /dev/null 2>&1 \
    && echo "  Ollama OK" \
    || echo "  WARNING: Ollama not responding on :6006"

# ── 2. Streamlit (always restart to pick up new code) ────────────
if pgrep -f "streamlit run" > /dev/null 2>&1; then
    echo "[2/3] Restarting Streamlit (picking up new code)..."
    pkill -f "streamlit run" 2>/dev/null || true
    sleep 2
else
    echo "[2/3] Starting Streamlit..."
fi
cd "$PROJ_DIR"
nohup /root/miniconda3/bin/python -m streamlit run alpha_agent/ui/app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    > "$LOG_DIR/streamlit.log" 2>&1 &
sleep 2
echo "  Streamlit PID: $!"

# ── 3. Cloudflare Tunnel ─────────────────────────────────────────
if ! pgrep -x cloudflared > /dev/null 2>&1; then
    echo "[3/3] Starting Cloudflare Tunnel..."
    nohup cloudflared tunnel run alpha-agent \
        > "$LOG_DIR/cloudflared.log" 2>&1 &
    sleep 2
    echo "  cloudflared PID: $!"
else
    echo "[3/3] cloudflared already running"
fi

echo ""
echo "=== All services started ==="
echo "  OLLAMA_BASE_URL=$OLLAMA_BASE_URL"
echo "  Streamlit:  http://localhost:8501"
echo "  Tunnel:     alpha.bobbyzhong.com (via Cloudflare)"
echo ""
echo "Logs in: $LOG_DIR/"
