"""
Supplier sourcing management tools – used exclusively by SupplierSourcingAgent.
Handles supplier discovery, DB registration, connection testing, and onboarding docs.
"""

import json
from datetime import datetime
from typing import Any

import httpx

from config import get_settings
from database import AsyncSessionLocal, BusinessMetric, Supplier
from sqlalchemy import select

settings = get_settings()


# ── Static onboarding reference ────────────────────────────────────────────────

_SUPPLIER_INFO: dict[str, dict] = {
    "dsers": {
        "name": "DSers",
        "signup_url": "https://www.dsers.com",
        "env_keys": ["DSERS_API_KEY"],
        "setup_steps": [
            "1. Sign up at https://www.dsers.com.",
            "2. Upgrade to Advanced plan (~$20/mo) or higher for API access.",
            "3. Go to Settings > API and generate your Partner API key.",
            "4. Set DSERS_API_KEY in your .env file.",
            "5. In DSers, connect your AliExpress account (Settings > Bind Account).",
        ],
        "pricing_model": "$20-49/month subscription",
        "product_types": "All AliExpress products — routes orders through DSers to AliExpress",
        "avg_shipping_days": "7-30 days (same as AliExpress)",
        "strengths": "Official AliExpress partner, automates AliExpress order placement, tracking sync",
        "weaknesses": "Monthly fee, still relies on AliExpress shipping times",
    },
    "aliexpress": {
        "name": "AliExpress",
        "signup_url": "https://portals.aliexpress.com/",
        "env_keys": ["ALIEXPRESS_APP_KEY", "ALIEXPRESS_APP_SECRET"],
        "setup_steps": [
            "1. Go to https://portals.aliexpress.com/ and create a developer account.",
            "2. Create a new app under 'My Apps'.",
            "3. Copy the App Key and App Secret.",
            "4. Set ALIEXPRESS_APP_KEY and ALIEXPRESS_APP_SECRET in your .env file.",
        ],
        "pricing_model": "No monthly fee. Pay per product.",
        "product_types": "Electronics, home, fashion, sports, beauty – huge catalog",
        "avg_shipping_days": "7-30 days",
        "strengths": "Massive catalog, lowest prices, no subscription",
        "weaknesses": "Long shipping from China, quality varies",
    },
    "cjdropshipping": {
        "name": "CJ Dropshipping",
        "signup_url": "https://cjdropshipping.com",
        "env_keys": ["CJDROPSHIPPING_API_KEY", "CJDROPSHIPPING_EMAIL"],
        "setup_steps": [
            "1. Sign up at https://cjdropshipping.com.",
            "2. Go to 'My CJ' > 'API Access' and generate your API key.",
            "3. Set CJDROPSHIPPING_API_KEY (your API key / password) and CJDROPSHIPPING_EMAIL in .env.",
        ],
        "pricing_model": "No monthly fee. Pay per product.",
        "product_types": "Electronics, home goods, fashion, tools",
        "avg_shipping_days": "5-20 days (US warehouse available)",
        "strengths": "US warehouse option, product sourcing service, good API",
        "weaknesses": "Smaller catalog than AliExpress",
    },
    "zendrop": {
        "name": "Zendrop",
        "signup_url": "https://app.zendrop.com/register",
        "env_keys": ["ZENDROP_API_KEY"],
        "setup_steps": [
            "1. Sign up at https://app.zendrop.com/register.",
            "2. Upgrade to Plus ($49/mo) or Pro ($79/mo) for API access.",
            "3. Go to Settings > API and generate your API key.",
            "4. Set ZENDROP_API_KEY in your .env file.",
        ],
        "pricing_model": "$49-79/month subscription + product costs",
        "product_types": "Curated US products, supplements, lifestyle, branded goods",
        "avg_shipping_days": "3-7 days (US), 7-14 days international",
        "strengths": "Fast US shipping, curated quality, auto-fulfillment",
        "weaknesses": "Monthly fee required for API, smaller catalog",
    },
    "spocket": {
        "name": "Spocket",
        "signup_url": "https://app.spocket.co/register",
        "env_keys": ["SPOCKET_API_KEY"],
        "setup_steps": [
            "1. Sign up at https://app.spocket.co/register.",
            "2. Subscribe to the Unicorn plan ($99/mo) for API access.",
            "3. Go to Account > API and generate your API key.",
            "4. Set SPOCKET_API_KEY in your .env file.",
        ],
        "pricing_model": "$49-99/month subscription + product costs",
        "product_types": "Fashion, jewelry, home decor, beauty, food from EU/US suppliers",
        "avg_shipping_days": "2-5 days (US/EU suppliers)",
        "strengths": "EU/US suppliers, fastest shipping, branded invoicing, premium feel",
        "weaknesses": "Higher subscription cost, premium product pricing",
    },
    "autods": {
        "name": "AutoDS",
        "signup_url": "https://platform.autods.com/register",
        "env_keys": ["AUTODS_API_KEY"],
        "setup_steps": [
            "1. Sign up at https://platform.autods.com/register.",
            "2. Choose a plan ($39-99/mo depending on product count).",
            "3. Go to Settings > API and generate your API key.",
            "4. Set AUTODS_API_KEY in your .env file.",
        ],
        "pricing_model": "$39-99/month subscription",
        "product_types": "Multi-source: Amazon, eBay, Walmart, AliExpress, Alibaba, Costco",
        "avg_shipping_days": "Varies by source marketplace (1-30 days)",
        "strengths": "Access to Amazon/Walmart/eBay products, price monitoring, auto-order",
        "weaknesses": "Complex setup, relies on third-party listings, variable shipping",
    },
    "printful": {
        "name": "Printful",
        "signup_url": "https://www.printful.com/auth/register",
        "env_keys": ["PRINTFUL_API_KEY"],
        "setup_steps": [
            "1. Sign up free at https://www.printful.com/auth/register.",
            "2. Go to Settings > API Access.",
            "3. Click 'Generate API key' and copy it.",
            "4. Set PRINTFUL_API_KEY in your .env file.",
        ],
        "pricing_model": "No monthly fee. Pay per item printed + fulfilled.",
        "product_types": "Custom print-on-demand: t-shirts, hoodies, mugs, phone cases, posters, bags",
        "avg_shipping_days": "2-5 days production + 2-5 days shipping (US)",
        "strengths": "No monthly fee, custom branding, no inventory risk, differentiation from competitors",
        "weaknesses": "Higher per-unit cost vs bulk, production lead time adds to shipping",
    },
}


# ── Config status helpers ──────────────────────────────────────────────────────

def _is_configured(platform: str) -> bool:
    return {
        "dsers":          bool(settings.dsers_api_key),
        "aliexpress":     bool(settings.aliexpress_app_key),
        "cjdropshipping": bool(settings.cjdropshipping_api_key and settings.cjdropshipping_email),
        "zendrop":        bool(settings.zendrop_api_key),
        "spocket":        bool(settings.spocket_api_key),
        "autods":         bool(settings.autods_api_key),
        "printful":       bool(settings.printful_api_key),
    }.get(platform, False)


# ── Tool implementations ───────────────────────────────────────────────────────

async def list_configured_suppliers() -> dict[str, Any]:
    """Return configuration and status for all known supplier platforms."""
    result = {}
    for platform, info in _SUPPLIER_INFO.items():
        configured = _is_configured(platform)
        result[platform] = {
            "name": info["name"],
            "configured": configured,
            "status": "ready" if configured else "missing_api_keys",
            "env_keys_needed": info["env_keys"],
            "pricing_model": info["pricing_model"],
            "avg_shipping_days": info["avg_shipping_days"],
            "product_types": info["product_types"],
        }
    return {"suppliers": result, "total": len(result)}


async def test_supplier_connection(platform: str) -> dict[str, Any]:
    """Verify API connectivity for a supplier platform. Returns status and any error details."""
    if not _is_configured(platform):
        info = _SUPPLIER_INFO.get(platform, {})
        return {
            "platform": platform,
            "status": "not_configured",
            "message": f"API keys not set. Required: {info.get('env_keys', [])}",
            "signup_url": info.get("signup_url", ""),
        }
    try:
        return await _ping(platform)
    except httpx.HTTPStatusError as e:
        return {"platform": platform, "status": "http_error", "code": e.response.status_code, "detail": str(e)}
    except Exception as e:
        return {"platform": platform, "status": "error", "detail": str(e)}


async def _ping(platform: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        if platform == "dsers":
            r = await client.get(
                "https://openapi.dsers.com/open/v1/orders",
                headers={"api-token": settings.dsers_api_key},
                params={"page": 1, "page_size": 1},
            )
        elif platform == "aliexpress":
            r = await client.get(
                "https://api.aliexpress.com/router/rest",
                params={
                    "method": "aliexpress.affiliate.product.query",
                    "app_key": settings.aliexpress_app_key,
                    "keywords": "test",
                    "page_no": 1,
                    "page_size": 1,
                    "target_currency": "USD",
                    "target_language": "EN",
                    "tracking_id": "dropship",
                },
            )
        elif platform == "cjdropshipping":
            r = await client.post(
                "https://developers.cjdropshipping.com/api2.0/v1/authentication/getAccessToken",
                json={"email": settings.cjdropshipping_email, "password": settings.cjdropshipping_api_key},
            )
            token = r.json().get("data", {}).get("accessToken")
            return {"platform": platform, "status": "connected" if token else "auth_failed", "http_status": r.status_code}
        elif platform == "zendrop":
            r = await client.get(
                "https://api.zendrop.com/api/products",
                headers={"Authorization": f"Bearer {settings.zendrop_api_key}"},
                params={"limit": 1},
            )
        elif platform == "spocket":
            r = await client.get(
                "https://api.spocket.co/products",
                headers={"Authorization": f"Bearer {settings.spocket_api_key}"},
                params={"per_page": 1},
            )
        elif platform == "autods":
            r = await client.get(
                "https://api.autods.com/v2/products/search",
                headers={"api-key": settings.autods_api_key},
                params={"keyword": "test", "limit": 1},
            )
        elif platform == "printful":
            r = await client.get(
                "https://api.printful.com/products",
                headers={"Authorization": f"Bearer {settings.printful_api_key}"},
            )
        else:
            return {"platform": platform, "status": "unknown_platform"}

        r.raise_for_status()
        return {"platform": platform, "status": "connected", "http_status": r.status_code}


async def register_supplier(
    name: str,
    platform: str,
    notes: str = "",
    processing_days: int = 2,
    shipping_days_min: int = 5,
    shipping_days_max: int = 21,
) -> dict[str, Any]:
    """Register or update a supplier record in the database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Supplier).where(Supplier.platform == platform)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.name = name
            existing.notes = notes
            existing.processing_days = processing_days
            existing.shipping_days_min = shipping_days_min
            existing.shipping_days_max = shipping_days_max
            existing.is_active = True
            await session.commit()
            return {"action": "updated", "platform": platform, "name": name, "id": existing.id}

        supplier = Supplier(
            name=name,
            platform=platform,
            notes=notes,
            processing_days=processing_days,
            shipping_days_min=shipping_days_min,
            shipping_days_max=shipping_days_max,
            is_active=True,
        )
        session.add(supplier)
        await session.commit()
        await session.refresh(supplier)
        return {"action": "registered", "platform": platform, "name": name, "id": supplier.id}


async def get_registered_suppliers() -> dict[str, Any]:
    """List all suppliers currently registered in the database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Supplier))
        rows = result.scalars().all()
        return {
            "suppliers": [
                {
                    "id": s.id,
                    "name": s.name,
                    "platform": s.platform,
                    "is_active": s.is_active,
                    "rating": s.rating,
                    "processing_days": s.processing_days,
                    "shipping_days_min": s.shipping_days_min,
                    "shipping_days_max": s.shipping_days_max,
                    "notes": s.notes,
                }
                for s in rows
            ],
            "total": len(rows),
        }


async def get_supplier_onboarding_info(platform: str) -> dict[str, Any]:
    """Get the signup URL, required env keys, and step-by-step setup instructions for a platform."""
    info = _SUPPLIER_INFO.get(platform)
    if not info:
        return {
            "error": f"Unknown platform '{platform}'.",
            "known_platforms": list(_SUPPLIER_INFO.keys()),
        }
    return {
        "platform": platform,
        "configured": _is_configured(platform),
        **info,
    }


async def record_supplier_evaluation(
    platform: str,
    connection_status: str,
    product_count_found: int = 0,
    avg_cost_usd: float = 0.0,
    notes: str = "",
) -> dict[str, Any]:
    """Persist a supplier evaluation as a business metric for audit history."""
    async with AsyncSessionLocal() as session:
        session.add(BusinessMetric(
            metric_name=f"supplier_evaluation_{platform}",
            metric_value=float(product_count_found),
            metric_data=json.dumps({
                "platform": platform,
                "connection_status": connection_status,
                "product_count_found": product_count_found,
                "avg_cost_usd": avg_cost_usd,
                "notes": notes,
                "evaluated_at": datetime.utcnow().isoformat(),
            }),
        ))
        await session.commit()
    return {"status": "recorded", "platform": platform}


# ── Tool schema class ──────────────────────────────────────────────────────────

class SupplierSourcingTools:
    SCHEMAS = [
        {
            "name": "list_configured_suppliers",
            "description": (
                "Check all supplier platforms and return which ones have API keys "
                "configured, their pricing model, shipping speed, and product types."
            ),
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "test_supplier_connection",
            "description": (
                "Test API connectivity for a specific supplier platform. "
                "Returns 'connected', 'not_configured', or 'error' with details."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "enum": ["dsers", "aliexpress", "cjdropshipping", "zendrop", "spocket", "autods", "printful"],
                    }
                },
                "required": ["platform"],
            },
        },
        {
            "name": "register_supplier",
            "description": (
                "Register or update a supplier in the database after confirming their connection. "
                "Call this for every successfully connected platform."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Human-readable name (e.g. 'CJ Dropshipping')"},
                    "platform": {
                        "type": "string",
                        "description": "Platform slug: aliexpress | cjdropshipping | zendrop | spocket | autods | printful",
                    },
                    "notes": {"type": "string", "description": "Notes about this supplier"},
                    "processing_days": {"type": "integer", "description": "Typical order processing time in days"},
                    "shipping_days_min": {"type": "integer", "description": "Fastest shipping in days"},
                    "shipping_days_max": {"type": "integer", "description": "Slowest shipping in days"},
                },
                "required": ["name", "platform"],
            },
        },
        {
            "name": "get_registered_suppliers",
            "description": "List all suppliers currently registered in the database.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_supplier_onboarding_info",
            "description": (
                "Get the signup URL, required API keys, and step-by-step setup instructions "
                "for a supplier platform. Use this to document what's needed for unconfigured platforms."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "enum": ["dsers", "aliexpress", "cjdropshipping", "zendrop", "spocket", "autods", "printful"],
                    }
                },
                "required": ["platform"],
            },
        },
        {
            "name": "record_supplier_evaluation",
            "description": "Log the result of a supplier evaluation to business metrics for audit history.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string"},
                    "connection_status": {
                        "type": "string",
                        "enum": ["connected", "not_configured", "error", "auth_failed"],
                    },
                    "product_count_found": {"type": "integer", "description": "Products found in search"},
                    "avg_cost_usd": {"type": "number", "description": "Average cost of found products"},
                    "notes": {"type": "string"},
                },
                "required": ["platform", "connection_status"],
            },
        },
    ]

    MAP: dict  # populated below


SupplierSourcingTools.MAP = {
    "list_configured_suppliers": list_configured_suppliers,
    "test_supplier_connection": test_supplier_connection,
    "register_supplier": register_supplier,
    "get_registered_suppliers": get_registered_suppliers,
    "get_supplier_onboarding_info": get_supplier_onboarding_info,
    "record_supplier_evaluation": record_supplier_evaluation,
}
