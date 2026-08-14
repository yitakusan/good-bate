"""Optional SMTP email notifications for order-request status changes."""

# ============================================================
# SHARED MODULE
#
# [用途] 申请状态邮件通知（若启用）
# [使用功能] FEATURE: ORDER_REQUEST
# ============================================================

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any, Optional

from app.database import get_conn
from app.settings import get_settings

logger = logging.getLogger("stockgood.notify")


def _smtp_ready() -> bool:
    s = get_settings()
    return bool(s.notify_enabled and s.smtp_host and s.smtp_from)


def _recipient_for_request(row: dict[str, Any]) -> Optional[str]:
    user_id = row.get("user_id")
    if user_id:
        with get_conn() as conn:
            u = conn.execute(
                "SELECT email FROM users WHERE id = ? AND is_active = 1",
                (int(user_id),),
            ).fetchone()
            if u and u["email"]:
                return str(u["email"])
    contact = (row.get("contact") or "").strip()
    if contact and "@" in contact:
        return contact
    return None


def send_email(to_addr: str, subject: str, body: str) -> bool:
    settings = get_settings()
    if not _smtp_ready():
        logger.debug("smtp not configured; skip notify to %s", to_addr)
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or ""
    msg["To"] = to_addr
    msg.set_content(body)
    try:
        if settings.smtp_use_tls:
            with smtplib.SMTP(settings.smtp_host or "", settings.smtp_port, timeout=20) as smtp:
                smtp.starttls()
                if settings.smtp_user and settings.smtp_password:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host or "", settings.smtp_port, timeout=20) as smtp:
                if settings.smtp_user and settings.smtp_password:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        return True
    except Exception:
        logger.exception("failed to send email to %s", to_addr)
        return False


def notify_order_request_status(row: dict[str, Any], event: str) -> None:
    """event: pending_payment | ordered | rejected | submitted"""
    to_addr = _recipient_for_request(row)
    if not to_addr:
        return
    code = row.get("request_code") or ""
    name = row.get("name") or ""
    if event == "ordered":
        subject = f"[Stockgood] 申请 {code} 已下单"
        body = (
            f"您好，您的申请 {code}（{name}）已确认下单。\n"
            f"店铺注文番号：{row.get('shop_order_ref') or '—'}\n"
            f"员工备注：{row.get('staff_note') or '—'}\n"
        )
    elif event == "rejected":
        subject = f"[Stockgood] 申请 {code} 已拒绝"
        body = (
            f"您好，您的申请 {code}（{name}）已被拒绝。\n"
            f"原因：{row.get('reject_reason') or '—'}\n"
        )
    elif event == "pending_payment":
        subject = f"[Stockgood] 申请 {code} 待付定金"
        body = (
            f"您好，申请 {code}（{name}）已创建，请支付 30% 定金后才会正式提交。\n"
            f"定金金额（JPY）：{row.get('deposit_amount') if row.get('deposit_amount') is not None else '—'}\n"
        )
    elif event == "submitted":
        subject = f"[Stockgood] 申请 {code} 已提交"
        body = (
            f"您好，申请 {code}（{name}）定金已确认，订单已提交，请等待处理。\n"
        )
    else:
        return
    send_email(to_addr, subject, body)
