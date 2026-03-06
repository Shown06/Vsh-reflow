#!/bin/bash
IP="133.117.73.142"
PORT="443"

echo "📡 サーバー($IP:$PORT)に接続してセットアップを開始します..."
scp -P $PORT setup/vps-init.sh root@$IP:/root/
ssh -p $PORT root@$IP "export SSH_PORT=443 && bash /root/vps-init.sh"

echo "📦 プロジェクトファイルをデプロイします..."
ssh -p $PORT root@$IP "mkdir -p /opt/vsh-reflow"
scp -P $PORT -r ./.env ./docker-compose.yml ./Dockerfile* ./requirements.txt ./src ./scripts ./monitoring root@$IP:/opt/vsh-reflow/

echo "🚀 Dockerコンテナを起動します..."
ssh -p $PORT root@$IP "cd /opt/vsh-reflow && docker compose up -d"
echo "✅ デプロイ完了！"
