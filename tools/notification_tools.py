"""
Customer notification tools (email via Resend).
"""

from typing import Any

import resend

from config import get_settings

settings = get_settings()


def _resend_client() -> None:
    resend.api_key = settings.resend_api_key


async def send_email(to_email: str, subject: str, body_html: str) -> dict[str, Any]:
    """Send an email via Resend. Falls back to logging when API key is unconfigured."""
    if not settings.resend_api_key:
        print(f"[EMAIL] To: {to_email} | Subject: {subject}")
        return {"success": True, "method": "logged", "to": to_email}

    try:
        _resend_client()
        result = resend.Emails.send({
            "from": f"{settings.store_name} <{settings.from_email}>",
            "to": [to_email],
            "subject": subject,
            "html": body_html,
        })
        return {"success": True, "method": "resend", "to": to_email, "id": result.get("id")}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def send_order_confirmation(
    to_email: str,
    customer_name: str,
    order_number: str,
    order_total: float,
    items: list[dict],
) -> dict[str, Any]:
    items_html = "".join(
        f"<tr><td>{i.get('name', 'Product')}</td><td>{i.get('quantity', 1)}</td>"
        f"<td>${i.get('total_price', 0):.2f}</td></tr>"
        for i in items
    )
    body = f"""
    <h2>Order Confirmation – {order_number}</h2>
    <p>Hi {customer_name}, thank you for your order!</p>
    <table border="1" cellpadding="8">
      <tr><th>Item</th><th>Qty</th><th>Price</th></tr>
      {items_html}
      <tr><td colspan="2"><strong>Total</strong></td><td><strong>${order_total:.2f}</strong></td></tr>
    </table>
    <p>We'll send you tracking information once your order ships.</p>
    <p>– {settings.store_name}</p>
    """
    return await send_email(to_email, f"Order Confirmed – {order_number}", body)


async def send_shipping_notification(
    to_email: str,
    customer_name: str,
    order_number: str,
    tracking_number: str,
    tracking_url: str,
) -> dict[str, Any]:
    body = f"""
    <h2>Your order has shipped!</h2>
    <p>Hi {customer_name}, great news – your order {order_number} is on its way.</p>
    <p><strong>Tracking number:</strong> {tracking_number}</p>
    <p><a href="{tracking_url}">Track your package</a></p>
    <p>– {settings.store_name}</p>
    """
    return await send_email(to_email, f"Your order {order_number} has shipped", body)


async def send_refund_notification(
    to_email: str,
    customer_name: str,
    order_number: str,
    refund_amount: float,
) -> dict[str, Any]:
    body = f"""
    <h2>Refund Processed</h2>
    <p>Hi {customer_name}, your refund of <strong>${refund_amount:.2f}</strong>
       for order {order_number} has been processed.</p>
    <p>Please allow 5-10 business days for it to appear on your statement.</p>
    <p>– {settings.store_name}</p>
    """
    return await send_email(to_email, f"Refund processed for {order_number}", body)


class NotificationTools:
    SCHEMAS = [
        {
            "name": "send_order_confirmation",
            "description": "Send order confirmation email to customer.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "to_email": {"type": "string"},
                    "customer_name": {"type": "string"},
                    "order_number": {"type": "string"},
                    "order_total": {"type": "number"},
                    "items": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["to_email", "customer_name", "order_number", "order_total", "items"],
            },
        },
        {
            "name": "send_shipping_notification",
            "description": "Send shipping notification with tracking info to customer.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "to_email": {"type": "string"},
                    "customer_name": {"type": "string"},
                    "order_number": {"type": "string"},
                    "tracking_number": {"type": "string"},
                    "tracking_url": {"type": "string"},
                },
                "required": ["to_email", "customer_name", "order_number", "tracking_number", "tracking_url"],
            },
        },
        {
            "name": "send_refund_notification",
            "description": "Send refund confirmation email to customer.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "to_email": {"type": "string"},
                    "customer_name": {"type": "string"},
                    "order_number": {"type": "string"},
                    "refund_amount": {"type": "number"},
                },
                "required": ["to_email", "customer_name", "order_number", "refund_amount"],
            },
        },
    ]

    MAP = {
        "send_order_confirmation": send_order_confirmation,
        "send_shipping_notification": send_shipping_notification,
        "send_refund_notification": send_refund_notification,
    }
