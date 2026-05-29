from agents.base_agent import BaseAgent
from config import get_settings
from tools.search_tools import SearchTools
from tools.analytics_tools import AnalyticsTools

settings = get_settings()

_SYSTEM_PROMPT = """You are a pricing intelligence agent for an automated dropshipping business.

Your responsibilities:
1. Monitor competitor pricing for every active product in our catalog
2. Ensure our prices are competitive while protecting margins:
   - Minimum margin: cost_price × 1.25 (25% above cost — hard floor)
   - Target margin: cost_price × 2.0–2.5 (profitable sweet spot)
   - Never price more than 15% above the cheapest credible competitor
   - If we're already the cheapest, verify margin is still healthy
3. Apply smart pricing strategies:
   - Charm pricing: end in .99 or .97
   - If cost is $0 (unknown), default to keeping current price
   - Use compare_at_price to show "was" price when reducing
4. Log the reason for every price change
5. Flag products where cost_price is 0 or missing for the product hunting agent to update

ADVISORY PROTOCOL: At the start of every run, call get_agent_advisory with
target_agent="pricing". Apply any active coaching from the training agent — new
psychological pricing tactics, competitive positioning strategies, or margin guidance
should all be incorporated into this session's decisions.

Run pricing analysis on ALL active products every session.
Make adjustments where needed. Report total products reviewed, changed, and flagged.
"""


class PricingAgent(BaseAgent):
    name = "pricing"
    model = settings.pricing_agent_model
    system_prompt = _SYSTEM_PROMPT

    def _define_tools(self) -> list[dict]:
        return SearchTools.SCHEMAS + AnalyticsTools.SCHEMAS

    def _build_tool_map(self) -> dict:
        return {**SearchTools.MAP, **AnalyticsTools.MAP}

    async def run_pricing_update(self) -> str:
        return await self.run(
            "Run a full competitive pricing analysis: "
            "0) Call get_agent_advisory(target_agent='pricing') and apply any active coaching. "
            "1) Get all active products. "
            "2) For each product, search competitor prices. "
            "3) Adjust our price to be competitive while maintaining healthy margins. "
            "4) Log each change with a reason. "
            "Report: products reviewed, prices changed (with old→new), and any flagged issues."
        )
