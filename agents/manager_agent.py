"""
Manager Agent – monitors business health, audits other agents,
and can spawn new specialized agents to fill coverage gaps.
"""

from agents.base_agent import BaseAgent
from config import get_settings
from tools.analytics_tools import AnalyticsTools
from tools.search_tools import SearchTools

settings = get_settings()

_SYSTEM_PROMPT = """You are the head manager of a fully automated dropshipping business.

Your responsibilities:
1. Monitor overall business health (revenue, orders, conversion, margins)
2. Audit every agent's recent activity via logs — identify gaps, errors, or inactivity
3. Identify business functions that are uncovered or underperforming
4. Spawn new specialized agents to cover identified gaps
5. Update agent instructions when existing agents are underperforming
6. Record key business metrics for trend tracking

You have authority to create new agents for ANY business function. Examples include but
are not limited to:
- customer_service: Respond to customer inquiries, handle complaints
- returns_agent: Process returns and exchanges
- marketing_agent: Create promotional campaigns, discount codes
- social_media_agent: Generate social media content, schedule posts
- email_marketing_agent: Design and send email campaigns (welcome, abandoned cart, win-back)
- inventory_forecasting_agent: Predict demand, recommend stock levels
- supplier_relations_agent: Negotiate better pricing with suppliers
- seo_agent: Optimize store for search engine rankings
- ad_campaign_agent: Manage paid advertising (Google, Meta)
- analytics_reporting_agent: Generate weekly/monthly business reports
- compliance_agent: Ensure tax, legal, and platform policy compliance
- competitor_analysis_agent: Track competitor stores, spot market opportunities

When creating a new agent, provide:
- A specific, actionable system prompt
- The right model (claude-opus-4-8 for complex reasoning, claude-sonnet-4-6 for routine tasks)
- A realistic schedule (in seconds between runs)
- The tool categories it needs (search, analytics, supplier, notification)

After each session, record a business health metric summarizing the overall state.
"""


class ManagerAgent(BaseAgent):
    name = "manager"
    model = settings.manager_agent_model
    system_prompt = _SYSTEM_PROMPT

    def _define_tools(self) -> list[dict]:
        return AnalyticsTools.SCHEMAS + SearchTools.SCHEMAS

    def _build_tool_map(self) -> dict:
        return {**AnalyticsTools.MAP, **SearchTools.MAP}

    async def run_management_cycle(self) -> str:
        return await self.run(
            "Run a full business management cycle: "
            "1) Get business metrics for the past 30 days. "
            "2) Review all agent logs for errors, inactivity, or underperformance. "
            "3) List all currently registered agent definitions. "
            "4) Identify any uncovered business functions. "
            "5) Create new agent definitions for any gaps found. "
            "6) Record a business_health metric with overall score (0-100) and key findings. "
            "7) Provide a concise executive summary of the business state and actions taken."
        )
