# Vsh-reflow 🚀

**AI社内チーム自律運用システム** — AIチームがSNS運用・競合調査・画像生成・マーケティングをすべて自律実行。重要判断のみ人間が承認。

## クイックスタート

```bash
# 1. 環境変数設定
cp .env.example .env
# .env を編集してAPIキーを設定

# 2. Docker起動
docker compose up -d

# 3. ステータス確認
docker compose ps
```

## アーキテクチャ

```
翔 → Discord/Telegram → Bot Hub → Task Queue (Redis+Celery)
                                        │
                    ┌───────────────────┼────────────────────┐
                    ▼                   ▼                    ▼
              Research Worker    Creative Worker      Publisher Worker
              (Growth-Agent)    (Content/Design)     (Pub-Agent)
                    │                   │                    │
                    ▼                   ▼                    │
              外部API群           画像生成API            SNS API
```

## AIエージェント一覧

| ロール | 名前 | 機能 |
|--------|------|------|
| PM / 議長 | PM-Agent | 会議進行・タスク割当・承認申請書作成 |
| グロースマーケター | Growth-Agent | トレンド調査・企画立案・戦略提案 |
| コンテンツクリエイター | Content-Agent | テキスト・コピー生成（3案提出） |
| デザイナー | Design-Agent | 画像生成（DALL-E 3 / fal.ai） |
| アナリスト | Analyst-Agent | パフォーマンス分析・週次レポート |
| コンプライアンス | Guard-Agent | コスト監視・リスク審査・STOP権限 |
| パブリッシャー | Pub-Agent | 承認後の投稿実行 |

## Discordコマンド

| コマンド | 説明 |
|----------|------|
| `/idea [テーマ]` | アイデア出し・企画立案 |
| `/research [キーワード]` | 競合・トレンド調査 |
| `/draft [プラットフォーム] [テーマ]` | 投稿下書き生成 |
| `/image [説明]` | 画像生成 |
| `/approve [タスクID]` | タスク承認 |
| `/reject [タスクID] [理由]` | タスク却下 |
| `/edit [タスクID] [修正指示]` | 修正指示 |
| `/status` | システム状態確認 |
| `/budget` | コスト確認 |
| `/meeting [テーマ]` | AI会議招集 |
| `/stop` | 緊急停止 |
| `/report` | 週次レポート |

## コスト管理

月額予算: **¥30,000** (自動制御)

| 閾値 | アクション |
|------|-----------|
| ¥20,000 | Discord通知（注意） |
| ¥25,000 | Discord+Telegram通知 + 低コストモード |
| ¥29,000 | タスク受付停止 + 緊急承認要求 |

## VPSデプロイ

```bash
# ConoHa VPS 初期セットアップ
sudo bash setup/vps-init.sh

# プロジェクトデプロイ
bash scripts/deploy.sh
```

## テスト

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

## 技術スタック

- **言語**: Python 3.12
- **Bot**: discord.py / python-telegram-bot
- **タスクキュー**: Redis + Celery
- **DB**: PostgreSQL
- **コンテナ**: Docker + Docker Compose
- **LLM**: OpenAI GPT-4o / Anthropic Claude
- **画像生成**: DALL-E 3 / fal.ai
- **監視**: Prometheus + Grafana
- **CI/CD**: GitHub Actions

---

**© 2026 株式会社EM / Vsh-reflow Project**
