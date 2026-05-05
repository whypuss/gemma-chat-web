#!/bin/bash
# llama-server watchdog — auto-restart if stuck or OOM
# Run: nohup bash ~/watchdog_llama.sh >> ~/watchdog.log 2>&1 &

LOG=/data/data/com.termux/files/home/watchdog.log
PIDFILE=/data/data/com.termux/files/home/llama.pid
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
        > /data/data/com.termux/files/home/llama.log 2>&1 &
    echo $! > "$PIDFILE"
    log "llama-server started PID=$(cat $PIDFILE)"
}

health_check() {
    RESP=$(curl -s --connect-timeout 5 --max-time 8 http://127.0.0.1:$PORT/v1/models 2>/dev/null)
    if echo "$RESP" | grep -q "models"; then
        return 0
    fi
    return 1
}

# Initial start
log "=== Watchdog starting ==="
start_llama

# Wait for first load (max 60s)
log "Waiting for initial model load..."
LOADED=0
for i in $(seq 1 30); do
    sleep 2
    if health_check; then
        SECS=$((i * 2))
        log "Model ready after ${SECS}s"
        LOADED=1
        break
    fi
done

if [ "$LOADED" -eq 0 ]; then
    log "FAIL: model didn't load after 60s"
    kill $(cat $PIDFILE) 2>/dev/null
    exit 1
fi

# Main loop — check every 30s
log "Watchdog active"
while true; do
    sleep 30

    # Process alive?
    if ! kill -0 $(cat $PIDFILE) 2>/dev/null; then
        log "WARN: llama-server died. Restarting..."
        start_llama
        sleep 30
        continue
    fi

    # Health check
    if ! health_check; then
        log "WARN: health check FAILED. Restarting..."
        kill $(cat $PIDFILE) 2>/dev/null
        sleep 3
        RESTART_COUNT=$((RESTART_COUNT + 1))
        if [ "$RESTART_COUNT" -gt "$MAX_RESTARTS" ]; then
            log "ERROR: too many restarts. Exiting."
            exit 1
        fi
        start_llama
        sleep 30
    fi

    log "OK at $(date '+%H:%M:%S')"
done
