"""Stripe payment integration.

Uses Stripe **Checkout (hosted)** so that:
  - card data never touches our server (PCI burden stays with Stripe),
  - the charge amount is computed server-side from DB prices (no client tampering),
  - an order is only marked paid after a **signature-verified** webhook.

The Stripe SDK is synchronous; network calls are run in a worker thread so they
don't block the asyncio event loop.
"""

import asyncio
import os
from typing import Any

import stripe

from config import get_settings

settings = get_settings()


def stripe_enabled() -> bool:
    return bool(settings.stripe_api_key)


def webhook_configured() -> bool:
    return bool(settings.stripe_webhook_secret)


def _configure() -> None:
    stripe.api_key = settings.stripe_api_key
    # In environments behind a TLS-intercepting proxy, honour a configured CA
    # bundle so outbound calls to api.stripe.com validate. No effect on Render
    # (these vars are unset there → Stripe uses its own trusted bundle).
    ca = (
        os.environ.get("STRIPE_CA_BUNDLE")
        or os.environ.get("REQUESTS_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
    )
    if ca and os.path.exists(ca):
        stripe.ca_bundle_path = ca


async def create_checkout_session(
    *,
    order_id: str,
    order_number: str,
    customer_email: str,
    line_items: list[dict[str, Any]],   # [{name, unit_price, quantity}]
    shipping_cost: float,
    base_url: str,
):
    """Create a Stripe Checkout Session and return it. Amounts are in dollars."""
    _configure()

    stripe_line_items = [
        {
            "price_data": {
                "currency": settings.currency,
                "product_data": {"name": li["name"]},
                "unit_amount": int(round(float(li["unit_price"]) * 100)),
            },
            "quantity": int(li["quantity"]),
        }
        for li in line_items
    ]

    if shipping_cost and shipping_cost > 0:
        stripe_line_items.append({
            "price_data": {
                "currency": settings.currency,
                "product_data": {"name": "Shipping"},
                "unit_amount": int(round(float(shipping_cost) * 100)),
            },
            "quantity": 1,
        })

    metadata = {"order_id": order_id, "order_number": order_number}

    return await asyncio.to_thread(
        stripe.checkout.Session.create,
        mode="payment",
        line_items=stripe_line_items,
        customer_email=customer_email or None,
        client_reference_id=order_id,
        metadata=metadata,
        payment_intent_data={"metadata": metadata},
        success_url=f"{base_url}/order/{order_id}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/checkout?canceled=1",
    )


def verify_and_parse_event(payload: bytes, sig_header: str):
    """Verify a webhook signature and return the parsed event. Raises on failure."""
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )


async def get_checkout_session(session_id: str):
    _configure()
    return await asyncio.to_thread(stripe.checkout.Session.retrieve, session_id)
