"""寄信(SMTP)與 LINE Messaging API 推播。第三方呼叫只放這裡。"""

import smtplib
import ssl
from email.message import EmailMessage

import httpx
from loguru import logger

from app.common.core.retry import retry_external
from app.common.exceptions import ExternalAPIException

_LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
_TIMEOUT_SECONDS = 10.0


class SmtpMailer:
    """stdlib smtplib。host 未設定時只寫 log(本機開發、測試不會寄出真信)。"""

    def __init__(self, host: str, port: int, username: str, password: str, from_email: str) -> None:
        self.host, self.port, self.username, self.password, self.from_email = host, port, username, password, from_email

    def send(self, to: list[str], subject: str, body: str) -> None:
        if not self.host:
            logger.info(f"[External] SMTP not configured, skip - recipients: {len(to)}")
            return
        message = EmailMessage()
        message["Subject"], message["From"], message["To"] = subject, self.from_email, ", ".join(to)
        message.set_content(body)
        context = ssl.create_default_context()
        try:
            if self.port == 465:  # implicit TLS
                with smtplib.SMTP_SSL(self.host, self.port, timeout=30, context=context) as server:
                    self._deliver(server, message)
            else:  # 587 STARTTLS
                with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                    server.starttls(context=context)
                    self._deliver(server, message)
        except (smtplib.SMTPException, OSError) as e:
            logger.warning(f"[External] SMTP send failed - recipients: {len(to)}, error_type: {type(e).__name__}")
            raise ExternalAPIException("通知信寄送失敗") from e
        logger.info(f"[External] Email sent - recipients: {len(to)}")

    def _deliver(self, server: smtplib.SMTP, message: EmailMessage) -> None:
        if self.username:
            server.login(self.username, self.password)
        server.send_message(message)


class LineMessagingClient:
    """LINE Messaging API push。token 未設定時只寫 log。"""

    def __init__(self, channel_access_token: str) -> None:
        self.token = channel_access_token

    def push(self, to: str, messages: list[dict], retry_key: str) -> None:
        """retry_key 是 LINE 的 X-Line-Retry-Key:同一則通知重送時帶同一個 key,LINE 不會重複推播。"""
        if not self.token:
            logger.info("[External] LINE not configured, skip push")
            return
        try:
            self._post(to, messages, retry_key)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 409:  # 同一個 retry key 已經成功送過
                logger.info("[External] LINE push already accepted (409 retry key)")
                return
            logger.warning(f"[External] LINE push failed - status: {status}")
            raise ExternalAPIException(f"LINE 推播失敗(HTTP {status})") from e
        logger.info("[External] LINE push sent")

    @retry_external("LINE", retry_on=(httpx.TransportError,))
    def _post(self, to: str, messages: list[dict], retry_key: str) -> None:
        resp = httpx.post(
            _LINE_PUSH_URL,
            headers={"Authorization": f"Bearer {self.token}", "X-Line-Retry-Key": retry_key},
            json={"to": to, "messages": messages},
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
