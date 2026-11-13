"""通知用的純函式:LINE webhook 簽章驗證、開發環境標題。"""

import base64
import hashlib
import hmac


def line_signature(body: bytes, channel_secret: str) -> str:
    """LINE 的簽章:base64(HMAC-SHA256(channel_secret, 原始 request body))。"""
    digest = hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def verify_line_signature(body: bytes, signature: str | None, channel_secret: str) -> bool:
    """secret 未設定一律不通過:空字串當 HMAC 金鑰,任何人都算得出簽章。compare_digest 防時序攻擊。"""
    if not channel_secret or not signature:
        return False
    return hmac.compare_digest(line_signature(body, channel_secret).encode(), signature.encode())


def subject_for_env(subject: str, is_prod: bool) -> str:
    """非正式環境寄出的信標題加 [DEV],免得跟正式環境的通知搞混。"""
    return subject if is_prod else f"[DEV] {subject}"
