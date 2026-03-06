#!/bin/bash
# ============================================
# Vsh-reflow - PostgreSQL 自動バックアップスクリプト
# cron で毎日深夜2時に実行: 0 2 * * * /opt/vsh-reflow/scripts/backup.sh
# 30日間保持
# ============================================
set -euo pipefail

BACKUP_DIR="/opt/vsh-reflow/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/vsh-reflow_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=30

# Docker Compose でPostgreSQLを使用
CONTAINER_NAME="vsh-reflow-postgres-1"
DB_NAME="${POSTGRES_DB:-vsh-reflow}"
DB_USER="${POSTGRES_USER:-vsh-reflow}"

echo "📦 バックアップ開始: ${TIMESTAMP}"

# バックアップディレクトリ作成
mkdir -p ${BACKUP_DIR}

# PostgreSQLダンプ（Docker経由）
docker exec ${CONTAINER_NAME} pg_dump -U ${DB_USER} ${DB_NAME} | gzip > ${BACKUP_FILE}

if [ $? -eq 0 ]; then
    FILESIZE=$(du -h ${BACKUP_FILE} | cut -f1)
    echo "✅ バックアップ成功: ${BACKUP_FILE} (${FILESIZE})"
else
    echo "❌ バックアップ失敗"
    exit 1
fi

# 古いバックアップの削除（30日以上前）
echo "🗑 ${RETENTION_DAYS}日以上前のバックアップを削除中..."
find ${BACKUP_DIR} -name "vsh-reflow_*.sql.gz" -mtime +${RETENTION_DAYS} -delete

REMAINING=$(ls -1 ${BACKUP_DIR}/vsh-reflow_*.sql.gz 2>/dev/null | wc -l)
echo "📋 保持中のバックアップ: ${REMAINING}件"
echo "✅ バックアップ完了"
