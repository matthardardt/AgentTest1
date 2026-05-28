import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import Customer, Order, OrderItem, OrderStatus, Product, ProductStatus, get_db

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
    payment_id: str = ""


@router.post("/")
async def create_order(body: CreateOrderRequest, db: AsyncSession = Depends(get_db)):
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

    # Validate products and compute totals
    subtotal = 0.0
    line_items = []
    for ci in body.items:
        prod_result = await db.execute(select(Product).where(Product.id == ci.product_id))
        product = prod_result.scalar_one_or_none()
        if not product or product.status != ProductStatus.ACTIVE:
            raise HTTPException(status_code=400, detail=f"Product {ci.product_id} unavailable")
        line_total = round(product.selling_price * ci.quantity, 2)
        subtotal += line_total
        line_items.append((product, ci.quantity, product.selling_price, line_total))

    subtotal = round(subtotal, 2)
    shipping_cost = 0.0
    total = round(subtotal + shipping_cost, 2)
    order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    order = Order(
        order_number=order_number,
        customer_id=customer.id,
        status=OrderStatus.PAID if body.payment_id else OrderStatus.PENDING,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total=total,
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

    await db.commit()
    return {
        "order_id": order.id,
        "order_number": order_number,
        "total": total,
        "status": order.status.value,
    }


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
