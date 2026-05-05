#!/bin/bash
# Kill everything
pkill -f cloudflared 2>/dev/null
pkill -f "cors_proxy" 2>/dev/null
sleep 2

cd /data/data/com.termux/files/home

# Install new CORS proxy
mv cors_proxy_v5.py.new cors_proxy.py

# Start new CORS proxy
nohup python3 cors_proxy.py > cors_proxy.log 2>&1 &
echo "CORS PID=$!"
sleep 3

# Verify CORS proxy is up
curl -s --connect-timeout 3 http://localhost:18080/v1/search?q=hello | python3 -c "import sys,json; d=json.load(sys.stdin); print('Search OK:', len(d.get('results',[])), 'results')"

# Start cloudflared pointing to CORS proxy (:18080)
nohup /data/data/com.termux/files/usr/bin/cloudflared tunnel --url http://localhost:18080 > cf.log 2>&1 &
echo "Cloudflared PID=$!"
sleep 10

# Get tunnel URL
TUNNEL_URL=$(grep -o "https://[^ ]*trycloudflare.com" /data/data/com.termux/files/home/cf.log | head -1)
echo "Tunnel URL: $TUNNEL_URL"

# Test
curl -s --connect-timeout 5 "$TUNNEL_URL/v1/search?q=macau+weather" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Tunnel search OK:', len(d.get('results',[])), 'results')"
