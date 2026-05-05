#!/bin/bash
# Kill old tunnels and CORS proxy
pkill -f "python3 cors_proxy" 2>/dev/null
pkill -f "localhost.run" 2>/dev/null
pkill -f "serveo.net" 2>/dev/null
sleep 2

cd /data/data/com.termux/files/home

# Start CORS proxy with chat UI
nohup python3 cors_proxy.py > cors_proxy.log 2>&1 &
echo "CORS PID=$!"

# Start localhost.run tunnel -> port 18080 (CORS proxy with chat UI)
nohup ssh -i .ssh/id_ed25519 \
  -o StrictHostKeyChecking=no \
  -o ServerAliveInterval=30 \
  -R 80:localhost:18080 \
  plan@localhost.run \
  >> localhost_chat.log 2>&1 &
echo "Tunnel PID=$!"

sleep 6
echo "--- CORS log ---"
tail -3 cors_proxy.log
echo "--- Tunnel log ---"
cat localhost_chat.log | tail -5
