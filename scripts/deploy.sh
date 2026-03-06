#!/bin/bash
# ============================================
# Vsh-reflow - デプロイスクリプト
# GitHub Actions または手動で実行
# ============================================
set -euo pipefail

PROJECT_DIR="/opt/vsh-reflow"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

echo "🚀 Vsh-reflow デプロイ開始..."

cd ${PROJECT_DIR}

# 最新コードを取得
echo "📥 最新コードを取得中..."
git pull origin main

# Dockerイメージのビルド
echo "🐳 Dockerイメージをビルド中..."
docker compose build --no-cache

# 古いコンテナを停止・新しいコンテナを起動
echo "🔄 サービスを再起動中..."
docker compose down
docker compose up -d

# ヘルスチェック
echo "🏥 ヘルスチェック中..."
sleep 10
curl -sf http://localhost:8080/health && echo " ✅ Bot Hub正常" || echo " ⚠️ Bot Hub応答なし"

# 古いDockerイメージをクリーンアップ
echo "🗑 不要なDockerイメージをクリーンアップ..."
docker image prune -f

echo "✅ デプロイ完了！"
docker compose ps
