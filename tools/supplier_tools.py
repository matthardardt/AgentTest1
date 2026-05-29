"""
Supplier integration tools.
Implements AliExpress and CJ Dropshipping adapters.
Falls back to mock data when API keys are not configured.
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


# ── CJ Dropshipping adapter ────────────────────────────────────────────────────

async def cj_get_token() -> str | None:
    """Obtain CJ Dropshipping access token."""
    if not settings.cjdropshipping_api_key:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://developers.cjdropshipping.com/api2.0/v1/authentication/getAccessToken",
            json={"email": settings.cjdropshipping_email, "password": settings.cjdropshipping_api_key},
        )
        r.raise_for_status()
        return r.json().get("data", {}).get("accessToken")


async def cj_search_products(keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """Search CJ Dropshipping for products."""
    token = await cj_get_token()
    if not token:
        return _mock_product_search(keyword, page_size)

    headers = {"CJ-Access-Token": token}
    params = {"productNameEn": keyword, "pageNum": page, "pageSize": page_size}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://developers.cjdropshipping.com/api2.0/v1/product/list",
            headers=headers,
            params=params,
        )
        r.raise_for_status()
        return r.json()


async def cj_place_order(
    product_id: str,
    quantity: int,
    shipping_name: str,
    shipping_address: str,
    shipping_city: str,
    shipping_country: str,
    shipping_zip: str,
    shipping_phone: str,
) -> dict[str, Any]:
    """Place a dropship order via CJ Dropshipping."""
    token = await cj_get_token()
    if not token:
        return _mock_place_order(product_id, quantity, shipping_name)

    headers = {"CJ-Access-Token": token}
    payload = {
        "orderNumber": str(uuid.uuid4()),
        "products": [{"vid": product_id, "quantity": quantity}],
        "shippingInfo": {
            "consigneeID": str(uuid.uuid4()),
            "consigneeName": shipping_name,
            "address": shipping_address,
            "city": shipping_city,
            "country": shipping_country,
            "zipCode": shipping_zip,
            "phone": shipping_phone,
        },
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://developers.cjdropshipping.com/api2.0/v1/shopping/order/createOrderV2",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        return r.json()


async def get_tracking_info(supplier_order_id: str) -> dict[str, Any]:
    """Get tracking information for a supplier order."""
    token = await cj_get_token()
    if not token:
        return _mock_tracking(supplier_order_id)

    headers = {"CJ-Access-Token": token}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://developers.cjdropshipping.com/api2.0/v1/shopping/order/getOrderDetail",
            headers=headers,
            params={"orderID": supplier_order_id},
        )
        r.raise_for_status()
        return r.json()


# ── Zendrop adapter ───────────────────────────────────────────────────────────

async def zendrop_search_products(keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """Search Zendrop catalog for products."""
    if not settings.zendrop_api_key:
        return _mock_product_search(keyword, page_size)

    headers = {"Authorization": f"Bearer {settings.zendrop_api_key}"}
    params = {"search": keyword, "page": page, "limit": page_size}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.zendrop.com/api/products", headers=headers, params=params)
        r.raise_for_status()
        return r.json()


# ── Spocket adapter ────────────────────────────────────────────────────────────

async def spocket_search_products(keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """Search Spocket marketplace for products."""
    if not settings.spocket_api_key:
        return _mock_product_search(keyword, page_size)

    headers = {"Authorization": f"Bearer {settings.spocket_api_key}"}
    params = {"q": keyword, "page": page, "per_page": page_size}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.spocket.co/products", headers=headers, params=params)
        r.raise_for_status()
        return r.json()


# ── AutoDS adapter ─────────────────────────────────────────────────────────────

async def autods_search_products(keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """Search AutoDS for products across their sourced marketplaces."""
    if not settings.autods_api_key:
        return _mock_product_search(keyword, page_size)

    headers = {"api-key": settings.autods_api_key}
    params = {"keyword": keyword, "page": page, "limit": page_size}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://api.autods.com/v2/products/search",
            headers=headers,
            params=params,
        )
        r.raise_for_status()
        return r.json()


# ── Printful adapter ───────────────────────────────────────────────────────────

async def printful_get_products(keyword: str = "", page_size: int = 20) -> dict[str, Any]:
    """Search Printful print-on-demand catalog."""
    if not settings.printful_api_key:
        return _mock_printful_catalog(keyword, page_size)

    headers = {"Authorization": f"Bearer {settings.printful_api_key}"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.printful.com/products", headers=headers)
        r.raise_for_status()
        data = r.json()

    products = data.get("result", [])
    if keyword:
        kw = keyword.lower()
        products = [
            p for p in products
            if kw in p.get("type", "").lower() or kw in p.get("type_name", "").lower()
        ]
    return {"products": products[:page_size], "total": len(products), "source": "printful"}


async def printful_get_product_variants(sync_product_id: str) -> dict[str, Any]:
    """Get variants and pricing for a specific Printful product."""
    if not settings.printful_api_key:
        return {"sync_product_id": sync_product_id, "source": "mock", "variants": []}

    headers = {"Authorization": f"Bearer {settings.printful_api_key}"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"https://api.printful.com/sync/products/{sync_product_id}",
            headers=headers,
        )
        r.raise_for_status()
        return r.json()


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


def _mock_place_order(product_id: str, quantity: int, name: str) -> dict[str, Any]:
    return {
        "success": True,
        "supplier_order_id": f"MOCK-{uuid.uuid4().hex[:8].upper()}",
        "product_id": product_id,
        "quantity": quantity,
        "recipient": name,
        "estimated_shipping_days": 12,
        "source": "mock",
    }


def _mock_tracking(supplier_order_id: str) -> dict[str, Any]:
    return {
        "supplier_order_id": supplier_order_id,
        "status": "in_transit",
        "tracking_number": f"MOCK{supplier_order_id[-6:].upper()}",
        "tracking_url": "https://track.example.com",
        "estimated_delivery": "7-14 days",
        "source": "mock",
    }


def _mock_printful_catalog(keyword: str, count: int) -> dict[str, Any]:
    templates = [
        {"type": "T-SHIRT", "type_name": "Unisex Staple T-Shirt | Bella + Canvas 3001"},
        {"type": "HOODIE", "type_name": "Unisex Heavy Blend Hoodie | Gildan 18500"},
        {"type": "MUG", "type_name": "White Glossy Mug"},
        {"type": "POSTER", "type_name": "Enhanced Matte Paper Poster"},
        {"type": "PHONE-CASE", "type_name": "Tough Phone Case"},
    ]
    kw = keyword.lower() if keyword else ""
    products = [
        {
            "id": f"mock_pf_{t['type'].lower()}",
            "type": t["type"],
            "type_name": t["type_name"],
            "base_price_usd": round(8.0 + i * 4.5, 2),
            "image_url": f"https://placeholder.com/300x300?text={t['type']}",
            "source": "mock",
        }
        for i, t in enumerate(templates)
        if not kw or kw in t["type"].lower() or kw in t["type_name"].lower()
    ]
    return {"products": products[:count], "total": len(products), "source": "mock"}


# ── Tool schemas ───────────────────────────────────────────────────────────────

class SupplierTools:
    SCHEMAS = [
        {
            "name": "search_supplier_products",
            "description": (
                "Search any configured supplier platform for dropshippable products. "
                "Platforms: cj (CJ Dropshipping), aliexpress, zendrop, spocket, autods, printful."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Product search keyword"},
                    "platform": {
                        "type": "string",
                        "enum": ["cj", "aliexpress", "zendrop", "spocket", "autods", "printful"],
                        "description": "Supplier platform to search",
                    },
                    "page_size": {"type": "integer", "default": 20},
                },
                "required": ["keyword"],
            },
        },
        {
            "name": "get_aliexpress_product_detail",
            "description": (
                "Fetch full product details from AliExpress by product ID — description, images, "
                "variants, pricing, and shipping info. Use after search to evaluate a specific product."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "AliExpress product ID"},
                },
                "required": ["product_id"],
            },
        },
        {
            "name": "place_supplier_order",
            "description": "Place a dropship order with a supplier to ship directly to a customer.",
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
    async def get_aliexpress_product_detail(product_id: str) -> dict[str, Any]:
        return await aliexpress_get_product(product_id)

    @staticmethod
    async def search_supplier_products(
        keyword: str, platform: str = "cj", page_size: int = 20
    ) -> dict[str, Any]:
        if platform == "aliexpress":
            return await aliexpress_search_products(keyword, page_size=page_size)
        if platform == "zendrop":
            return await zendrop_search_products(keyword, page_size=page_size)
        if platform == "spocket":
            return await spocket_search_products(keyword, page_size=page_size)
        if platform == "autods":
            return await autods_search_products(keyword, page_size=page_size)
        if platform == "printful":
            return await printful_get_products(keyword, page_size=page_size)
        return await cj_search_products(keyword, page_size=page_size)

    @staticmethod
    async def place_supplier_order(**kwargs) -> dict[str, Any]:
        return await cj_place_order(**{
            "product_id": kwargs["supplier_product_id"],
            "quantity": kwargs["quantity"],
            "shipping_name": kwargs["shipping_name"],
            "shipping_address": kwargs["shipping_address"],
            "shipping_city": kwargs["shipping_city"],
            "shipping_country": kwargs["shipping_country"],
            "shipping_zip": kwargs["shipping_zip"],
            "shipping_phone": kwargs["shipping_phone"],
        })

    @staticmethod
    async def get_supplier_tracking(supplier_order_id: str) -> dict[str, Any]:
        return await get_tracking_info(supplier_order_id)

    MAP: dict  # populated below


SupplierTools.MAP = {
    "search_supplier_products": SupplierTools.search_supplier_products,
    "get_aliexpress_product_detail": SupplierTools.get_aliexpress_product_detail,
    "place_supplier_order": SupplierTools.place_supplier_order,
    "get_supplier_tracking": SupplierTools.get_supplier_tracking,
}
