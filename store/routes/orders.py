"""
Order creation, Stripe Checkout, and the Stripe webhook that confirms payment.

Flow when Stripe is configured (settings.payments_enabled):
  1. Browser POSTs cart + shipping to /api/orders/create-checkout-session
  2. We create the Order (status PENDING) and a Stripe Checkout Session, and
     return the hosted checkout URL.
  3. Browser redirects to Stripe. On success Stripe calls /api/orders/webhook/stripe
     with `checkout.session.completed`, and we flip the order to PAID — which is
     what the ordering/fulfillment agent watches for.

Flow when Stripe is NOT configured (test/preview):
  create-checkout-session still records a PENDING order and tells the browser to
  go straight to the confirmation page, so the storefront stays clickable.
"""

import asyncio
import json
import uuid
from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import Customer, Order, OrderItem, OrderStatus, Product, ProductStatus, get_db

settings = get_settings()
if settings.stripe_api_key:
    stripe.api_key = settings.stripe_api_key

router = APIRouter()


# ── Request models ──────────────────────────────────────────────────────────────

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
    payment_id: str = ""


# ── Shared order builder ──────────────────────────────────────────────────────

async def _build_order(body: CreateOrderRequest, db: AsyncSession, *, paid: bool):
    """Upsert customer, validate items, persist a PENDING/PAID order. Returns
    (order, stripe_line_items)."""
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

    if not body.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    subtotal = 0.0
    line_items = []          # (product, qty, unit_price, line_total)
    stripe_line_items = []
    for ci in body.items:
        if ci.quantity < 1 or ci.quantity > 100:
            raise HTTPException(status_code=400, detail="Invalid quantity")
        prod_result = await db.execute(select(Product).where(Product.id == ci.product_id))
        product = prod_result.scalar_one_or_none()
        if not product or product.status != ProductStatus.ACTIVE:
            raise HTTPException(status_code=400, detail=f"Product {ci.product_id} unavailable")
        line_total = round(product.selling_price * ci.quantity, 2)
        subtotal += line_total
        line_items.append((product, ci.quantity, product.selling_price, line_total))
        stripe_line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {"name": product.name},
                "unit_amount": int(round(product.selling_price * 100)),
            },
            "quantity": ci.quantity,
        })

    subtotal = round(subtotal, 2)
    shipping_cost = 0.0       # free shipping; absorbed into unit economics
    total = round(subtotal + shipping_cost, 2)
    order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    order = Order(
        order_number=order_number,
        customer_id=customer.id,
        status=OrderStatus.PAID if paid else OrderStatus.PENDING,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total=total,
        payment_method="stripe" if settings.payments_enabled else "manual",
        payment_id=body.payment_id,
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

    return order, stripe_line_items


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/")
async def create_order(body: CreateOrderRequest, db: AsyncSession = Depends(get_db)):
    """Direct order creation (API consumers / tests). Marks PAID iff a payment_id
    is supplied. Browsers should use /create-checkout-session instead."""
    order, _ = await _build_order(body, db, paid=bool(body.payment_id))
    await db.commit()
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "total": order.total,
        "status": order.status.value,
    }


@router.post("/create-checkout-session")
async def create_checkout_session(body: CreateOrderRequest, db: AsyncSession = Depends(get_db)):
    """Create a PENDING order and (if Stripe is configured) a hosted Stripe
    Checkout Session. Returns either a checkout_url to redirect to, or a
    redirect to the confirmation page when payments are disabled."""
    order, stripe_line_items = await _build_order(body, db, paid=False)

    if not settings.payments_enabled:
        # No Stripe configured — record the order and let the storefront proceed.
        await db.commit()
        return {
            "payments_enabled": False,
            "order_id": order.id,
            "redirect_url": f"/order/{order.id}",
        }

    order_id = order.id
    await db.commit()

    try:
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            mode="payment",
            line_items=stripe_line_items,
            customer_email=body.email,
            client_reference_id=order_id,
            metadata={"order_id": order_id},
            payment_intent_data={"metadata": {"order_id": order_id}},
            success_url=f"{settings.store_url}/order/{order_id}?paid=1",
            cancel_url=f"{settings.store_url}/checkout",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Payment provider error: {exc}")

    return {
        "payments_enabled": True,
        "order_id": order_id,
        "checkout_url": session.url,
    }


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive Stripe events and flip the matching order to PAID.

    Requires STRIPE_WEBHOOK_SECRET — we never change order state from an
    unverified request."""
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        # construct_event decodes the body and verifies the HMAC signature
        # (raises on tamper/replay). We then read fields from the raw JSON to
        # avoid Stripe's object-wrapper accessors.
        stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {exc}")

    event = json.loads(payload)
    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    order_id = (obj.get("metadata") or {}).get("order_id") or obj.get("client_reference_id")
    payment_id = obj.get("payment_intent") or obj.get("id")

    if etype in ("checkout.session.completed", "payment_intent.succeeded") and order_id:
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.PAID
            order.payment_id = str(payment_id or "")
            order.updated_at = datetime.utcnow()
            await db.commit()

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
        "total": order.total,
        "tracking_number": order.tracking_number,
        "tracking_url": order.tracking_url,
        "created_at": order.created_at.isoformat(),
    }
