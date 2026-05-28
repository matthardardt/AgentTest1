from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import Product, ProductStatus, get_db

router = APIRouter()


class ProductOut(BaseModel):
    id: str
    name: str
    description: str | None
    category: str | None
    sku: str | None
    selling_price: float
    compare_at_price: float | None
    images: str | None
    status: str | None
    tags: str | None
    stock_quantity: int | None

    class Config:
        from_attributes = True


@router.get("/")
async def list_products(
    category: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    q = select(Product).where(Product.status == ProductStatus.ACTIVE).limit(limit)
    if category:
        q = q.where(Product.category == category)
    result = await db.execute(q)
    return {"products": [ProductOut.model_validate(p) for p in result.scalars().all()]}


@router.get("/{product_id}")
async def get_product(product_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return ProductOut.model_validate(p)
