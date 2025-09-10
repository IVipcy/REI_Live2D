#!/bin/bash

# WebSocketサポートのためのNginx設定を追加
cat > /etc/nginx/conf.d/websocket_upgrade.conf <<'EOF'
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

upstream websocket {
    server 127.0.0.1:5000;
}
EOF

echo "WebSocket設定を追加しました" 