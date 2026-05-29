"""
Internal admin API — consumed by agents and an optional admin dashboard.
Not customer-facing.
"""

import hmac
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import (
    AgentDefinition, AgentLog, BusinessMetric, Order,
    OrderStatus, Product, ProductStatus, get_db,
)

settings = get_settings()

router = APIRouter()


def _admin_secret() -> str:
    # Falls back to SECRET_KEY when a dedicated ADMIN_API_KEY isn't configured.
    return settings.admin_api_key or settings.secret_key


async def require_admin(x_admin_key: str = Header(default="")) -> None:
    """Protect the internal admin API. Pass the key via the `X-Admin-Key` header."""
    expected = _admin_secret()
    if not expected or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/stats", dependencies=[Depends(require_admin)])
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_products = (await db.execute(
        select(func.count(Product.id)).where(Product.status == ProductStatus.ACTIVE)
    )).scalar()

    total_orders = (await db.execute(select(func.count(Order.id)))).scalar()

    pending_orders = (await db.execute(
        select(func.count(Order.id)).where(Order.status == OrderStatus.PAID)
    )).scalar()

    revenue = (await db.execute(
        select(func.sum(Order.total))
        .where(Order.status.notin_([OrderStatus.CANCELLED, OrderStatus.REFUNDED]))
    )).scalar() or 0.0

    return {
        "active_products": total_products,
        "total_orders": total_orders,
        "pending_fulfillment": pending_orders,
        "total_revenue": round(revenue, 2),
    }


@router.get("/agents", dependencies=[Depends(require_admin)])
async def list_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentDefinition))
    return {"agents": [
        {"name": a.name, "description": a.description, "is_active": a.is_active,
         "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None}
        for a in result.scalars().all()
    ]}


@router.get("/logs", dependencies=[Depends(require_admin)])
async def recent_logs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentLog).order_by(AgentLog.created_at.desc()).limit(limit)
    )
    return {"logs": [
        {"agent": l.agent_name, "status": l.status, "tokens": l.tokens_used,
         "duration_s": l.duration_seconds, "created_at": l.created_at.isoformat()}
        for l in result.scalars().all()
    ]}


@router.get("/seed")
async def seed_catalog(key: str = "", db: AsyncSession = Depends(get_db)):
    """Seed the catalog with starter products. Protected by SECRET_KEY query param."""
    if not settings.secret_key or not hmac.compare_digest(key, settings.secret_key):
        raise HTTPException(status_code=403, detail="Invalid key")

    existing = (await db.execute(
        select(func.count(Product.id))
    )).scalar() or 0
    if existing > 0:
        return {"message": f"Catalog already has {existing} products — skipping seed."}

    seed_products = [
        {
            "name": "Wireless Noise-Cancelling Earbuds",
            "description": "Premium wireless earbuds with active noise cancellation, 30-hour battery life, and crystal-clear sound. Perfect for work, travel, and workouts.",
            "supplier_price": 18.50, "selling_price": 49.99, "stock_quantity": 100,
            "category": "Electronics", "tags": ["earbuds", "wireless", "audio"],
            "images": ["https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=600"],
        },
        {
            "name": "Portable Magnetic Phone Stand",
            "description": "Adjustable magnetic desk stand compatible with all smartphones. Foldable design fits in your pocket. Strong magnet, no wobble.",
            "supplier_price": 4.20, "selling_price": 19.99, "stock_quantity": 200,
            "category": "Accessories", "tags": ["phone", "stand", "desk"],
            "images": ["https://images.unsplash.com/photo-1586953208448-b95a79798f07?w=600"],
        },
        {
            "name": "LED Star Projector Night Light",
            "description": "Galaxy projector with 12 lighting modes, timer, and remote control. Creates a stunning starry sky on your ceiling. Perfect gift.",
            "supplier_price": 12.00, "selling_price": 34.99, "stock_quantity": 150,
            "category": "Home & Decor", "tags": ["light", "bedroom", "gift"],
            "images": ["https://images.unsplash.com/photo-1519681393784-d120267933ba?w=600"],
        },
        {
            "name": "Stainless Steel Insulated Tumbler",
            "description": "40oz vacuum-insulated tumbler keeps drinks cold 24hrs or hot 12hrs. Leak-proof lid, fits most cup holders. BPA-free.",
            "supplier_price": 8.50, "selling_price": 29.99, "stock_quantity": 300,
            "category": "Kitchen", "tags": ["tumbler", "water bottle", "insulated"],
            "images": ["https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=600"],
        },
        {
            "name": "Resistance Bands Set (5 Levels)",
            "description": "Set of 5 colour-coded resistance bands from light to extra-heavy. Includes carry bag and exercise guide. Latex-free.",
            "supplier_price": 6.00, "selling_price": 24.99, "stock_quantity": 250,
            "category": "Fitness", "tags": ["fitness", "workout", "resistance bands"],
            "images": ["https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=600"],
        },
        {
            "name": "Minimalist Leather Wallet (RFID Block)",
            "description": "Slim bifold wallet with RFID blocking technology. Holds 8 cards + cash. Genuine leather, available in black and brown.",
            "supplier_price": 7.00, "selling_price": 27.99, "stock_quantity": 175,
            "category": "Accessories", "tags": ["wallet", "leather", "RFID"],
            "images": ["https://images.unsplash.com/photo-1627123424574-724758594e93?w=600"],
        },
        {
            "name": "Fast Wireless Charging Pad",
            "description": "15W fast wireless charger compatible with iPhone, Samsung, and all Qi devices. Non-slip surface, LED indicator, cable included.",
            "supplier_price": 9.00, "selling_price": 32.99, "stock_quantity": 120,
            "category": "Electronics", "tags": ["charger", "wireless", "iPhone"],
            "images": ["https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?w=600"],
        },
        {
            "name": "Acupressure Massage Ball Set",
            "description": "Set of 3 spiky massage balls in different sizes. Relieves muscle tension, plantar fasciitis, and stress. Great for desk workers.",
            "supplier_price": 5.00, "selling_price": 18.99, "stock_quantity": 200,
            "category": "Wellness", "tags": ["massage", "wellness", "stress relief"],
            "images": ["https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=600"],
        },
    ]

    added = 0
    for p in seed_products:
        db.add(Product(
            id=str(uuid.uuid4()),
            name=p["name"],
            description=p["description"],
            cost_price=p["supplier_price"],
            selling_price=p["selling_price"],
            stock_quantity=p["stock_quantity"],
            category=p["category"],
            tags=json.dumps(p["tags"]),
            images=json.dumps(p["images"]),
            status=ProductStatus.ACTIVE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ))
        added += 1

    await db.commit()
    return {"success": True, "products_added": added,
            "message": f"Seeded {added} products. Refresh the homepage!"}


@router.get("/metrics", dependencies=[Depends(require_admin)])
async def recent_metrics(limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BusinessMetric).order_by(BusinessMetric.recorded_at.desc()).limit(limit)
    )
    return {"metrics": [
        {"name": m.metric_name, "value": m.metric_value,
         "recorded_at": m.recorded_at.isoformat()}
        for m in result.scalars().all()
    ]}
