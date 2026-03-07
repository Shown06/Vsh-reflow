"""
Vsh-reflow - ヘルスチェック & API エンドポイント
各コンテナの /health およびダッシュボード用 /api/agents。
"""

import logging
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime, timezone

from src.config import settings

logger = logging.getLogger(__name__)

_start_time = time.time()


class HealthHandler(BaseHTTPRequestHandler):
    """シンプルなヘルスチェック & エージェントAPIハンドラー"""

    def do_GET(self):
        if self.path == "/health":
            uptime = time.time() - _start_time
            response = {
                "status": "healthy",
                "service": "vsh-reflow",
                "uptime_seconds": round(uptime, 1),
            }

            # Redis接続チェック
            try:
                import redis
                r = redis.Redis.from_url(settings.redis.url)
                r.ping()
                response["redis"] = "connected"
            except Exception:
                response["redis"] = "disconnected"

            self._send_json(response)

        elif self.path == "/api/agents":
            # 全エージェントの状態をRedisから取得し、未登録のエージェントはアイドルとして補完する
            response = {"agents": []}
            try:
                import redis
                from datetime import datetime, timezone
                r = redis.Redis.from_url(settings.redis.url)
                
                # 1. 登録済みエージェントをRedisから取得
                keys = r.keys("vsh:agent:*")
                registered_agents = {}
                for key in keys:
                    data = r.get(key)
                    if data:
                        try:
                            agent_data = json.loads(data)
                            registered_agents[agent_data.get("name")] = agent_data
                            response["agents"].append(agent_data)
                        except json.JSONDecodeError:
                            pass
                
                # 2. 未登録のエージェントをAGENTS_MAPから調べて補完登録
                try:
                    import sys
                    import os
                    # パスを追加してsrcモジュールをインポートできるようにする
                    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    from src.workers.celery_app import AGENT_MAP
                    from src.agents import PM_Agent, GrowthAgent, AnalystAgent, SEAgent, WebAgent, DesignAgent
                    from src.agents import FinanceAgent, CRM_Agent, DeployAgent, ContentAgent, BrowserAgent
                    from src.agents import EmailAgent, CommerceAgent, SaaS_API_Agent, LineAgent, ScheduleAgent
                    from src.agents import GitHubAgent, GuardAgent, TelegramBotAgent, PubCrawlerAgent
                    
                    # 簡易的な名前とロールのマップ（インスタンス化せずに取得）
                    # AGENT_MAPのキーと実際のエージェント情報をマッピング
                    basic_agents = {
                        "pm": {"name": "PM-Agent", "role": "PM"},
                        "growth": {"name": "GrowthAgent", "role": "GROWTH_HACKER"},
                        "analyst": {"name": "AnalystAgent", "role": "DATA_ANALYST"},
                        "dev": {"name": "SEAgent", "role": "DEVELOPER"},
                        "web": {"name": "WebAgent", "role": "FRONTEND_ENGINEER"},
                        "design": {"name": "DesignAgent", "role": "UIUX_DESIGNER"},
                        "finance": {"name": "FinanceAgent", "role": "ACCOUNTANT"},
                        "crm": {"name": "CRM-Agent", "role": "SALES_SUPPORT"},
                        "deploy": {"name": "DeployAgent", "role": "INFRA_ENGINEER"},
                        "content": {"name": "ContentAgent", "role": "CONTENT_CREATOR"},
                        "browser": {"name": "BrowserAgent", "role": "RESEARCHER"},
                        "email": {"name": "EmailAgent", "role": "SUPPORT_DESK"},
                        "commerce": {"name": "CommerceAgent", "role": "EC_MANAGER"},
                        "saas": {"name": "SaaS-API-Agent", "role": "API_INTEGRATOR"},
                        "line": {"name": "LINE-Agent", "role": "SNS_MANAGER"},
                        "schedule": {"name": "ScheduleAgent", "role": "SECRETARY"},
                        "github": {"name": "GitHubAgent", "role": "QA_ENGINEER"},
                        "pub": {"name": "PubCrawlerAgent", "role": "SECURITY_EXPERT"}
                    }

                    for key, info in basic_agents.items():
                        if info["name"] not in registered_agents:
                            # Redisに未登録のエージェントを待機中として書き込み
                            idle_data = {
                                "name": info["name"],
                                "role": info["role"],
                                "status": "idle",
                                "task": "",
                                "thought": "システム再構成完了。待機しています。",
                                "last_seen": datetime.now(timezone.utc).isoformat()
                            }
                            # レスポンスにも追加
                            response["agents"].append(idle_data)
                            # Redisにも登録（次回以降のため）
                            r.set(f"vsh:agent:{info['name']}", json.dumps(idle_data), ex=3600)  # 1時間保持

                except Exception as map_err:
                    print(f"Agent map iteration error: {map_err}") # ログ出力

                status_code = 200
            except Exception as e:
                response = {"error": str(e)}
                status_code = 500


            self._send_json(response, status_code)

        elif self.path == "/metrics":
            # Prometheus メトリクス
            try:
                from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.end_headers()
                self.wfile.write(generate_latest())
            except ImportError:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"# prometheus_client not installed\n")
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data, status=200):
        """JSONレスポンス送信ヘルパー"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        """ヘルスチェックのアクセスログを抑制"""
        pass


def start_health_server(port: int = 8080):
    """ヘルスチェックHTTPサーバーを起動"""
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"API/Healthサーバー起動: port {port}")
    server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_health_server()
