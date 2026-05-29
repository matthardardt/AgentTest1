"""
Marketing tools for Vendo's Deals — content generation, promo codes, campaign tracking.
"""

import json
import random
import string
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func

from database import (
    AsyncSessionLocal, Product, ProductStatus, PromoCode,
    MarketingCampaign, BusinessMetric, Order, OrderItem,
)


# ── Deal discovery ─────────────────────────────────────────────────────────────

async def get_featured_deals(limit: int = 10) -> dict[str, Any]:
    """Get the best deals in the store — highest savings, best margin products to promote."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Product).where(Product.status == ProductStatus.ACTIVE)
        )
        products = result.scalars().all()

    deals = []
    for p in products:
        savings_pct = 0.0
        if p.compare_at_price and p.compare_at_price > p.selling_price:
            savings_pct = round((p.compare_at_price - p.selling_price) / p.compare_at_price * 100, 1)

        margin_pct = 0.0
        if p.cost_price and p.cost_price > 0:
            margin_pct = round((p.selling_price - p.cost_price) / p.selling_price * 100, 1)

        tags = json.loads(p.tags or "[]")
        deals.append({
            "id": p.id,
            "name": p.name,
            "description": (p.description or "")[:300],
            "category": p.category,
            "selling_price": p.selling_price,
            "compare_at_price": p.compare_at_price,
            "savings_pct": savings_pct,
            "margin_pct": margin_pct,
            "tags": tags,
            "images": json.loads(p.images or "[]")[:1],
        })

    deals.sort(key=lambda d: (d["savings_pct"], d["margin_pct"]), reverse=True)
    return {"deals": deals[:limit], "total_active": len(products)}


# ── Promo code management ──────────────────────────────────────────────────────

async def create_promo_code(
    code: str,
    discount_value: float,
    discount_type: str = "percent",
    description: str = "",
    min_order_value: float = 0.0,
    valid_days: int = 7,
    max_uses: int | None = None,
    campaign_name: str = "",
) -> dict[str, Any]:
    """Create a discount promo code in the database."""
    code = code.upper().strip()
    valid_until = datetime.utcnow() + timedelta(days=valid_days)

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(PromoCode).where(PromoCode.code == code))
        if existing.scalar_one_or_none():
            return {"success": False, "error": f"Code {code} already exists"}

        promo = PromoCode(
            code=code,
            description=description,
            discount_type=discount_type,
            discount_value=discount_value,
            min_order_value=min_order_value,
            max_uses=max_uses,
            valid_until=valid_until,
            campaign_name=campaign_name,
        )
        db.add(promo)
        await db.commit()
        return {
            "success": True,
            "code": code,
            "discount": f"{discount_value}{'%' if discount_type == 'percent' else '$'} off",
            "valid_until": valid_until.strftime("%Y-%m-%d"),
            "min_order": min_order_value,
        }


async def list_promo_codes(active_only: bool = True) -> dict[str, Any]:
    """List existing promo codes."""
    async with AsyncSessionLocal() as db:
        q = select(PromoCode)
        if active_only:
            q = q.where(PromoCode.is_active == True).where(
                (PromoCode.valid_until == None) | (PromoCode.valid_until > datetime.utcnow())
            )
        result = await db.execute(q.order_by(PromoCode.created_at.desc()))
        codes = result.scalars().all()

    return {
        "codes": [
            {
                "code": c.code,
                "description": c.description,
                "discount": f"{c.discount_value}{'%' if c.discount_type == 'percent' else '$'} off",
                "min_order": c.min_order_value,
                "uses": c.current_uses,
                "max_uses": c.max_uses,
                "valid_until": c.valid_until.strftime("%Y-%m-%d") if c.valid_until else "no expiry",
                "campaign": c.campaign_name,
            }
            for c in codes
        ],
        "count": len(codes),
    }


def _random_code(prefix: str = "VENDO", length: int = 6) -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=length))
    return f"{prefix}{suffix}"


async def generate_promo_code_auto(
    campaign_name: str,
    discount_value: float = 15.0,
    discount_type: str = "percent",
    valid_days: int = 7,
    description: str = "",
) -> dict[str, Any]:
    """Auto-generate a unique promo code for a campaign."""
    for _ in range(10):
        code = _random_code()
        result = await create_promo_code(
            code=code,
            discount_value=discount_value,
            discount_type=discount_type,
            description=description or f"Vendo's Deals promo — {campaign_name}",
            valid_days=valid_days,
            campaign_name=campaign_name,
        )
        if result.get("success"):
            return result
    return {"success": False, "error": "Could not generate unique code after 10 attempts"}


# ── Campaign management ────────────────────────────────────────────────────────

async def save_marketing_campaign(
    name: str,
    campaign_type: str,
    platform: str,
    content: str,
    subject_line: str = "",
    target_audience: str = "",
    product_ids: list[str] | None = None,
    promo_code: str = "",
    status: str = "draft",
    notes: str = "",
) -> dict[str, Any]:
    """Save a generated marketing campaign to the database."""
    async with AsyncSessionLocal() as db:
        campaign = MarketingCampaign(
            name=name,
            campaign_type=campaign_type,
            platform=platform,
            content=content,
            subject_line=subject_line,
            target_audience=target_audience,
            product_ids=json.dumps(product_ids or []),
            promo_code=promo_code,
            status=status,
            notes=notes,
        )
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        return {"success": True, "campaign_id": campaign.id, "name": name, "platform": platform}


async def get_campaign_history(
    campaign_type: str | None = None,
    platform: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Get recent marketing campaigns."""
    async with AsyncSessionLocal() as db:
        q = select(MarketingCampaign).order_by(MarketingCampaign.created_at.desc()).limit(limit)
        if campaign_type:
            q = q.where(MarketingCampaign.campaign_type == campaign_type)
        if platform:
            q = q.where(MarketingCampaign.platform == platform)
        result = await db.execute(q)
        campaigns = result.scalars().all()

    return {
        "campaigns": [
            {
                "id": c.id,
                "name": c.name,
                "type": c.campaign_type,
                "platform": c.platform,
                "status": c.status,
                "subject": c.subject_line,
                "promo_code": c.promo_code,
                "created_at": c.created_at.isoformat(),
            }
            for c in campaigns
        ],
        "count": len(campaigns),
    }


async def update_campaign_metrics(
    campaign_id: str,
    impressions: int = 0,
    clicks: int = 0,
    conversions: int = 0,
    revenue_attributed: float = 0.0,
    status: str = "",
) -> dict[str, Any]:
    """Update performance metrics for a campaign."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MarketingCampaign).where(MarketingCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            return {"error": f"Campaign {campaign_id} not found"}

        if impressions:
            campaign.impressions += impressions
        if clicks:
            campaign.clicks += clicks
        if conversions:
            campaign.conversions += conversions
        if revenue_attributed:
            campaign.revenue_attributed += revenue_attributed
        if status:
            campaign.status = status
            if status == "published":
                campaign.published_at = datetime.utcnow()
        await db.commit()
        return {"success": True, "campaign_id": campaign_id}


async def get_marketing_summary(days: int = 30) -> dict[str, Any]:
    """Get an overview of marketing activity and attributed metrics."""
    since = datetime.utcnow() - timedelta(days=days)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MarketingCampaign).where(MarketingCampaign.created_at >= since)
        )
        campaigns = result.scalars().all()

        promo_result = await db.execute(
            select(PromoCode).where(PromoCode.created_at >= since)
        )
        promos = promo_result.scalars().all()

    by_platform: dict[str, int] = {}
    total_impressions = total_clicks = total_conversions = 0
    total_revenue = 0.0
    for c in campaigns:
        by_platform[c.platform] = by_platform.get(c.platform, 0) + 1
        total_impressions += c.impressions or 0
        total_clicks += c.clicks or 0
        total_conversions += c.conversions or 0
        total_revenue += c.revenue_attributed or 0.0

    return {
        "period_days": days,
        "total_campaigns": len(campaigns),
        "campaigns_by_platform": by_platform,
        "total_promo_codes_created": len(promos),
        "total_promo_code_uses": sum(p.current_uses or 0 for p in promos),
        "total_impressions": total_impressions,
        "total_clicks": total_clicks,
        "total_conversions": total_conversions,
        "revenue_attributed": round(total_revenue, 2),
        "ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions else 0,
    }


# ── Tool schemas ───────────────────────────────────────────────────────────────

class MarketingTools:
    SCHEMAS = [
        {
            "name": "get_featured_deals",
            "description": (
                "Get the best current deals from Vendo's catalog — highest savings and margins. "
                "Use this first to know what products to promote in campaigns."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10, "description": "Max deals to return"},
                },
            },
        },
        {
            "name": "create_promo_code",
            "description": "Create a discount promo code in the store database for customers to use at checkout.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The promo code (e.g. VENDO20)"},
                    "discount_value": {"type": "number", "description": "Discount amount (percent or fixed dollar)"},
                    "discount_type": {"type": "string", "enum": ["percent", "fixed"], "default": "percent"},
                    "description": {"type": "string"},
                    "min_order_value": {"type": "number", "default": 0.0},
                    "valid_days": {"type": "integer", "default": 7},
                    "max_uses": {"type": "integer", "description": "Max redemptions (omit for unlimited)"},
                    "campaign_name": {"type": "string"},
                },
                "required": ["code", "discount_value"],
            },
        },
        {
            "name": "generate_promo_code_auto",
            "description": "Auto-generate a unique random promo code for a campaign (e.g. VENDO7X2KP4).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "campaign_name": {"type": "string"},
                    "discount_value": {"type": "number", "default": 15.0},
                    "discount_type": {"type": "string", "enum": ["percent", "fixed"], "default": "percent"},
                    "valid_days": {"type": "integer", "default": 7},
                    "description": {"type": "string"},
                },
                "required": ["campaign_name"],
            },
        },
        {
            "name": "list_promo_codes",
            "description": "List existing promo codes and their usage stats.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "active_only": {"type": "boolean", "default": True},
                },
            },
        },
        {
            "name": "save_marketing_campaign",
            "description": (
                "Save a generated marketing campaign (social post, email, blog article, press release, etc.) "
                "to the database for tracking and later publishing."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Campaign name / identifier"},
                    "campaign_type": {
                        "type": "string",
                        "enum": ["social", "email", "seo", "press_release", "influencer", "affiliate", "ad_copy"],
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["twitter", "instagram", "facebook", "tiktok", "pinterest",
                                 "email", "blog", "reddit", "youtube", "linkedin", "press", "affiliate"],
                    },
                    "content": {"type": "string", "description": "The full generated content / copy"},
                    "subject_line": {"type": "string", "description": "Email subject line (for email campaigns)"},
                    "target_audience": {"type": "string"},
                    "product_ids": {"type": "array", "items": {"type": "string"}},
                    "promo_code": {"type": "string"},
                    "status": {"type": "string", "enum": ["draft", "scheduled", "published"], "default": "draft"},
                    "notes": {"type": "string"},
                },
                "required": ["name", "campaign_type", "platform", "content"],
            },
        },
        {
            "name": "get_campaign_history",
            "description": "View recent marketing campaigns by type or platform.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "campaign_type": {
                        "type": "string",
                        "enum": ["social", "email", "seo", "press_release", "influencer", "affiliate", "ad_copy"],
                    },
                    "platform": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
        {
            "name": "update_campaign_metrics",
            "description": "Update impressions, clicks, conversions, or status for a campaign.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "campaign_id": {"type": "string"},
                    "impressions": {"type": "integer", "default": 0},
                    "clicks": {"type": "integer", "default": 0},
                    "conversions": {"type": "integer", "default": 0},
                    "revenue_attributed": {"type": "number", "default": 0.0},
                    "status": {"type": "string", "enum": ["draft", "scheduled", "published", "archived"]},
                },
                "required": ["campaign_id"],
            },
        },
        {
            "name": "get_marketing_summary",
            "description": "Get an overview of all marketing activity, promo code usage, and attributed revenue.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 30},
                },
            },
        },
    ]

    MAP = {
        "get_featured_deals": get_featured_deals,
        "create_promo_code": create_promo_code,
        "generate_promo_code_auto": generate_promo_code_auto,
        "list_promo_codes": list_promo_codes,
        "save_marketing_campaign": save_marketing_campaign,
        "get_campaign_history": get_campaign_history,
        "update_campaign_metrics": update_campaign_metrics,
        "get_marketing_summary": get_marketing_summary,
    }
