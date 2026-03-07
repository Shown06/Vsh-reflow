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
                
                # 2. 未登録のエージェントを補完登録
                basic_agents = {
                    "pm": {"name": "PM-Agent", "role": "PM"},
                    "growth": {"name": "Growth-Agent", "role": "GROWTH_HACKER"},
                    "analyst": {"name": "Analyst-Agent", "role": "DATA_ANALYST"},
                    "dev": {"name": "Dev-Agent", "role": "DEVELOPER"},
                    "web": {"name": "Web-Agent", "role": "FRONTEND_ENGINEER"},
                    "design": {"name": "Design-Agent", "role": "UIUX_DESIGNER"},
                    "finance": {"name": "Finance-Agent", "role": "ACCOUNTANT"},
                    "crm": {"name": "CRM-Agent", "role": "SALES_SUPPORT"},
                    "deploy": {"name": "Deploy-Agent", "role": "INFRA_ENGINEER"},
                    "content": {"name": "Content-Agent", "role": "CONTENT_CREATOR"},
                    "browser": {"name": "Browser-Agent", "role": "RESEARCHER"},
                    "email": {"name": "Email-Agent", "role": "SUPPORT_DESK"},
                    "commerce": {"name": "Commerce-Agent", "role": "EC_MANAGER"},
                    "saas": {"name": "SaaS-Agent", "role": "API_INTEGRATOR"},
                    "line": {"name": "LINE-Agent", "role": "SNS_MANAGER"},
                    "schedule": {"name": "Schedule-Agent", "role": "SECRETARY"},
                    "github": {"name": "GitHub-Agent", "role": "QA_ENGINEER"},
                    "pub": {"name": "Pub-Agent", "role": "SECURITY_EXPERT"}
                }

                # 任意: 実際のAGENT_MAPから動的にマッピングを拡張（インポートできれば）
                try:
                    import sys
                    import os
                    sys.path.append(os.getcwd())
                    from src.workers.celery_app import AGENT_MAP
                    # インポート成功時はここでAGENT_MAPから情報を補完可能
                except Exception as e:
                    logger.debug(f"Dynamic agent map import skipped: {e}")

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
                        try:
                            r.set(f"vsh:agent:{info['name']}", json.dumps(idle_data), ex=3600)
                        except Exception as redis_err:
                            logger.error(f"Failed to set redis key for {info['name']}: {redis_err}")

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
