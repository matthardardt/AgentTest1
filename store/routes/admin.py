"""
Internal admin API — consumed by agents and an optional admin dashboard.
Not customer-facing.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    AgentDefinition, AgentLog, BusinessMetric, Order,
    OrderStatus, Product, ProductStatus, get_db,
)

router = APIRouter()


@router.get("/stats")
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


@router.get("/agents")
async def list_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentDefinition))
    return {"agents": [
        {"name": a.name, "description": a.description, "is_active": a.is_active,
         "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None}
        for a in result.scalars().all()
    ]}


@router.get("/logs")
async def recent_logs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentLog).order_by(AgentLog.created_at.desc()).limit(limit)
    )
    return {"logs": [
        {"agent": l.agent_name, "status": l.status, "tokens": l.tokens_used,
         "duration_s": l.duration_seconds, "created_at": l.created_at.isoformat()}
        for l in result.scalars().all()
    ]}


@router.get("/metrics")
async def recent_metrics(limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BusinessMetric).order_by(BusinessMetric.recorded_at.desc()).limit(limit)
    )
    return {"metrics": [
        {"name": m.metric_name, "value": m.metric_value,
         "recorded_at": m.recorded_at.isoformat()}
        for m in result.scalars().all()
    ]}
