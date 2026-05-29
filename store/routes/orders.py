import json
import uuid
from datetime import datetime

import stripe as stripe_lib
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import Customer, Order, OrderItem, OrderStatus, Product, ProductStatus, get_db

router = APIRouter()
settings = get_settings()


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


class CreatePaymentIntentRequest(BaseModel):
    email: str
    shipping_address: ShippingAddress
    items: list[CartItem]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _resolve_line_items(items: list[CartItem], db: AsyncSession):
    """Validate cart items, return (product, qty, unit_price, line_total) tuples and subtotal."""
    line_items = []
    subtotal = 0.0
    for ci in items:
        result = await db.execute(select(Product).where(Product.id == ci.product_id))
        product = result.scalar_one_or_none()
        if not product or product.status != ProductStatus.ACTIVE:
            raise HTTPException(status_code=400, detail=f"Product {ci.product_id} unavailable")
        line_total = round(product.selling_price * ci.quantity, 2)
        subtotal += line_total
        line_items.append((product, ci.quantity, product.selling_price, line_total))
    return line_items, round(subtotal, 2)


async def _upsert_customer(email: str, addr: ShippingAddress, db: AsyncSession) -> Customer:
    result = await db.execute(select(Customer).where(Customer.email == email))
    customer = result.scalar_one_or_none()
    if not customer:
        customer = Customer(
            email=email,
            name=addr.name,
            phone=addr.phone,
            address_line1=addr.address_line1,
            city=addr.city,
            state=addr.state,
            country=addr.country,
            postal_code=addr.postal_code,
        )
        db.add(customer)
        await db.flush()
    return customer


async def _build_order(
    customer: Customer,
    line_items: list,
    subtotal: float,
    addr: ShippingAddress,
    db: AsyncSession,
    payment_method: str = "",
    payment_id: str = "",
    status: OrderStatus = OrderStatus.PENDING,
) -> Order:
    order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    order = Order(
        order_number=order_number,
        customer_id=customer.id,
        status=status,
        subtotal=subtotal,
        shipping_cost=0.0,
        total=subtotal,
        payment_method=payment_method,
        payment_id=payment_id,
        shipping_address=addr.model_dump_json(),
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
    return order


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/")
async def create_order(body: CreateOrderRequest, db: AsyncSession = Depends(get_db)):
    """Create a PENDING order without payment. Use for testing or non-Stripe flows."""
    line_items, subtotal = await _resolve_line_items(body.items, db)
    customer = await _upsert_customer(body.email, body.shipping_address, db)
    order = await _build_order(customer, line_items, subtotal, body.shipping_address, db)
    await db.commit()
    return {"order_id": order.id, "order_number": order.order_number,
            "total": order.total, "status": order.status.value}


@router.post("/create-payment-intent")
async def create_payment_intent(
    body: CreatePaymentIntentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe PaymentIntent and a PENDING order. Returns client_secret for frontend."""
    if not settings.stripe_api_key:
        raise HTTPException(status_code=503, detail="Stripe not configured — set STRIPE_API_KEY")

    stripe_lib.api_key = settings.stripe_api_key
    line_items, subtotal = await _resolve_line_items(body.items, db)
    amount_cents = int(subtotal * 100)

    try:
        intent = stripe_lib.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            metadata={"email": body.email},
        )
    except stripe_lib.StripeError as exc:
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc.user_message}")

    customer = await _upsert_customer(body.email, body.shipping_address, db)
    order = await _build_order(
        customer, line_items, subtotal, body.shipping_address, db,
        payment_method="stripe",
        payment_id=intent.id,
    )
    await db.commit()
    return {"client_secret": intent.client_secret, "order_id": order.id}


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Stripe sends this when a payment succeeds. Marks the matching order as PAID."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if settings.stripe_webhook_secret:
        stripe_lib.api_key = settings.stripe_api_key
        try:
            event = stripe_lib.Webhook.construct_event(
                payload, sig, settings.stripe_webhook_secret
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe_lib.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        try:
            event = json.loads(payload)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

    if event.get("type") == "payment_intent.succeeded":
        pi_id = event["data"]["object"]["id"]
        result = await db.execute(select(Order).where(Order.payment_id == pi_id))
        order = result.scalar_one_or_none()
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.PAID
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
