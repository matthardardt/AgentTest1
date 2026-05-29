"""
FastAPI storefront — serves the customer-facing shop and an internal admin API
consumed by agents.
"""

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import (
    AsyncSessionLocal, Customer, Order, OrderItem,
    OrderStatus, Product, ProductStatus, init_db, get_db,
)
from store.routes import products, orders, cart, admin

settings = get_settings()

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.store_name, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Custom Jinja2 filters
templates.env.filters["from_json"] = lambda v: json.loads(v) if v else []
templates.env.filters["tojson"] = json.dumps

# Attach routers
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(orders.router, prefix="/api/orders", tags=["orders"])
app.include_router(cart.router, prefix="/api/cart", tags=["cart"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])


# ── Customer-facing pages ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product)
        .where(Product.status == ProductStatus.ACTIVE)
        .order_by(Product.created_at.desc())
        .limit(20)
    )
    products_list = result.scalars().all()
    return templates.TemplateResponse(request, "index.html", {
        "products": products_list,
        "store_name": settings.store_name,
    })


@app.get("/product/{product_id}", response_class=HTMLResponse)
async def product_page(product_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product or product.status == ProductStatus.DISCONTINUED:
        raise HTTPException(status_code=404, detail="Product not found")
    images = json.loads(product.images or "[]")
    tags = json.loads(product.tags or "[]")
    return templates.TemplateResponse(request, "product.html", {
        "product": product,
        "images": images,
        "tags": tags,
        "store_name": settings.store_name,
    })


@app.get("/checkout", response_class=HTMLResponse)
async def checkout_page(request: Request):
    return templates.TemplateResponse(request, "checkout.html", {
        "store_name": settings.store_name,
        "stripe_publishable_key": settings.stripe_publishable_key or "",
    })


@app.get("/order/{order_id}", response_class=HTMLResponse)
async def order_page(order_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    items = items_result.scalars().all()
    return templates.TemplateResponse(request, "order_confirmation.html", {
        "order": order,
        "items": items,
        "store_name": settings.store_name,
    })


@app.get("/pages/{slug}", response_class=HTMLResponse)
async def legal_page(slug: str, request: Request):
    """Serve a generated legal/policy page (privacy, terms, refund, shipping)."""
    safe_slug = "".join(c for c in slug.lower() if c.isalnum() or c in ("-", "_"))
    template_name = f"legal_{safe_slug}.html"
    if not (BASE_DIR / "templates" / template_name).exists():
        raise HTTPException(status_code=404, detail="Page not found")
    return templates.TemplateResponse(request, template_name, {
        "store_name": settings.store_name,
    })


@app.get("/health")
async def health():
    return {"status": "ok", "store": settings.store_name}
