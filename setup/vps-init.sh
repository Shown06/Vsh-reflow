#!/bin/bash
# ============================================
# Vsh-reflow - ConoHa VPS 初期セットアップスクリプト
# Ubuntu 24.04 LTS 対応
# §5 準拠
# ============================================
set -euo pipefail

echo "🚀 Vsh-reflow VPS 初期セットアップを開始します..."

# -------------------------------------------
# 1. システム更新
# -------------------------------------------
echo "📦 システムを最新に更新中..."
apt-get update && apt-get upgrade -y

# -------------------------------------------
# 2. SSH鍵認証のみ許可 & ポート変更
# -------------------------------------------
SSH_PORT=${SSH_PORT:-2222}
echo "🔐 SSH設定を強化中... (ポート: ${SSH_PORT})"

# バックアップ
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak

# SSH設定変更 (初期セットアップのためパスワード認証を一旦許可)
sed -i "s/#Port 22/Port ${SSH_PORT}/" /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/PermitRootLogin no/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config


systemctl restart sshd
echo "✅ SSH設定完了 (ポート: ${SSH_PORT}, パスワード認証: 有効)"


# -------------------------------------------
# 3. UFW ファイアウォール設定
# -------------------------------------------
echo "🛡 ファイアウォール設定中..."
apt-get install -y ufw

ufw default deny incoming
ufw default allow outgoing
ufw allow ${SSH_PORT}/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable

echo "✅ UFW有効化完了"

# -------------------------------------------
# 4. Fail2ban 設定
# -------------------------------------------
echo "🔒 Fail2ban設定中..."
apt-get install -y fail2ban

cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
ignoreip = 127.0.0.1/8

[sshd]
enabled = true
port = ${SSH_PORT}
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 7200
EOF

systemctl enable fail2ban
systemctl restart fail2ban
echo "✅ Fail2ban設定完了"

# -------------------------------------------
# 5. 自動セキュリティアップデート
# -------------------------------------------
echo "🔄 自動セキュリティアップデート設定中..."
apt-get install -y unattended-upgrades apt-listchanges

cat > /etc/apt/apt.conf.d/50unattended-upgrades << 'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}";
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF

dpkg-reconfigure -plow unattended-upgrades
echo "✅ 自動アップデート設定完了"

# -------------------------------------------
# 6. Docker / Docker Compose インストール
# -------------------------------------------
echo "🐳 Docker インストール中..."

# 古い Docker 削除
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
    apt-get remove -y $pkg 2>/dev/null || true
done

# Docker 公式リポジトリ追加
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Docker の自動起動
systemctl enable docker
systemctl start docker

echo "✅ Docker インストール完了"
docker --version
docker compose version

# -------------------------------------------
# 7. ログローテーション設定
# -------------------------------------------
echo "📋 ログローテーション設定中..."

cat > /etc/logrotate.d/vsh-reflow << 'EOF'
/var/log/vsh-reflow/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 root root
    sharedscripts
}
EOF

mkdir -p /var/log/vsh-reflow
echo "✅ ログローテーション設定完了"

# -------------------------------------------
# 8. プロジェクトディレクトリ作成
# -------------------------------------------
PROJECT_DIR="/opt/vsh-reflow"
echo "📁 プロジェクトディレクトリ作成: ${PROJECT_DIR}"
mkdir -p ${PROJECT_DIR}
mkdir -p ${PROJECT_DIR}/backups

# -------------------------------------------
# 9. swap設定（メモリ最適化）
# -------------------------------------------
echo "💾 Swap設定中..."
if [ ! -f /swapfile ]; then
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab
    echo "✅ Swap 4GB 追加完了"
else
    echo "ℹ️ Swap既に設定済み"
fi

# -------------------------------------------
# 完了
# -------------------------------------------
echo ""
echo "============================================"
echo "🎉 Vsh-reflow VPS 初期セットアップ完了！"
echo "============================================"
echo ""
echo "📋 設定内容:"
echo "   SSH ポート: ${SSH_PORT}"
echo "   パスワード認証: 無効"
echo "   UFW: 有効"
echo "   Fail2ban: 有効"
echo "   Docker: インストール済み"
echo "   自動アップデート: 有効"
echo ""
echo "⚠️ 次のステップ:"
echo "   1. SSH鍵をサーバーに配置済みか確認"
echo "   2. 新しいSSHポート (${SSH_PORT}) で接続テスト"
echo "   3. GitHubからプロジェクトをクローン"
echo "   4. .env ファイルを作成・設定"
echo "   5. docker compose up -d で起動"
echo ""
