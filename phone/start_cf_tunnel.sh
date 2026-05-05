#!/bin/bash
# Kill any existing cloudflared
pkill -f "cloudflared" 2>/dev/null
sleep 1

cd /data/data/com.termux/files/home

# Start cloudflared tunnel in background, output tunnel URL to file
nohup /data/data/com.termux/files/usr/bin/cloudflared tunnel --url http://localhost:8080 > cf_tunnel_url.txt 2>&1 &
CF_PID=$!
echo "Cloudflared PID=$CF_PID"

# Wait for URL to appear
sleep 8
TUNNEL_URL=$(cat cf_tunnel_url.txt | grep "https://.*trycloudflare.com" | head -1 | awk '{print $NF}')
echo "Tunnel URL: $TUNNEL_URL"

# Quick test
curl -s --connect-timeout 5 "$TUNNEL_URL/v1/models" | head -3
