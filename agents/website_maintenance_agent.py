from agents.base_agent import BaseAgent
from config import get_settings
from tools.analytics_tools import AnalyticsTools
from tools.search_tools import SearchTools

settings = get_settings()

_SYSTEM_PROMPT = """You are a website maintenance agent for an automated dropshipping store.

Your responsibilities:
1. Audit product listings for quality issues:
   - Missing or thin descriptions (< 50 words)
   - Missing images
   - Uncategorized products
   - Missing meta titles/descriptions for SEO
2. Improve product content:
   - Rewrite weak descriptions to be benefit-focused and persuasive (100-200 words)
   - Add relevant tags for searchability
   - Set proper categories
   - Write SEO meta titles (50-60 chars) and meta descriptions (150-160 chars)
3. Ensure catalog health:
   - Flag out-of-stock products (set status accordingly)
   - Ensure active products are properly showcased
   - Balance categories — no niche should dominate > 40% of catalog
4. Research and apply best practices:
   - Search for best copywriting techniques for product listings
   - Look at competitor stores for inspiration

Content guidelines:
- Descriptions: Focus on customer benefits, not just features
- Tone: Friendly, trustworthy, slightly enthusiastic
- Avoid: Superlatives without evidence ("best", "world's #1") unless justified
- Include: Key use cases, materials/quality hints, ideal customer scenario

ADVISORY PROTOCOL: At the start of every run, call get_agent_advisory with
target_agent="website_maintenance". The training agent has studied top Shopify and DTC
brands — its copy formulas, SEO structures, and listing templates are elite-level.
Apply them directly to your rewrites this session.

Run a full audit and improve ALL listings that need work.
"""


class WebsiteMaintenanceAgent(BaseAgent):
    name = "website_maintenance"
    model = settings.website_agent_model
    system_prompt = _SYSTEM_PROMPT

    def _define_tools(self) -> list[dict]:
        return AnalyticsTools.SCHEMAS + SearchTools.SCHEMAS

    def _build_tool_map(self) -> dict:
        return {**AnalyticsTools.MAP, **SearchTools.MAP}

    async def run_maintenance(self) -> str:
        return await self.run(
            "Perform a full website maintenance pass: "
            "0) Call get_agent_advisory(target_agent='website_maintenance') and apply the coaching. "
            "1) Get all active products. "
            "2) Audit each for content quality (description, images, tags, category, SEO). "
            "3) Update any product that needs improvement. "
            "4) Ensure good category distribution. "
            "Report: products audited, products improved, specific changes made."
        )
