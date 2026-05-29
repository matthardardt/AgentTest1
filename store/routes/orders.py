import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    AsyncSessionLocal, Customer, Order, OrderItem, OrderStatus,
    Product, ProductStatus, get_db,
)
from store import payments
from store.shipping import compute_shipping

log = logging.getLogger("orders")

router = APIRouter()


class ShippingAddress(BaseModel):
    name: str
    address_line1: str
    address_line2: str = ""
    city: str
    state: str
    country: str
    postal_code: str
    phone: str = ""


class CartItem(BaseModel):
    product_id: str
    quantity: int = 1


class CreateOrderRequest(BaseModel):
    email: str
    shipping_address: ShippingAddress
    items: list[CartItem]


def _base_url(request: Request) -> str:
    """Absolute base URL for building Stripe redirect links.

    Render terminates TLS at its proxy, so force https for non-local hosts even
    if the upstream request looks like http.
    """
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://") and not any(
        h in base for h in ("localhost", "127.0.0.1")
    ):
        base = "https://" + base[len("http://"):]
    return base


@router.post("/")
async def create_order(body: CreateOrderRequest, request: Request, db: AsyncSession = Depends(get_db)):
    if not body.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Upsert customer
    cust_result = await db.execute(select(Customer).where(Customer.email == body.email))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        customer = Customer(
            email=body.email,
            name=body.shipping_address.name,
            phone=body.shipping_address.phone,
            address_line1=body.shipping_address.address_line1,
            city=body.shipping_address.city,
            state=body.shipping_address.state,
            country=body.shipping_address.country,
            postal_code=body.shipping_address.postal_code,
        )
        db.add(customer)
        await db.flush()

    # Validate products and compute totals from AUTHORITATIVE DB prices.
    subtotal = 0.0
    line_items = []
    for ci in body.items:
        if ci.quantity < 1:
            raise HTTPException(status_code=400, detail="Invalid quantity")
        prod_result = await db.execute(select(Product).where(Product.id == ci.product_id))
        product = prod_result.scalar_one_or_none()
        if not product or product.status != ProductStatus.ACTIVE:
            raise HTTPException(status_code=400, detail=f"Product {ci.product_id} unavailable")
        line_total = round(product.selling_price * ci.quantity, 2)
        subtotal += line_total
        line_items.append((product, ci.quantity, product.selling_price, line_total))

    subtotal = round(subtotal, 2)
    shipping_cost = compute_shipping(subtotal)
    total = round(subtotal + shipping_cost, 2)
    order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    # Orders ALWAYS start PENDING. They become PAID only via a verified Stripe webhook.
    order = Order(
        order_number=order_number,
        customer_id=customer.id,
        status=OrderStatus.PENDING,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total=total,
        payment_method="stripe" if payments.stripe_enabled() else "unconfigured",
        shipping_address=body.shipping_address.model_dump_json(),
    )
    db.add(order)
    await db.flush()

    for product, qty, unit_price, line_total in line_items:
        db.add(OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=qty,
            unit_price=unit_price,
            total_price=line_total,
        ))

    await db.commit()

    # Create a Stripe Checkout Session (hosted) if payments are configured.
    if payments.stripe_enabled():
        try:
            session = await payments.create_checkout_session(
                order_id=order.id,
                order_number=order_number,
                customer_email=body.email,
                line_items=[
                    {"name": p.name, "unit_price": up, "quantity": q}
                    for (p, q, up, _lt) in line_items
                ],
                shipping_cost=shipping_cost,
                base_url=_base_url(request),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Stripe session creation failed for %s: %s", order.id, exc)
            raise HTTPException(status_code=502, detail="Payment provider error. Please try again.")

        # Persist the session id so the webhook / status checks can correlate.
        order.payment_id = session.get("id") if isinstance(session, dict) else session.id
        await db.commit()

        return {
            "order_id": order.id,
            "order_number": order_number,
            "total": total,
            "status": order.status.value,
            "checkout_url": session.get("url") if isinstance(session, dict) else session.url,
            "payment_required": True,
        }

    # Payments not configured: keep the order PENDING (never auto-mark paid).
    return {
        "order_id": order.id,
        "order_number": order_number,
        "total": total,
        "status": order.status.value,
        "checkout_url": None,
        "payment_required": True,
        "message": "Payments are not configured on this store yet; order saved as PENDING.",
    }


async def _mark_order_paid(order_id: str, payment_intent_id: str | None) -> bool:
    """Idempotently mark a PENDING order as PAID. Returns True if it transitioned."""
    if not order_id:
        return False
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            log.warning("Webhook referenced unknown order_id=%s", order_id)
            return False
        if order.status == OrderStatus.PENDING:
            order.status = OrderStatus.PAID
            if payment_intent_id:
                order.payment_id = payment_intent_id
            await db.commit()
            log.info("Order %s marked PAID via webhook", order_id)
            return True
        return False


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Stripe webhook endpoint. Only a verified event can mark an order paid."""
    if not payments.webhook_configured():
        log.error("Received Stripe webhook but STRIPE_WEBHOOK_SECRET is not set")
        raise HTTPException(status_code=503, detail="Webhook not configured")

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = payments.verify_and_parse_event(payload, sig)
    except Exception as exc:  # invalid signature / payload
        log.warning("Stripe webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature")

    etype = event["type"]
    obj = event["data"]["object"]

    # Stripe's StripeObject supports subscripting but not dict.get(); use a
    # helper that works for both StripeObject and plain dicts.
    def g(o, key, default=None):
        try:
            return o[key]
        except (KeyError, TypeError):
            return default

    if etype == "checkout.session.completed":
        if g(obj, "payment_status") == "paid":
            order_id = g(g(obj, "metadata") or {}, "order_id") or g(obj, "client_reference_id")
            await _mark_order_paid(order_id, g(obj, "payment_intent"))
    elif etype == "payment_intent.succeeded":
        order_id = g(g(obj, "metadata") or {}, "order_id")
        await _mark_order_paid(order_id, g(obj, "id"))

    return {"received": True}


@router.get("/{order_id}")
async def get_order(order_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status.value,
        "subtotal": order.subtotal,
        "shipping_cost": order.shipping_cost,
        "total": order.total,
        "tracking_number": order.tracking_number,
        "tracking_url": order.tracking_url,
        "created_at": order.created_at.isoformat(),
    }
