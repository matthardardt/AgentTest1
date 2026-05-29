"""
Seed initial data: default supplier + a few example products.
Run once: python -m scripts.seed
"""

import asyncio
import json
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import AsyncSessionLocal, Product, ProductStatus, Supplier, init_db


SAMPLE_PRODUCTS = [
    {
        "name": "Ergonomic Laptop Stand – Adjustable Aluminum",
        "description": (
            "Transform your workspace with this sleek aluminum laptop stand. "
            "Six adjustable height levels reduce neck strain, while the open design "
            "keeps your laptop cool. Folds flat in seconds for easy storage. "
            "Compatible with all 11–17\" laptops."
        ),
        "category": "Home Office",
        "cost_price": 12.50,
        "selling_price": 34.99,
        "compare_at_price": 49.99,
        "tags": ["laptop stand", "home office", "ergonomic", "aluminum"],
        "images": ["https://images.unsplash.com/photo-1593642632559-0c6d3fc62b89?w=600"],
    },
    {
        "name": "LED Ring Light – 10\" with Phone Holder",
        "description": (
            "Perfect for content creators, video calls, and beauty routines. "
            "Three color modes (warm, daylight, cool) with 10 brightness levels. "
            "Includes adjustable phone holder and 67\" tripod stand. "
            "USB powered — works with any laptop or power bank."
        ),
        "category": "Photography",
        "cost_price": 9.99,
        "selling_price": 29.99,
        "compare_at_price": 39.99,
        "tags": ["ring light", "led", "content creator", "photography", "video call"],
        "images": ["https://images.unsplash.com/photo-1617886903355-9354bb57751f?w=600"],
    },
    {
        "name": "Minimalist Leather Wallet – RFID Blocking",
        "description": (
            "Slim, smart, and stylish — this premium PU leather wallet holds up to "
            "8 cards and has a convenient cash slot. Built-in RFID blocking technology "
            "protects your cards from electronic theft. Available in classic black."
        ),
        "category": "Accessories",
        "cost_price": 5.50,
        "selling_price": 19.99,
        "tags": ["wallet", "rfid", "minimalist", "leather", "gift"],
        "images": ["https://images.unsplash.com/photo-1627123424574-724758594e93?w=600"],
    },
    {
        "name": "Portable Blender – USB Rechargeable",
        "description": (
            "Make fresh smoothies, shakes, and juices anywhere. "
            "Rechargeable via USB-C, this 400ml blender delivers 6-blade performance "
            "in a compact bottle you can take to the gym, office, or outdoors. "
            "BPA-free, easy to clean."
        ),
        "category": "Kitchen",
        "cost_price": 11.00,
        "selling_price": 32.99,
        "compare_at_price": 44.99,
        "tags": ["blender", "portable", "usb", "smoothie", "kitchen"],
        "images": ["https://images.unsplash.com/photo-1553530979-fbb9e4aee36f?w=600"],
    },
    {
        "name": "Silicone Cable Organizer Set (10 pcs)",
        "description": (
            "Say goodbye to cable chaos. This set of 10 reusable silicone ties keeps "
            "USB cables, charging cords, and earphones neatly organized on your desk "
            "or in your bag. Heat-resistant, waterproof, and built to last."
        ),
        "category": "Tech Accessories",
        "cost_price": 3.00,
        "selling_price": 12.99,
        "tags": ["cable organizer", "desk", "tech", "silicone", "organization"],
        "images": ["https://images.unsplash.com/photo-1585771724684-38269d6639fd?w=600"],
    },
]


async def seed():
    await init_db()
    async with AsyncSessionLocal() as db:
        # Default supplier
        supplier = Supplier(
            name="AliExpress",
            platform="aliexpress",
            processing_days=3,
            shipping_days_min=7,
            shipping_days_max=21,
            is_active=True,
        )
        db.add(supplier)
        await db.flush()

        for data in SAMPLE_PRODUCTS:
            p = Product(
                name=data["name"],
                description=data["description"],
                category=data["category"],
                sku=f"SKU-{uuid.uuid4().hex[:8].upper()}",
                cost_price=data["cost_price"],
                selling_price=data["selling_price"],
                compare_at_price=data.get("compare_at_price"),
                images=json.dumps(data.get("images", [])),
                tags=json.dumps(data.get("tags", [])),
                supplier_id=supplier.id,
                status=ProductStatus.ACTIVE,
            )
            db.add(p)

        await db.commit()
        print(f"✓ Seeded {len(SAMPLE_PRODUCTS)} products and 1 supplier.")


if __name__ == "__main__":
    asyncio.run(seed())
