"""
Image validation tools — check whether product images actually show the product.

Vision analysis is done via a direct Anthropic API call (Claude Haiku) inside
each tool, keeping the main agent loop text-only and cheap.
"""

import base64
import json
from datetime import datetime, timedelta
from typing import Any

import anthropic
import httpx
from sqlalchemy import select

from config import get_settings
from database import AsyncSessionLocal, Product, ProductStatus

settings = get_settings()

_VISION_MODEL = "claude-haiku-4-5-20251001"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VendosDeals-ImageBot/1.0)"}


async def get_unvalidated_products(limit: int = 20) -> dict[str, Any]:
    """
    Return products that have images but haven't been validated yet,
    or whose validation is older than 7 days.
    """
    cutoff = datetime.utcnow() - timedelta(days=7)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Product).where(
                Product.status == ProductStatus.ACTIVE,
                Product.images.isnot(None),
                (Product.images_validated_at.is_(None)) |
                (Product.images_validated_at < cutoff),
            ).limit(limit)
        )
        products = result.scalars().all()

    out = []
    for p in products:
        try:
            images = json.loads(p.images or "[]")
        except (json.JSONDecodeError, TypeError):
            images = []
        if images:
            out.append({
                "id": p.id,
                "name": p.name,
                "description": p.description or "",
                "category": p.category or "",
                "images": images,
                "validation_status": p.images_validation_status,
            })
    return {"products": out, "count": len(out)}


async def analyze_product_image(
    product_id: str,
    image_url: str,
    product_name: str,
    product_description: str,
) -> dict[str, Any]:
    """
    Download an image and use Claude vision to decide whether it accurately
    represents the product. Returns verdict (match/mismatch/unclear) and reason.
    """
    try:
        async with httpx.AsyncClient(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get(image_url)
            if resp.status_code != 200:
                return {
                    "verdict": "unclear",
                    "reason": f"Could not fetch image (HTTP {resp.status_code})",
                    "image_url": image_url,
                }
            image_data = base64.standard_b64encode(resp.content).decode("utf-8")
            content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            if content_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                content_type = "image/jpeg"
    except Exception as exc:
        return {"verdict": "unclear", "reason": f"Image fetch error: {exc}", "image_url": image_url}

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await client.messages.create(
            model=_VISION_MODEL,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": content_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Does this image accurately show the product being sold?\n\n"
                            f"Product name: {product_name}\n"
                            f"Description: {product_description[:300]}\n\n"
                            "Reply with exactly one of:\n"
                            "MATCH – image clearly shows this product\n"
                            "MISMATCH – image shows something different\n"
                            "UNCLEAR – impossible to tell\n\n"
                            "Then one sentence explaining why."
                        ),
                    },
                ],
            }],
        )
        response_text = msg.content[0].text.strip()
    except Exception as exc:
        return {"verdict": "unclear", "reason": f"Vision API error: {exc}", "image_url": image_url}

    upper = response_text.upper()
    if upper.startswith("MATCH"):
        verdict = "match"
    elif upper.startswith("MISMATCH"):
        verdict = "mismatch"
    else:
        verdict = "unclear"

    return {
        "verdict": verdict,
        "reason": response_text,
        "image_url": image_url,
        "product_id": product_id,
    }


async def search_replacement_images(product_name: str, category: str = "") -> dict[str, Any]:
    """
    Search for replacement product images.
    Uses SerpAPI image search if configured; returns empty list otherwise.
    """
    if not settings.serp_api_key:
        return {
            "images": [],
            "note": "No SERP API key configured — cannot auto-replace images.",
        }

    query = f"{product_name} {category} product photo white background".strip()
    params = {
        "q": query,
        "api_key": settings.serp_api_key,
        "engine": "google",
        "tbm": "isch",
        "num": 5,
        "safe": "active",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://serpapi.com/search", params=params)
            r.raise_for_status()
            data = r.json()
        images = [
            item["original"]
            for item in data.get("images_results", [])[:5]
            if item.get("original")
        ]
        return {"images": images, "query": query}
    except Exception as exc:
        return {"images": [], "error": str(exc)}


async def update_product_images(product_id: str, images: list[str]) -> dict[str, Any]:
    """Replace the images list for a product."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Product).where(Product.id == product_id))
        p = result.scalar_one_or_none()
        if not p:
            return {"error": f"Product {product_id} not found"}
        p.images = json.dumps(images)
        p.updated_at = datetime.utcnow()
        await db.commit()
    return {"success": True, "product_id": product_id, "image_count": len(images)}


async def mark_product_images_validated(
    product_id: str,
    status: str,
    notes: str = "",
) -> dict[str, Any]:
    """
    Record image validation result on the product.
    status: "valid" | "replaced" | "flagged"
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Product).where(Product.id == product_id))
        p = result.scalar_one_or_none()
        if not p:
            return {"error": f"Product {product_id} not found"}
        p.images_validated_at = datetime.utcnow()
        p.images_validation_status = status
        if status == "flagged" and notes:
            # Append a tag so other agents can see the flag
            try:
                tags = json.loads(p.tags or "[]")
            except (json.JSONDecodeError, TypeError):
                tags = []
            flag_tag = "needs-image-update"
            if flag_tag not in tags:
                tags.append(flag_tag)
            p.tags = json.dumps(tags)
        await db.commit()
    return {"success": True, "product_id": product_id, "status": status}


# ── Tool definitions ───────────────────────────────────────────────────────────

class ImageValidationTools:
    SCHEMAS = [
        {
            "name": "get_unvalidated_products",
            "description": "Return active products with images that haven't been validated yet (or validated more than 7 days ago).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of products to return (default 20).",
                        "default": 20,
                    }
                },
                "required": [],
            },
        },
        {
            "name": "analyze_product_image",
            "description": "Download an image URL and use Claude vision to verify whether it accurately shows the stated product. Returns verdict: match, mismatch, or unclear.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID."},
                    "image_url": {"type": "string", "description": "URL of the image to analyze."},
                    "product_name": {"type": "string", "description": "Name of the product."},
                    "product_description": {"type": "string", "description": "Product description for context."},
                },
                "required": ["product_id", "image_url", "product_name", "product_description"],
            },
        },
        {
            "name": "search_replacement_images",
            "description": "Search for replacement images for a product whose current images are wrong. Requires SERP API key.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string", "description": "Product name to search for."},
                    "category": {"type": "string", "description": "Product category for better results."},
                },
                "required": ["product_name"],
            },
        },
        {
            "name": "update_product_images",
            "description": "Replace the image list for a product with a new set of URLs.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID."},
                    "images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New list of image URLs.",
                    },
                },
                "required": ["product_id", "images"],
            },
        },
        {
            "name": "mark_product_images_validated",
            "description": "Record the image validation result for a product. Use status='valid' if images match, 'replaced' if you updated the images, 'flagged' if images are wrong but no replacement was found.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product ID."},
                    "status": {
                        "type": "string",
                        "enum": ["valid", "replaced", "flagged"],
                        "description": "Validation outcome.",
                    },
                    "notes": {"type": "string", "description": "Optional notes about the validation."},
                },
                "required": ["product_id", "status"],
            },
        },
    ]

    MAP = {
        "get_unvalidated_products": get_unvalidated_products,
        "analyze_product_image": analyze_product_image,
        "search_replacement_images": search_replacement_images,
        "update_product_images": update_product_images,
        "mark_product_images_validated": mark_product_images_validated,
    }
