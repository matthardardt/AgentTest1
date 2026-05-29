import json

from agents.base_agent import BaseAgent
from config import get_settings
from tools.analytics_tools import AnalyticsTools
from tools.notification_tools import NotificationTools
from tools.supplier_tools import SupplierTools
from database import AsyncSessionLocal, Customer, Order
from sqlalchemy import select

settings = get_settings()

_SYSTEM_PROMPT = """You are an order fulfillment agent for an automated dropshipping business.

Your responsibilities:
1. Monitor for newly PAID orders that need processing
2. For each paid order:
   a. Fetch the full order details including items and shipping address
   b. For each item, call get_product to get product details including supplier_platform
   c. Place a dropship order with the correct supplier platform (see routing rules below)
   d. Update order status to "ordered_from_supplier"
   e. Send order confirmation email to the customer
3. Monitor orders in "ordered_from_supplier" status:
   a. Check tracking information from the supplier
   b. When tracking is available, update the order with tracking info
   c. Set status to "shipped" and notify the customer with tracking details
4. Check "shipped" orders and mark as "delivered" when appropriate
5. Handle cancellation requests:
   - If order is still PAID (not yet sent to supplier), cancel and refund
   - If already shipped, advise customer to return
6. Handle refund requests for delivered orders with valid complaints

## Supplier Routing Rules
Always call get_product first to check the product's supplier_platform field, then pass the
matching platform to place_supplier_order:
- "aliexpress"  → platform="dsers"    (DSers routes to AliExpress; include variant_id if known)
- "zendrop"     → platform="zendrop"
- "spocket"     → platform="spocket"
- "autods"      → platform="autods"
- "printful"    → platform="printful"

Use the same platform when calling get_supplier_tracking for that order.

Process ALL pending work in each session. Be thorough.
Always use the exact shipping address from the order — never modify it.
"""


class OrderingAgent(BaseAgent):
    name = "ordering"
    model = settings.ordering_agent_model
    system_prompt = _SYSTEM_PROMPT

    def _define_tools(self) -> list[dict]:
        return (
            AnalyticsTools.SCHEMAS
            + SupplierTools.SCHEMAS
            + NotificationTools.SCHEMAS
            + [
                {
                    "name": "get_customer_info",
                    "description": "Get customer contact info (email, name) for a customer ID.",
                    "input_schema": {
                        "type": "object",
                        "properties": {"customer_id": {"type": "string"}},
                        "required": ["customer_id"],
                    },
                }
            ]
        )

    def _build_tool_map(self) -> dict:
        return {
            **AnalyticsTools.MAP,
            **{
                "search_supplier_products": SupplierTools.search_supplier_products,
                "get_aliexpress_product_detail": SupplierTools.get_aliexpress_product_detail,
                "place_supplier_order": SupplierTools.place_supplier_order,
                "get_supplier_tracking": SupplierTools.get_supplier_tracking,
            },
            **NotificationTools.MAP,
            "get_customer_info": self._get_customer_info,
        }

    @staticmethod
    async def _get_customer_info(customer_id: str) -> dict:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Customer).where(Customer.id == customer_id))
            c = result.scalar_one_or_none()
            if not c:
                return {"error": f"Customer {customer_id} not found"}
            return {
                "id": c.id,
                "email": c.email,
                "name": c.name,
                "phone": c.phone,
            }

    async def run_fulfillment_cycle(self) -> str:
        return await self.run(
            "Run a complete fulfillment cycle: "
            "1) Get all PAID orders that need to be sent to suppliers. "
            "2) For each paid order, get order details and place supplier orders. "
            "3) Update statuses and send customer confirmations. "
            "4) Check orders_from_supplier for tracking updates. "
            "5) Handle any cancellation or refund requests. "
            "Report all actions taken."
        )
