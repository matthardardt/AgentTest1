"""
Business analytics and database CRUD tools shared across agents.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    AgentAdvisory, AgentDefinition, AgentLog, BusinessMetric, Customer,
    Order, OrderItem, OrderStatus, Product, ProductStatus,
    PricingHistory, Supplier, AsyncSessionLocal,
)


# ── Product catalog operations ─────────────────────────────────────────────────

async def get_all_products(status: str | None = None) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        q = select(Product)
        if status:
            q = q.where(Product.status == ProductStatus(status))
        result = await db.execute(q)
        products = result.scalars().all()
        return {
            "products": [_product_to_dict(p) for p in products],
            "count": len(products),
        }


async def get_product(product_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Product).where(Product.id == product_id))
        p = result.scalar_one_or_none()
        if not p:
            return {"error": f"Product {product_id} not found"}
        return _product_to_dict(p)


async def add_product(
    name: str,
    selling_price: float,
    cost_price: float = 0.0,
    description: str = "",
    category: str = "",
    images: list[str] | None = None,
    supplier_product_id: str = "",
    supplier_url: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        import uuid as _uuid
        sku = f"SKU-{_uuid.uuid4().hex[:8].upper()}"
        p = Product(
            name=name,
            selling_price=selling_price,
            cost_price=cost_price,
            description=description,
            category=category,
            sku=sku,
            images=json.dumps(images or []),
            supplier_product_id=supplier_product_id,
            supplier_url=supplier_url,
            tags=json.dumps(tags or []),
            status=ProductStatus.ACTIVE,
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return {"success": True, "product_id": p.id, "sku": sku, "name": name}


async def update_product(product_id: str, **fields) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Product).where(Product.id == product_id))
        p = result.scalar_one_or_none()
        if not p:
            return {"error": f"Product {product_id} not found"}
        for k, v in fields.items():
            if hasattr(p, k):
                setattr(p, k, v)
        p.updated_at = datetime.utcnow()
        await db.commit()
        return {"success": True, "product_id": product_id, "updated": list(fields.keys())}


async def remove_product(product_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Product).where(Product.id == product_id))
        p = result.scalar_one_or_none()
        if not p:
            return {"error": f"Product {product_id} not found"}
        p.status = ProductStatus.DISCONTINUED
        p.updated_at = datetime.utcnow()
        await db.commit()
        return {"success": True, "product_id": product_id, "status": "discontinued"}


# ── Pricing operations ─────────────────────────────────────────────────────────

async def update_product_price(product_id: str, new_price: float, reason: str = "") -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Product).where(Product.id == product_id))
        p = result.scalar_one_or_none()
        if not p:
            return {"error": f"Product {product_id} not found"}

        old_price = p.selling_price
        if old_price == new_price:
            return {"success": True, "message": "Price unchanged", "price": new_price}

        p.selling_price = new_price
        p.compare_at_price = old_price if new_price < old_price else None
        p.updated_at = datetime.utcnow()

        db.add(PricingHistory(
            product_id=product_id,
            old_price=old_price,
            new_price=new_price,
            reason=reason,
        ))
        await db.commit()
        return {
            "success": True,
            "product_id": product_id,
            "old_price": old_price,
            "new_price": new_price,
            "change_pct": round((new_price - old_price) / old_price * 100, 1),
        }


async def get_pricing_history(product_id: str, days: int = 30) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(PricingHistory)
            .where(PricingHistory.product_id == product_id)
            .where(PricingHistory.changed_at >= since)
            .order_by(PricingHistory.changed_at.desc())
        )
        history = result.scalars().all()
        return {
            "product_id": product_id,
            "history": [
                {
                    "old_price": h.old_price,
                    "new_price": h.new_price,
                    "reason": h.reason,
                    "changed_at": h.changed_at.isoformat(),
                }
                for h in history
            ],
        }


# ── Order operations ───────────────────────────────────────────────────────────

async def get_orders(status: str | None = None, limit: int = 50) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        q = select(Order).order_by(Order.created_at.desc()).limit(limit)
        if status:
            q = q.where(Order.status == OrderStatus(status))
        result = await db.execute(q)
        orders = result.scalars().all()
        return {
            "orders": [_order_to_dict(o) for o in orders],
            "count": len(orders),
        }


async def get_order(order_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Order).where(Order.id == order_id))
        o = result.scalar_one_or_none()
        if not o:
            return {"error": f"Order {order_id} not found"}

        items_result = await db.execute(
            select(OrderItem).where(OrderItem.order_id == order_id)
        )
        items = items_result.scalars().all()
        d = _order_to_dict(o)
        d["items"] = [
            {
                "product_id": i.product_id,
                "quantity": i.quantity,
                "unit_price": i.unit_price,
                "total_price": i.total_price,
            }
            for i in items
        ]
        return d


async def update_order_status(
    order_id: str,
    status: str,
    supplier_order_id: str = "",
    tracking_number: str = "",
    tracking_url: str = "",
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Order).where(Order.id == order_id))
        o = result.scalar_one_or_none()
        if not o:
            return {"error": f"Order {order_id} not found"}

        o.status = OrderStatus(status)
        if supplier_order_id:
            o.supplier_order_id = supplier_order_id
        if tracking_number:
            o.tracking_number = tracking_number
        if tracking_url:
            o.tracking_url = tracking_url
        o.updated_at = datetime.utcnow()
        await db.commit()
        return {"success": True, "order_id": order_id, "new_status": status}


# ── Business metrics / analytics ───────────────────────────────────────────────

async def get_business_metrics(days: int = 30) -> dict[str, Any]:
    since = datetime.utcnow() - timedelta(days=days)
    async with AsyncSessionLocal() as db:
        # Revenue
        rev_result = await db.execute(
            select(func.sum(Order.total))
            .where(Order.created_at >= since)
            .where(Order.status.notin_([OrderStatus.CANCELLED, OrderStatus.REFUNDED]))
        )
        revenue = rev_result.scalar() or 0.0

        # Order count
        cnt_result = await db.execute(
            select(func.count(Order.id)).where(Order.created_at >= since)
        )
        order_count = cnt_result.scalar() or 0

        # Pending orders
        pend_result = await db.execute(
            select(func.count(Order.id)).where(Order.status == OrderStatus.PAID)
        )
        pending = pend_result.scalar() or 0

        # Active products
        prod_result = await db.execute(
            select(func.count(Product.id)).where(Product.status == ProductStatus.ACTIVE)
        )
        active_products = prod_result.scalar() or 0

        # Top products by revenue
        top_result = await db.execute(
            select(Product.name, func.sum(OrderItem.total_price).label("rev"))
            .join(OrderItem, Product.id == OrderItem.product_id)
            .join(Order, OrderItem.order_id == Order.id)
            .where(Order.created_at >= since)
            .group_by(Product.id)
            .order_by(func.sum(OrderItem.total_price).desc())
            .limit(5)
        )
        top_products = [{"name": r[0], "revenue": round(r[1], 2)} for r in top_result]

        return {
            "period_days": days,
            "revenue": round(revenue, 2),
            "order_count": order_count,
            "avg_order_value": round(revenue / order_count, 2) if order_count else 0,
            "pending_orders": pending,
            "active_products": active_products,
            "top_products": top_products,
        }


async def get_agent_logs(agent_name: str | None = None, limit: int = 20) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        q = select(AgentLog).order_by(AgentLog.created_at.desc()).limit(limit)
        if agent_name:
            q = q.where(AgentLog.agent_name == agent_name)
        result = await db.execute(q)
        logs = result.scalars().all()
        return {
            "logs": [
                {
                    "agent": l.agent_name,
                    "task": l.task,
                    "status": l.status,
                    "tokens": l.tokens_used,
                    "duration_s": l.duration_seconds,
                    "created_at": l.created_at.isoformat(),
                }
                for l in logs
            ]
        }


async def save_agent_definition(
    name: str,
    description: str,
    system_prompt: str,
    model: str = "claude-sonnet-4-6",
    tools_config: list[str] | None = None,
    schedule_seconds: int = 3600,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AgentDefinition).where(AgentDefinition.name == name))
        existing = result.scalar_one_or_none()
        if existing:
            existing.description = description
            existing.system_prompt = system_prompt
            existing.model = model
            existing.tools_config = json.dumps(tools_config or [])
            existing.schedule_seconds = schedule_seconds
        else:
            db.add(AgentDefinition(
                name=name,
                description=description,
                system_prompt=system_prompt,
                model=model,
                tools_config=json.dumps(tools_config or []),
                schedule_seconds=schedule_seconds,
            ))
        await db.commit()
        return {"success": True, "agent_name": name}


async def get_all_agent_definitions() -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AgentDefinition).where(AgentDefinition.is_active))
        agents = result.scalars().all()
        return {
            "agents": [
                {
                    "name": a.name,
                    "description": a.description,
                    "model": a.model,
                    "schedule_seconds": a.schedule_seconds,
                    "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None,
                    "created_at": a.created_at.isoformat(),
                }
                for a in agents
            ]
        }


async def record_metric(name: str, value: float, data: dict | None = None) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        db.add(BusinessMetric(
            metric_name=name,
            metric_value=value,
            metric_data=json.dumps(data or {}),
        ))
        await db.commit()
        return {"success": True}


async def get_agent_advisory(target_agent: str, limit: int = 3) -> dict[str, Any]:
    """Retrieve active coaching advisories from the Training Agent."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentAdvisory)
            .where(AgentAdvisory.target_agent == target_agent)
            .where(AgentAdvisory.status == "active")
            .order_by(AgentAdvisory.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
    if not rows:
        return {"advisories": [], "message": "No active advisories yet — proceed with defaults."}
    return {
        "advisories": [
            {
                "advisory_type": r.advisory_type,
                "priority": r.priority,
                "guidance": r.guidance,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "count": len(rows),
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _product_to_dict(p: Product) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "sku": p.sku,
        "cost_price": p.cost_price,
        "selling_price": p.selling_price,
        "compare_at_price": p.compare_at_price,
        "images": json.loads(p.images or "[]"),
        "status": p.status.value if p.status else None,
        "tags": json.loads(p.tags or "[]"),
        "supplier_product_id": p.supplier_product_id,
        "supplier_url": p.supplier_url,
        "stock_quantity": p.stock_quantity,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _order_to_dict(o: Order) -> dict:
    return {
        "id": o.id,
        "order_number": o.order_number,
        "customer_id": o.customer_id,
        "status": o.status.value if o.status else None,
        "subtotal": o.subtotal,
        "shipping_cost": o.shipping_cost,
        "total": o.total,
        "shipping_address": json.loads(o.shipping_address or "{}"),
        "supplier_order_id": o.supplier_order_id,
        "tracking_number": o.tracking_number,
        "tracking_url": o.tracking_url,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


# ── Tool schemas ───────────────────────────────────────────────────────────────

class AnalyticsTools:
    SCHEMAS = [
        {
            "name": "get_all_products",
            "description": "Get the current product catalog from the store.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["active", "inactive", "out_of_stock", "discontinued"],
                               "description": "Filter by status (optional)"},
                },
            },
        },
        {
            "name": "get_product",
            "description": "Get details for a single product.",
            "input_schema": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
        {
            "name": "add_product",
            "description": "Add a new product to the store catalog.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "selling_price": {"type": "number"},
                    "cost_price": {"type": "number"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "images": {"type": "array", "items": {"type": "string"}},
                    "supplier_product_id": {"type": "string"},
                    "supplier_url": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "selling_price"],
            },
        },
        {
            "name": "update_product",
            "description": "Update fields on an existing product (description, images, category, status, etc.).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "images": {"type": "string", "description": "JSON array of image URLs"},
                    "tags": {"type": "string", "description": "JSON array of tags"},
                    "status": {"type": "string", "enum": ["active", "inactive", "out_of_stock"]},
                    "meta_title": {"type": "string"},
                    "meta_description": {"type": "string"},
                },
                "required": ["product_id"],
            },
        },
        {
            "name": "remove_product",
            "description": "Discontinue a product from the store.",
            "input_schema": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
        {
            "name": "update_product_price",
            "description": "Update the selling price for a product and record the change.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "new_price": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["product_id", "new_price"],
            },
        },
        {
            "name": "get_pricing_history",
            "description": "Get price change history for a product.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "days": {"type": "integer", "default": 30},
                },
                "required": ["product_id"],
            },
        },
        {
            "name": "get_orders",
            "description": "Get customer orders, optionally filtered by status.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["pending", "paid", "processing",
                               "ordered_from_supplier", "shipped", "delivered",
                               "cancelled", "refunded"]},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        },
        {
            "name": "get_order",
            "description": "Get full details for a single order including items.",
            "input_schema": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
        {
            "name": "update_order_status",
            "description": "Update an order's status and optionally set supplier order / tracking info.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["processing", "ordered_from_supplier",
                               "shipped", "delivered", "cancelled", "refunded"]},
                    "supplier_order_id": {"type": "string"},
                    "tracking_number": {"type": "string"},
                    "tracking_url": {"type": "string"},
                },
                "required": ["order_id", "status"],
            },
        },
        {
            "name": "get_business_metrics",
            "description": "Get overall business KPIs: revenue, order count, top products, etc.",
            "input_schema": {
                "type": "object",
                "properties": {"days": {"type": "integer", "default": 30}},
            },
        },
        {
            "name": "get_agent_logs",
            "description": "Get recent logs from agent runs.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
        {
            "name": "save_agent_definition",
            "description": "Create or update a dynamic agent definition in the database.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "system_prompt": {"type": "string"},
                    "model": {"type": "string", "default": "claude-sonnet-4-6"},
                    "tools_config": {"type": "array", "items": {"type": "string"}},
                    "schedule_seconds": {"type": "integer", "default": 3600},
                },
                "required": ["name", "description", "system_prompt"],
            },
        },
        {
            "name": "get_all_agent_definitions",
            "description": "List all registered agent definitions.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "record_metric",
            "description": "Record a business metric data point.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "number"},
                    "data": {"type": "object"},
                },
                "required": ["name", "value"],
            },
        },
        {
            "name": "get_agent_advisory",
            "description": (
                "Retrieve active coaching advisories from the Training Agent for your agent role. "
                "Call this at the start of your run and integrate the guidance into your decisions."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_agent": {
                        "type": "string",
                        "description": (
                            "Your agent name: product_hunting, pricing, website_maintenance, "
                            "design, ordering, image_validation, or manager"
                        ),
                    },
                    "limit": {"type": "integer", "default": 3},
                },
                "required": ["target_agent"],
            },
        },
    ]

    MAP = {
        "get_all_products": get_all_products,
        "get_product": get_product,
        "add_product": add_product,
        "update_product": update_product,
        "remove_product": remove_product,
        "update_product_price": update_product_price,
        "get_pricing_history": get_pricing_history,
        "get_orders": get_orders,
        "get_order": get_order,
        "update_order_status": update_order_status,
        "get_business_metrics": get_business_metrics,
        "get_agent_logs": get_agent_logs,
        "save_agent_definition": save_agent_definition,
        "get_all_agent_definitions": get_all_agent_definitions,
        "record_metric": record_metric,
        "get_agent_advisory": get_agent_advisory,
    }
