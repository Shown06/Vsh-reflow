"""
Vsh-reflow - Email-Agent (メール送受信・テンプレート・自動返信)
SMTP送信 + IMAP受信 + SendGrid API 対応。
"""

import logging
import os
import email
import imaplib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)


class EmailAgent(BaseAgent):
    """メール送受信エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.PUB, name="Email-Agent")
        self._smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        self._smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self._smtp_user = os.environ.get("SMTP_USER", "")
        self._smtp_password = os.environ.get("SMTP_PASSWORD", "")
        self._imap_host = os.environ.get("IMAP_HOST", "imap.gmail.com")
        self._imap_port = int(os.environ.get("IMAP_PORT", "993"))
        self._sendgrid_key = os.environ.get("SENDGRID_API_KEY", "")
        self._from_email = os.environ.get("FROM_EMAIL", self._smtp_user)

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "send_email":
            return await self._send_email(task_code, payload)
        elif task_type == "read_emails":
            return await self._read_emails(task_code, payload)
        elif task_type == "draft_email":
            return await self._draft_email(task_code, payload)
        elif task_type == "auto_reply":
            return await self._auto_reply(task_code, payload)
        elif task_type == "send_newsletter":
            return await self._send_newsletter(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _send_email(self, task_code: str, payload: dict) -> dict:
        """メール送信"""
        to_email = payload.get("to", "")
        subject = payload.get("subject", "")
        body = payload.get("body", "")
        html = payload.get("html", False)

        if not to_email or not subject:
            return {"success": False, "error": "宛先とタイトルは必須です"}

        # SendGrid 優先、なければ SMTP
        if self._sendgrid_key:
            return await self._send_via_sendgrid(to_email, subject, body, html)
        elif self._smtp_user:
            return await self._send_via_smtp(to_email, subject, body, html)
        else:
            return {"success": False, "error": "メール送信設定が未設定です（SMTP_USER or SENDGRID_API_KEY）"}

    async def _send_via_smtp(self, to: str, subject: str, body: str, html: bool) -> dict:
        """SMTP経由でメール送信"""
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self._from_email
            msg["To"] = to
            msg["Subject"] = subject

            if html:
                msg.attach(MIMEText(body, "html", "utf-8"))
            else:
                msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                server.starttls()
                server.login(self._smtp_user, self._smtp_password)
                server.send_message(msg)

            return {
                "success": True,
                "result": {
                    "to": to,
                    "subject": subject,
                    "method": "smtp",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                },
                "cost_yen": 0.0,
            }
        except Exception as e:
            return {"success": False, "error": f"SMTP送信エラー: {e}"}

    async def _send_via_sendgrid(self, to: str, subject: str, body: str, html: bool) -> dict:
        """SendGrid API経由でメール送信"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {self._sendgrid_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "personalizations": [{"to": [{"email": to}]}],
                        "from": {"email": self._from_email},
                        "subject": subject,
                        "content": [{"type": "text/html" if html else "text/plain", "value": body}],
                    },
                )
                if response.status_code >= 400:
                    return {"success": False, "error": f"SendGrid Error: {response.text}"}

            return {
                "success": True,
                "result": {
                    "to": to,
                    "subject": subject,
                    "method": "sendgrid",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                },
                "cost_yen": 0.0,
            }
        except Exception as e:
            return {"success": False, "error": f"SendGrid送信エラー: {e}"}

    async def _read_emails(self, task_code: str, payload: dict) -> dict:
        """メール受信（IMAP）"""
        folder = payload.get("folder", "INBOX")
        count = payload.get("count", 10)
        unread_only = payload.get("unread_only", True)

        if not self._smtp_user:
            return {"success": False, "error": "IMAP設定が未設定です"}

        try:
            mail = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
            mail.login(self._smtp_user, self._smtp_password)
            mail.select(folder)

            search_criteria = "UNSEEN" if unread_only else "ALL"
            _, msg_nums = mail.search(None, search_criteria)

            emails = []
            msg_list = msg_nums[0].split()[-count:]  # 最新N件

            for num in reversed(msg_list):
                _, data = mail.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                            break
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

                emails.append({
                    "from": msg.get("From", ""),
                    "subject": msg.get("Subject", ""),
                    "date": msg.get("Date", ""),
                    "body_preview": body[:300],
                })

            mail.logout()

            return {
                "success": True,
                "result": {
                    "emails": emails,
                    "count": len(emails),
                    "folder": folder,
                },
                "cost_yen": 0.0,
            }
        except Exception as e:
            return {"success": False, "error": f"IMAP受信エラー: {e}"}

    async def _draft_email(self, task_code: str, payload: dict) -> dict:
        """LLMでメール文面を生成"""
        purpose = payload.get("purpose", "")
        to_name = payload.get("to_name", "")
        tone = payload.get("tone", "丁寧・ビジネス")
        context = payload.get("context", "")

        result = await self.call_llm(
            prompt=f"""以下の条件でメールの文面を生成してください。

目的: {purpose}
宛先: {to_name}
トーン: {tone}
背景情報: {context}

以下を含めてください:
- 件名
- 本文（挨拶、本題、締め）
- 署名""",
            system_prompt="日本語のビジネスメールのプロとして、適切な敬語と構成でメールを作成してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {
                "draft": result.get("text", ""),
                "note": "📧 この下書きを確認して /approve で送信してください",
            },
            "cost_yen": result.get("cost_yen", 0.0),
            "require_approval": True,
        }

    async def _auto_reply(self, task_code: str, payload: dict) -> dict:
        """受信メールに対する自動返信案を生成"""
        original_email = payload.get("original", "")

        result = await self.call_llm(
            prompt=f"""以下のメールに対する返信文を生成してください。

受信メール:
{original_email}

要件:
- 丁寧なビジネス日本語
- 受信内容に適切に応答
- 必要に応じて追加質問を含める""",
            system_prompt="受信メールの内容を正確に理解し、適切な返信を生成してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {
                "reply_draft": result.get("text", ""),
                "note": "📧 翔の確認後に送信してください",
            },
            "cost_yen": result.get("cost_yen", 0.0),
            "require_approval": True,
        }

    async def _send_newsletter(self, task_code: str, payload: dict) -> dict:
        """ニュースレター生成・送信準備"""
        topic = payload.get("topic", "")
        recipients = payload.get("recipients", [])

        # LLMでニュースレター生成
        result = await self.call_llm(
            prompt=f"""以下のテーマでHTMLニュースレターを生成してください。

テーマ: {topic}

要件:
- レスポンシブなHTMLメール
- ヘッダー画像の代わりにテキストロゴ
- 3-5つのセクション
- CTAボタン
- フッター（配信停止リンク含む）""",
            system_prompt="メールマーケティングのプロとして、開封率とクリック率が高いニュースレターを作成してください。",
            tier=LLMTier.IMPORTANT,
            task_hint="html code",
        )

        return {
            "success": True,
            "result": {
                "newsletter_html": result.get("text", ""),
                "recipients_count": len(recipients),
                "note": "📧 承認後に配信します",
            },
            "cost_yen": result.get("cost_yen", 0.0),
            "require_approval": True,
        }


# エージェントインスタンス
email_agent = EmailAgent()
