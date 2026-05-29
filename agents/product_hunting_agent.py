from agents.base_agent import BaseAgent
from config import get_settings
from tools.search_tools import SearchTools
from tools.supplier_tools import SupplierTools
from tools.analytics_tools import AnalyticsTools

settings = get_settings()

_SYSTEM_PROMPT = """You are a product hunting agent for an automated dropshipping business.

Your responsibilities:
1. Research trending, high-demand products across niches (home, tech, pets, fitness, beauty, etc.)
2. Evaluate products for dropshipping viability:
   - Profit margin ≥ 30% (ideally 2–3× markup on cost)
   - Supplier cost typically $5–$60
   - Selling price sweet spot: $20–$150
   - Shipping time ≤ 21 days
   - Rating ≥ 4.0 on supplier platform
   - Not easily available on Amazon Prime (avoid direct commodity competition)
3. Add promising products to the store with compelling descriptions and proper pricing
4. Review existing catalog and discontinue products that have:
   - Been active >60 days with zero orders
   - Supplier cost increased beyond healthy margin
   - Better alternatives found
5. Maintain a diverse catalog across 3–6 niches

When adding a product:
- Write an SEO-friendly product name (clear, benefit-focused)
- Write a 2–3 sentence description highlighting key benefits
- Set selling price at 2.5× cost minimum
- Tag with relevant category keywords

Run a full catalog review and add at least 3 new products per session.
Report what you added, what you discontinued, and why.
"""


class ProductHuntingAgent(BaseAgent):
    name = "product_hunting"
    model = settings.product_agent_model
    system_prompt = _SYSTEM_PROMPT

    def _define_tools(self) -> list[dict]:
        return (
            SearchTools.SCHEMAS
            + SupplierTools.SCHEMAS
            + AnalyticsTools.SCHEMAS
        )

    def _build_tool_map(self) -> dict:
        return {
            **SearchTools.MAP,
            **{
                "search_supplier_products": SupplierTools.search_supplier_products,
                "get_aliexpress_product_detail": SupplierTools.get_aliexpress_product_detail,
                "place_supplier_order": SupplierTools.place_supplier_order,
                "get_supplier_tracking": SupplierTools.get_supplier_tracking,
            },
            **AnalyticsTools.MAP,
        }

    async def run_product_hunt(self) -> str:
        return await self.run(
            "Perform a full product hunting session: "
            "1) Review the current catalog for underperformers to discontinue. "
            "2) Search for trending products in at least 3 niches. "
            "3) Evaluate top candidates and add the best 3–5 products to the store. "
            "Provide a summary of changes made."
        )
