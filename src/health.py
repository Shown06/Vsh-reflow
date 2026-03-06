"""
Vsh-reflow - ヘルスチェックエンドポイント
各コンテナの /health エンドポイント。
"""

import logging
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

logger = logging.getLogger(__name__)

_start_time = time.time()


class HealthHandler(BaseHTTPRequestHandler):
    """シンプルなヘルスチェックHTTPハンドラー"""

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
                from src.config import settings
                r = redis.Redis(
                    host=settings.redis.host,
                    port=settings.redis.port,
                    socket_timeout=2,
                )
                r.ping()
                response["redis"] = "connected"
            except Exception:
                response["redis"] = "disconnected"

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

        elif self.path == "/metrics":
            # Prometheus メトリクス
            try:
                from prometheus_client import (
                    generate_latest,
                    CONTENT_TYPE_LATEST,
                    Counter,
                    Gauge,
                    Histogram,
                )

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

    def log_message(self, format, *args):
        """ヘルスチェックのアクセスログを抑制"""
        pass


def start_health_server(port: int = 8080):
    """ヘルスチェックHTTPサーバーを起動"""
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"ヘルスチェックサーバー起動: port {port}")
    server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_health_server()
