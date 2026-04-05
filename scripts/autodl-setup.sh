#!/usr/bin/env bash
# autodl-setup.sh — Run on AutoDL to start all services
# Usage: bash autodl-setup.sh
set -euo pipefail

# Ensure miniconda is in PATH (AutoDL uses conda, not system python)
export PATH="/root/miniconda3/bin:$PATH"
# Ensure alpha_agent package is importable without pip install -e
export PYTHONPATH="/root/alpha-agent:${PYTHONPATH:-}"

PROJ_DIR="/root/alpha-agent"
LOG_DIR="/root/alpha-agent/logs"
mkdir -p "$LOG_DIR"

echo "=== Alpha Agent AutoDL Setup ==="

# 1. Start Ollama (if not already running)
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

# Verify Ollama
if curl -sf http://localhost:6006/api/version > /dev/null 2>&1; then
    echo "  Ollama OK"
else
    echo "  WARNING: Ollama not responding on :6006"
fi

# 2. Start Streamlit
if ! pgrep -f "streamlit run" > /dev/null 2>&1; then
    echo "[2/3] Starting Streamlit..."
    cd "$PROJ_DIR"
    nohup python -m streamlit run alpha_agent/ui/app.py \
        --server.port 8501 \
        --server.address 0.0.0.0 \
        --server.headless true \
        > "$LOG_DIR/streamlit.log" 2>&1 &
    sleep 2
    echo "  Streamlit PID: $!"
else
    echo "[2/3] Streamlit already running"
fi

# 3. Start Cloudflare Tunnel
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
echo "  Ollama:     http://localhost:6006"
echo "  Streamlit:  http://localhost:8501"
echo "  Tunnel:     alpha.bobbyzhong.com (via Cloudflare)"
echo ""
echo "Logs in: $LOG_DIR/"
