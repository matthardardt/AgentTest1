import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, text,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _gen_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────

class ProductStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    OUT_OF_STOCK = "out_of_stock"
    DISCONTINUED = "discontinued"


class OrderStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    PROCESSING = "processing"
    ORDERED_FROM_SUPPLIER = "ordered_from_supplier"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


# ── Models ────────────────────────────────────────────────────────────────────

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(String, primary_key=True, default=_gen_id)
    name = Column(String, nullable=False)
    platform = Column(String)             # aliexpress | manual
    api_key = Column(String)
    base_url = Column(String)
    rating = Column(Float, default=0.0)
    processing_days = Column(Integer, default=3)
    shipping_days_min = Column(Integer, default=7)
    shipping_days_max = Column(Integer, default=30)
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="supplier")


class Product(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True, default=_gen_id)
    name = Column(String, nullable=False)
    description = Column(Text)
    category = Column(String)
    sku = Column(String, unique=True)
    cost_price = Column(Float, default=0.0)
    selling_price = Column(Float, nullable=False)
    compare_at_price = Column(Float)
    images = Column(Text)                 # JSON array of URLs
    supplier_id = Column(String, ForeignKey("suppliers.id"))
    supplier_product_id = Column(String)
    supplier_url = Column(String)
    weight_kg = Column(Float)
    status = Column(Enum(ProductStatus), default=ProductStatus.ACTIVE)
    stock_quantity = Column(Integer, default=999)  # virtual stock for dropshipping
    tags = Column(Text)                   # JSON array
    meta_title = Column(String)
    meta_description = Column(Text)
    images_validated_at = Column(DateTime, nullable=True)
    images_validation_status = Column(String, nullable=True)  # valid | replaced | flagged
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    supplier = relationship("Supplier", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")
    pricing_history = relationship("PricingHistory", back_populates="product")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(String, primary_key=True, default=_gen_id)
    email = Column(String, nullable=False, unique=True)
    name = Column(String)
    phone = Column(String)
    address_line1 = Column(String)
    address_line2 = Column(String)
    city = Column(String)
    state = Column(String)
    country = Column(String)
    postal_code = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", back_populates="customer")


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=_gen_id)
    order_number = Column(String, unique=True)
    customer_id = Column(String, ForeignKey("customers.id"))
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    subtotal = Column(Float)
    shipping_cost = Column(Float, default=0.0)
    total = Column(Float)
    payment_method = Column(String)
    payment_id = Column(String)
    shipping_address = Column(Text)       # JSON
    notes = Column(Text)
    supplier_order_id = Column(String)
    tracking_number = Column(String)
    tracking_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(String, primary_key=True, default=_gen_id)
    order_id = Column(String, ForeignKey("orders.id"))
    product_id = Column(String, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")


class PricingHistory(Base):
    __tablename__ = "pricing_history"

    id = Column(String, primary_key=True, default=_gen_id)
    product_id = Column(String, ForeignKey("products.id"))
    old_price = Column(Float)
    new_price = Column(Float)
    reason = Column(String)
    changed_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="pricing_history")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(String, primary_key=True, default=_gen_id)
    agent_name = Column(String, nullable=False)
    task = Column(Text)
    result = Column(Text)
    status = Column(String)               # success | error
    tokens_used = Column(Integer)
    duration_seconds = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentDefinition(Base):
    """Dynamically-created agents stored in DB (manager agent spawns these)."""

    __tablename__ = "agent_definitions"

    id = Column(String, primary_key=True, default=_gen_id)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text)
    system_prompt = Column(Text)
    model = Column(String, default="claude-sonnet-4-6")
    tools_config = Column(Text)           # JSON list of tool names
    schedule_seconds = Column(Integer, default=3600)
    is_active = Column(Boolean, default=True)
    created_by = Column(String, default="manager")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_run_at = Column(DateTime)


class BusinessMetric(Base):
    __tablename__ = "business_metrics"

    id = Column(String, primary_key=True, default=_gen_id)
    metric_name = Column(String, nullable=False)
    metric_value = Column(Float)
    metric_data = Column(Text)            # JSON for complex values
    recorded_at = Column(DateTime, default=datetime.utcnow)


class TrainingInsight(Base):
    """Raw knowledge extracted by the training agent from top e-commerce sites."""

    __tablename__ = "training_insights"

    id = Column(String, primary_key=True, default=_gen_id)
    source_site = Column(String)          # e.g. "amazon", "etsy", "shopify-store"
    category = Column(String, nullable=False)  # copy|pricing|ux|trust|catalog|promotion|image|seo
    insight = Column(Text, nullable=False)
    confidence_score = Column(Float, default=0.8)   # 0.0–1.0
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentAdvisory(Base):
    """Tailored coaching generated by the training agent for each operational agent."""

    __tablename__ = "agent_advisories"

    id = Column(String, primary_key=True, default=_gen_id)
    target_agent = Column(String, nullable=False)   # product_hunting|pricing|website_maintenance|…
    advisory_type = Column(String, default="strategic")  # immediate|strategic
    priority = Column(String, default="medium")          # high|medium|low
    guidance = Column(Text, nullable=False)
    status = Column(String, default="active")            # active|superseded
    created_at = Column(DateTime, default=datetime.utcnow)


class TrainingSession(Base):
    """Audit log of every training agent run."""

    __tablename__ = "training_sessions"

    id = Column(String, primary_key=True, default=_gen_id)
    sites_researched = Column(Text)       # JSON list
    insights_extracted = Column(Integer, default=0)
    advisories_generated = Column(Integer, default=0)
    self_improvement_notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Additive column migrations for existing deployments
        for stmt in [
            "ALTER TABLE products ADD COLUMN images_validated_at DATETIME",
            "ALTER TABLE products ADD COLUMN images_validation_status VARCHAR",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # Column already exists


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
