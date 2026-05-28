"""
Lightweight server-side cart (session-less: client stores cart in localStorage).
This route validates cart contents and returns current prices.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import Product, ProductStatus, get_db

router = APIRouter()


class CartValidateRequest(BaseModel):
    items: list[dict]  # [{product_id, quantity}]


@router.post("/validate")
async def validate_cart(body: CartValidateRequest, db: AsyncSession = Depends(get_db)):
    """
    Validate cart items against current DB prices.
    Returns updated item list with current prices and a total.
    """
    validated = []
    total = 0.0

    for item in body.items:
        pid = item.get("product_id")
        qty = max(1, int(item.get("quantity", 1)))
        result = await db.execute(select(Product).where(Product.id == pid))
        product = result.scalar_one_or_none()

        if not product or product.status != ProductStatus.ACTIVE:
            validated.append({"product_id": pid, "error": "unavailable"})
            continue

        line_total = round(product.selling_price * qty, 2)
        total += line_total
        validated.append({
            "product_id": pid,
            "name": product.name,
            "quantity": qty,
            "unit_price": product.selling_price,
            "line_total": line_total,
            "image": __first_image(product.images),
        })

    return {"items": validated, "total": round(total, 2)}


def __first_image(images_json: str | None) -> str:
    import json
    try:
        imgs = json.loads(images_json or "[]")
        return imgs[0] if imgs else ""
    except Exception:
        return ""
