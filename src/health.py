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
            # 全エージェントの状態をRedisから取得
            response = {"agents": []}
            try:
                import redis
                r = redis.Redis.from_url(settings.redis.url)
                
                # エージェントのキーをスキャン
                keys = r.keys("vsh:agent:*")
                for key in keys:
                    data = r.get(key)
                    if data:
                        response["agents"].append(json.loads(data))
                
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
