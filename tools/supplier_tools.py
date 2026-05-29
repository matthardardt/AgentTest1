"""
Supplier integration tools.
Active platforms: AliExpress (search) + DSers (AliExpress orders),
Zendrop, Spocket, AutoDS, Printful.
Falls back to mock data when API keys are not configured.
"""

import uuid
from typing import Any

import httpx

from config import get_settings

settings = get_settings()

_SHIPPING = ["shipping_name", "shipping_address", "shipping_city",
             "shipping_country", "shipping_zip", "shipping_phone"]


# ── AliExpress adapter (search only — orders go via DSers) ────────────────────

async def aliexpress_search_products(keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    if not settings.aliexpress_app_key:
        return _mock_search(keyword, page_size)
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
    if not settings.aliexpress_app_key:
        return _mock_detail(product_id)
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


# ── DSers adapter (AliExpress order automation) ───────────────────────────────
# Docs: https://www.dsers.com/partner-api/

async def dsers_place_order(
    product_id: str, variant_id: str, quantity: int,
    shipping_name: str, shipping_address: str, shipping_city: str,
    shipping_country: str, shipping_zip: str, shipping_phone: str,
) -> dict[str, Any]:
    if not settings.dsers_api_key:
        return _mock_order(product_id, quantity, shipping_name)
    headers = {"api-token": settings.dsers_api_key, "Content-Type": "application/json"}
    payload = {
        "products": [{"product_id": product_id, "variant_id": variant_id, "quantity": quantity}],
        "shipping_address": {
            "name": shipping_name, "address1": shipping_address,
            "city": shipping_city, "country_code": shipping_country,
            "zip": shipping_zip, "phone": shipping_phone,
        },
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://openapi.dsers.com/open/v1/orders/create",
                              headers=headers, json=payload)
        r.raise_for_status()
        return r.json()


async def dsers_get_order(order_id: str) -> dict[str, Any]:
    if not settings.dsers_api_key:
        return _mock_tracking(order_id)
    headers = {"api-token": settings.dsers_api_key}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"https://openapi.dsers.com/open/v1/orders/{order_id}",
                             headers=headers)
        r.raise_for_status()
        return r.json()


# ── Zendrop adapter ────────────────────────────────────────────────────────────

async def zendrop_search_products(keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    if not settings.zendrop_api_key:
        return _mock_search(keyword, page_size)
    headers = {"Authorization": f"Bearer {settings.zendrop_api_key}"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.zendrop.com/api/products",
                             headers=headers, params={"search": keyword, "page": page, "limit": page_size})
        r.raise_for_status()
        return r.json()


async def zendrop_place_order(
    product_id: str, variant_id: str, quantity: int,
    shipping_name: str, shipping_address: str, shipping_city: str,
    shipping_country: str, shipping_zip: str, shipping_phone: str,
) -> dict[str, Any]:
    if not settings.zendrop_api_key:
        return _mock_order(product_id, quantity, shipping_name)
    headers = {"Authorization": f"Bearer {settings.zendrop_api_key}"}
    payload = {
        "product_id": product_id, "variant_id": variant_id, "quantity": quantity,
        "shipping": {"name": shipping_name, "address": shipping_address, "city": shipping_city,
                     "country": shipping_country, "zip": shipping_zip, "phone": shipping_phone},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://api.zendrop.com/api/orders",
                              headers=headers, json=payload)
        r.raise_for_status()
        return r.json()


async def zendrop_get_order(order_id: str) -> dict[str, Any]:
    if not settings.zendrop_api_key:
        return _mock_tracking(order_id)
    headers = {"Authorization": f"Bearer {settings.zendrop_api_key}"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"https://api.zendrop.com/api/orders/{order_id}", headers=headers)
        r.raise_for_status()
        return r.json()


# ── Spocket adapter ────────────────────────────────────────────────────────────

async def spocket_search_products(keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    if not settings.spocket_api_key:
        return _mock_search(keyword, page_size)
    headers = {"Authorization": f"Bearer {settings.spocket_api_key}"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.spocket.co/products",
                             headers=headers, params={"q": keyword, "page": page, "per_page": page_size})
        r.raise_for_status()
        return r.json()


async def spocket_place_order(
    product_id: str, variant_id: str, quantity: int,
    shipping_name: str, shipping_address: str, shipping_city: str,
    shipping_country: str, shipping_zip: str, shipping_phone: str,
) -> dict[str, Any]:
    if not settings.spocket_api_key:
        return _mock_order(product_id, quantity, shipping_name)
    headers = {"Authorization": f"Bearer {settings.spocket_api_key}"}
    payload = {
        "variant_id": variant_id, "quantity": quantity,
        "shipping_address": {"name": shipping_name, "address1": shipping_address,
                             "city": shipping_city, "country": shipping_country,
                             "zip": shipping_zip, "phone": shipping_phone},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://api.spocket.co/orders", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()


async def spocket_get_order(order_id: str) -> dict[str, Any]:
    if not settings.spocket_api_key:
        return _mock_tracking(order_id)
    headers = {"Authorization": f"Bearer {settings.spocket_api_key}"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"https://api.spocket.co/orders/{order_id}", headers=headers)
        r.raise_for_status()
        return r.json()


# ── AutoDS adapter ─────────────────────────────────────────────────────────────

async def autods_search_products(keyword: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    if not settings.autods_api_key:
        return _mock_search(keyword, page_size)
    headers = {"api-key": settings.autods_api_key}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.autods.com/v2/products/search",
                             headers=headers, params={"keyword": keyword, "page": page, "limit": page_size})
        r.raise_for_status()
        return r.json()


async def autods_place_order(
    product_id: str, variant_id: str, quantity: int,
    shipping_name: str, shipping_address: str, shipping_city: str,
    shipping_country: str, shipping_zip: str, shipping_phone: str,
) -> dict[str, Any]:
    if not settings.autods_api_key:
        return _mock_order(product_id, quantity, shipping_name)
    headers = {"api-key": settings.autods_api_key}
    payload = {
        "product_id": product_id, "variant_id": variant_id, "quantity": quantity,
        "shipping_address": {"name": shipping_name, "address1": shipping_address,
                             "city": shipping_city, "country_code": shipping_country,
                             "zip": shipping_zip, "phone": shipping_phone},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://api.autods.com/v2/orders",
                              headers=headers, json=payload)
        r.raise_for_status()
        return r.json()


async def autods_get_order(order_id: str) -> dict[str, Any]:
    if not settings.autods_api_key:
        return _mock_tracking(order_id)
    headers = {"api-key": settings.autods_api_key}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"https://api.autods.com/v2/orders/{order_id}", headers=headers)
        r.raise_for_status()
        return r.json()


# ── Printful adapter ───────────────────────────────────────────────────────────

async def printful_get_products(keyword: str = "", page_size: int = 20) -> dict[str, Any]:
    if not settings.printful_api_key:
        return _mock_printful(keyword, page_size)
    headers = {"Authorization": f"Bearer {settings.printful_api_key}"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.printful.com/products", headers=headers)
        r.raise_for_status()
    products = r.json().get("result", [])
    if keyword:
        kw = keyword.lower()
        products = [p for p in products
                    if kw in p.get("type", "").lower() or kw in p.get("type_name", "").lower()]
    return {"products": products[:page_size], "total": len(products), "source": "printful"}


async def printful_get_product_variants(sync_product_id: str) -> dict[str, Any]:
    if not settings.printful_api_key:
        return {"sync_product_id": sync_product_id, "source": "mock", "variants": []}
    headers = {"Authorization": f"Bearer {settings.printful_api_key}"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"https://api.printful.com/sync/products/{sync_product_id}",
                             headers=headers)
        r.raise_for_status()
        return r.json()


async def printful_place_order(
    product_id: str, variant_id: str, quantity: int,
    shipping_name: str, shipping_address: str, shipping_city: str,
    shipping_country: str, shipping_zip: str, shipping_phone: str,
) -> dict[str, Any]:
    if not settings.printful_api_key:
        return _mock_order(product_id, quantity, shipping_name)
    headers = {"Authorization": f"Bearer {settings.printful_api_key}"}
    payload = {
        "recipient": {"name": shipping_name, "address1": shipping_address,
                      "city": shipping_city, "country_code": shipping_country,
                      "zip": shipping_zip, "phone": shipping_phone},
        "items": [{"sync_variant_id": variant_id or product_id, "quantity": quantity}],
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://api.printful.com/orders", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()


async def printful_get_order(order_id: str) -> dict[str, Any]:
    if not settings.printful_api_key:
        return _mock_tracking(order_id)
    headers = {"Authorization": f"Bearer {settings.printful_api_key}"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"https://api.printful.com/orders/{order_id}", headers=headers)
        r.raise_for_status()
        return r.json()


# ── Mock data ─────────────────────────────────────────────────────────────────

def _mock_search(keyword: str, count: int) -> dict[str, Any]:
    products = [
        {
            "product_id": f"mock_{keyword.replace(' ', '_')}_{i}",
            "name": f"{keyword.title()} Product {i + 1}",
            "price_usd": round(5.0 + i * 3.5, 2),
            "image_url": f"https://placeholder.com/300x300?text={keyword}+{i}",
            "rating": round(4.0 + (i % 3) * 0.3, 1),
            "orders_count": 100 + i * 50,
            "shipping_days": 7 + i * 2,
        }
        for i in range(min(count, 5))
    ]
    return {"products": products, "total": count, "source": "mock"}


def _mock_detail(product_id: str) -> dict[str, Any]:
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


def _mock_order(product_id: str, quantity: int, name: str) -> dict[str, Any]:
    return {
        "success": True,
        "supplier_order_id": f"MOCK-{uuid.uuid4().hex[:8].upper()}",
        "product_id": product_id,
        "quantity": quantity,
        "recipient": name,
        "estimated_shipping_days": 12,
        "source": "mock",
    }


def _mock_tracking(order_id: str) -> dict[str, Any]:
    return {
        "supplier_order_id": order_id,
        "status": "in_transit",
        "tracking_number": f"MOCK{order_id[-6:].upper()}",
        "tracking_url": "https://track.example.com",
        "estimated_delivery": "7-14 days",
        "source": "mock",
    }


def _mock_printful(keyword: str, count: int) -> dict[str, Any]:
    templates = [
        {"type": "T-SHIRT",    "type_name": "Unisex Staple T-Shirt | Bella + Canvas 3001"},
        {"type": "HOODIE",     "type_name": "Unisex Heavy Blend Hoodie | Gildan 18500"},
        {"type": "MUG",        "type_name": "White Glossy Mug"},
        {"type": "POSTER",     "type_name": "Enhanced Matte Paper Poster"},
        {"type": "PHONE-CASE", "type_name": "Tough Phone Case"},
    ]
    kw = keyword.lower() if keyword else ""
    products = [
        {"id": f"mock_pf_{t['type'].lower()}", **t,
         "base_price_usd": round(8.0 + i * 4.5, 2), "source": "mock"}
        for i, t in enumerate(templates)
        if not kw or kw in t["type"].lower() or kw in t["type_name"].lower()
    ]
    return {"products": products[:count], "total": len(products), "source": "mock"}


# ── Tool schemas & dispatch ────────────────────────────────────────────────────

_ORDER_PLATFORMS = ["dsers", "zendrop", "spocket", "autods", "printful"]
_SEARCH_PLATFORMS = ["aliexpress", "zendrop", "spocket", "autods", "printful"]


class SupplierTools:
    SCHEMAS = [
        {
            "name": "search_supplier_products",
            "description": (
                "Search a supplier platform for dropshippable products. "
                "Platforms: aliexpress, zendrop, spocket, autods, printful."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "platform": {
                        "type": "string",
                        "enum": _SEARCH_PLATFORMS,
                        "description": "Supplier platform to search",
                    },
                    "page_size": {"type": "integer", "default": 20},
                },
                "required": ["keyword", "platform"],
            },
        },
        {
            "name": "get_aliexpress_product_detail",
            "description": (
                "Fetch full AliExpress product details by product ID — description, images, "
                "variants, pricing, shipping. Use before adding to catalog."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
        {
            "name": "place_supplier_order",
            "description": (
                "Place a dropship order to ship directly to a customer. "
                "Check the product's supplier_platform field (from get_product) to choose the platform: "
                "aliexpress → 'dsers', zendrop → 'zendrop', spocket → 'spocket', "
                "autods → 'autods', printful → 'printful'."
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
                    "platform": {
                        "type": "string",
                        "enum": _ORDER_PLATFORMS,
                        "description": "Fulfillment platform matching the product's source",
                    },
                    "variant_id": {
                        "type": "string",
                        "description": "Variant/SKU ID from the supplier (required for dsers, printful)",
                    },
                },
                "required": ["supplier_product_id", "quantity", "shipping_name",
                             "shipping_address", "shipping_city", "shipping_country",
                             "shipping_zip", "shipping_phone", "platform"],
            },
        },
        {
            "name": "get_supplier_tracking",
            "description": "Get shipping tracking for a supplier order. Pass the same platform used when placing the order.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "supplier_order_id": {"type": "string"},
                    "platform": {
                        "type": "string",
                        "enum": _ORDER_PLATFORMS,
                        "description": "Platform the order was placed through",
                    },
                },
                "required": ["supplier_order_id", "platform"],
            },
        },
    ]

    @staticmethod
    async def search_supplier_products(keyword: str, platform: str, page_size: int = 20) -> dict[str, Any]:
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
        return {"error": f"Unknown search platform: {platform}"}

    @staticmethod
    async def get_aliexpress_product_detail(product_id: str) -> dict[str, Any]:
        return await aliexpress_get_product(product_id)

    @staticmethod
    async def place_supplier_order(**kw) -> dict[str, Any]:
        p = kw["platform"]
        args = dict(
            product_id=kw["supplier_product_id"],
            variant_id=kw.get("variant_id", ""),
            quantity=kw["quantity"],
            shipping_name=kw["shipping_name"],
            shipping_address=kw["shipping_address"],
            shipping_city=kw["shipping_city"],
            shipping_country=kw["shipping_country"],
            shipping_zip=kw["shipping_zip"],
            shipping_phone=kw["shipping_phone"],
        )
        if p == "dsers":     return await dsers_place_order(**args)
        if p == "zendrop":   return await zendrop_place_order(**args)
        if p == "spocket":   return await spocket_place_order(**args)
        if p == "autods":    return await autods_place_order(**args)
        if p == "printful":  return await printful_place_order(**args)
        return {"error": f"Unknown order platform: {p}"}

    @staticmethod
    async def get_supplier_tracking(supplier_order_id: str, platform: str) -> dict[str, Any]:
        if platform == "dsers":    return await dsers_get_order(supplier_order_id)
        if platform == "zendrop":  return await zendrop_get_order(supplier_order_id)
        if platform == "spocket":  return await spocket_get_order(supplier_order_id)
        if platform == "autods":   return await autods_get_order(supplier_order_id)
        if platform == "printful": return await printful_get_order(supplier_order_id)
        return {"error": f"Unknown tracking platform: {platform}"}

    MAP: dict  # populated below


SupplierTools.MAP = {
    "search_supplier_products":      SupplierTools.search_supplier_products,
    "get_aliexpress_product_detail":  SupplierTools.get_aliexpress_product_detail,
    "place_supplier_order":          SupplierTools.place_supplier_order,
    "get_supplier_tracking":         SupplierTools.get_supplier_tracking,
}
