"""
Supplier integration tools.
Implements the AliExpress adapter for product sourcing.

AliExpress does not expose an automated dropship order-placement API for most
sellers, so order placement and tracking run in MANUAL mode: paid orders are
flagged for the operator to fulfil by hand on AliExpress, then the tracking
number is recorded back into the order. When AliExpress API keys are not
configured, product search falls back to mock data so the agents still run.
"""

import json
import uuid
from typing import Any

import httpx

from config import get_settings

settings = get_settings()


# ── AliExpress adapter ─────────────────────────────────────────────────────────

async def aliexpress_search_products(keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """Search AliExpress for products matching keyword."""
    if not settings.aliexpress_app_key:
        return _mock_product_search(keyword, page_size)

    params = {
        "method": "aliexpress.affiliate.product.query",
        "app_key": settings.aliexpress_app_key,
        "keywords": keyword,
        "page_no": page,
        "page_size": page_size,
        "target_currency": "USD",
        "target_language": "EN",
        "tracking_id": "dropship",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.aliexpress.com/router/rest", params=params)
        r.raise_for_status()
        return r.json()


async def aliexpress_get_product(product_id: str) -> dict[str, Any]:
    """Get detailed info for an AliExpress product."""
    if not settings.aliexpress_app_key:
        return _mock_product_detail(product_id)

    params = {
        "method": "aliexpress.affiliate.productdetail.get",
        "app_key": settings.aliexpress_app_key,
        "product_ids": product_id,
        "target_currency": "USD",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.aliexpress.com/router/rest", params=params)
        r.raise_for_status()
        return r.json()


# ── Manual fulfilment ──────────────────────────────────────────────────────────
# AliExpress has no automated order API here, so orders are queued for the
# operator to place by hand. These return a structured "manual" result the
# ordering agent records on the order so a human knows to act.

def _manual_place_order(product_id: str, quantity: int, name: str) -> dict[str, Any]:
    return {
        "success": True,
        "fulfilment_mode": "manual",
        "supplier_order_id": f"MANUAL-{uuid.uuid4().hex[:8].upper()}",
        "product_id": product_id,
        "quantity": quantity,
        "recipient": name,
        "action_required": (
            "Place this order manually on AliExpress and ship to the customer "
            "address, then record the AliExpress tracking number on the order."
        ),
        "estimated_shipping_days": 12,
        "source": "manual",
    }


def _manual_tracking(supplier_order_id: str) -> dict[str, Any]:
    return {
        "supplier_order_id": supplier_order_id,
        "fulfilment_mode": "manual",
        "status": "awaiting_manual_tracking",
        "note": (
            "Tracking is added manually after the AliExpress order ships. "
            "Update the order with the AliExpress tracking number when available."
        ),
        "source": "manual",
    }


# ── Mock data for development / no API keys ────────────────────────────────────

def _mock_product_search(keyword: str, count: int) -> dict[str, Any]:
    products = []
    for i in range(min(count, 5)):
        products.append({
            "product_id": f"mock_{keyword.replace(' ', '_')}_{i}",
            "name": f"{keyword.title()} Product {i + 1}",
            "price_usd": round(5.0 + i * 3.5, 2),
            "image_url": f"https://placeholder.com/300x300?text={keyword}+{i}",
            "rating": round(4.0 + (i % 3) * 0.3, 1),
            "orders_count": 100 + i * 50,
            "supplier": "mock_supplier",
            "shipping_days": 7 + i * 2,
        })
    return {"products": products, "total": count, "source": "mock"}


def _mock_product_detail(product_id: str) -> dict[str, Any]:
    return {
        "product_id": product_id,
        "name": f"Product {product_id}",
        "description": "High quality product with fast shipping.",
        "price_usd": 12.99,
        "images": ["https://placeholder.com/600x600"],
        "weight_kg": 0.3,
        "shipping_days": 10,
        "source": "mock",
    }


# ── Tool schemas ───────────────────────────────────────────────────────────────

class SupplierTools:
    SCHEMAS = [
        {
            "name": "search_supplier_products",
            "description": "Search AliExpress for products to stock.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Product search keyword"},
                    "page_size": {"type": "integer", "default": 20},
                },
                "required": ["keyword"],
            },
        },
        {
            "name": "place_supplier_order",
            "description": (
                "Queue a dropship order for fulfilment. AliExpress orders are placed "
                "manually by the operator, so this returns a manual-fulfilment ticket "
                "to record on the order."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "supplier_product_id": {"type": "string"},
                    "quantity": {"type": "integer"},
                    "shipping_name": {"type": "string"},
                    "shipping_address": {"type": "string"},
                    "shipping_city": {"type": "string"},
                    "shipping_country": {"type": "string"},
                    "shipping_zip": {"type": "string"},
                    "shipping_phone": {"type": "string"},
                },
                "required": ["supplier_product_id", "quantity", "shipping_name",
                             "shipping_address", "shipping_city", "shipping_country",
                             "shipping_zip", "shipping_phone"],
            },
        },
        {
            "name": "get_supplier_tracking",
            "description": "Get shipping tracking information for a supplier order.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "supplier_order_id": {"type": "string"},
                },
                "required": ["supplier_order_id"],
            },
        },
    ]

    @staticmethod
    async def search_supplier_products(keyword: str, page_size: int = 20) -> dict[str, Any]:
        return await aliexpress_search_products(keyword, page_size=page_size)

    @staticmethod
    async def place_supplier_order(**kwargs) -> dict[str, Any]:
        return _manual_place_order(
            product_id=kwargs["supplier_product_id"],
            quantity=kwargs["quantity"],
            name=kwargs["shipping_name"],
        )

    @staticmethod
    async def get_supplier_tracking(supplier_order_id: str) -> dict[str, Any]:
        return _manual_tracking(supplier_order_id)

    MAP: dict  # populated below


SupplierTools.MAP = {
    "search_supplier_products": SupplierTools.search_supplier_products,
    "place_supplier_order": SupplierTools.place_supplier_order,
    "get_supplier_tracking": SupplierTools.get_supplier_tracking,
}
