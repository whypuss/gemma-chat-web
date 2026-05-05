#!/data/data/com.termux/files/usr/bin/bash
# Auto-restart watchdog for llama-server (context=2048), CORS proxy, and serveo tunnel
LOG=/data/data/com.termux/files/home/watchdog.log
MODEL=/data/data/com.termux/files/home/models/gemma-2-2b-it-abliterated-Q4_K_M.gguf
PORT=8080
MAX_RESTARTS=10
RESTART_COUNT=0

log() { echo "[$(date '+%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

start_llama() {
    killall llama-server 2>/dev/null
    sleep 2
    nohup /data/data/com.termux/files/usr/bin/llama-server \
        -m "$MODEL" \
        --host 127.0.0.1 \
        --port $PORT \
        -ngl 0 \
        -c 2048 \
        -tb 2 \
        -ub 2 \
        -np 1 \
        -t 2 \
        --no-warmup \
        >> /data/data/com.termux/files/home/llama.log 2>&1 &
    echo $! > /data/data/com.termux/files/home/llama.pid
    log "llama-server started PID=$(cat /data/data/com.termux/files/home/llama.pid)"
}

health_check() {
    RESP=$(curl -s --connect-timeout 5 --max-time 8 http://127.0.0.1:$PORT/v1/models 2>/dev/null)
    if echo "$RESP" | grep -q "models"; then
        return 0
    fi
    return 1
}

log "Watchdog started"

while true; do

    # ── llama-server ──────────────────────────────────────
    if ! pgrep -f "llama-server.*gemma" > /dev/null 2>&1; then
        log "llama-server not running, starting..."
        start_llama
        sleep 5
        if health_check; then
            log "llama-server healthy"
        else
            log "WARN: llama-server unhealthy after start"
        fi
    else
        if ! health_check; then
            log "WARN: llama-server died. Restarting..."
            start_llama
            sleep 5
        fi
    fi

    # ── CORS proxy ────────────────────────────────────────
    if ! pgrep -f "cors_proxy" > /dev/null 2>&1; then
        log "cors_proxy not running, starting..."
        killall python3 2>/dev/null
        sleep 1
        nohup python3 /data/data/com.termux/files/home/cors_proxy.py \
            >> /data/data/com.termux/files/home/cors.log 2>&1 &
        sleep 2
        log "cors_proxy started"
    fi

    # ── serveo tunnel (moggy subdomain) ──────────────────
    if ! pgrep -f "serveo.net" > /dev/null 2>&1; then
        log "serveo tunnel not running, starting..."
        nohup ssh -i /data/data/com.termux/files/home/.ssh/id_ed25519 \
            -o StrictHostKeyChecking=no \
            -o ServerAliveInterval=30 \
            -R moggy:80:localhost:18080 \
            serveo.net \
            >> /data/data/com.termux/files/home/serveo.log 2>&1 &
        sleep 12
        if pgrep -f "serveo.net" > /dev/null 2>&1; then
            log "serveo tunnel started"
        fi
    fi

    sleep 30

done
