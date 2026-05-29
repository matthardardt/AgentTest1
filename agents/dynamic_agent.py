"""
DynamicAgent — executes agent definitions stored in the database by the manager agent.
The manager creates AgentDefinition rows; the orchestrator picks them up and runs them.
"""

from agents.base_agent import BaseAgent
from tools.analytics_tools import AnalyticsTools
from tools.search_tools import SearchTools
from tools.supplier_tools import SupplierTools
from tools.notification_tools import NotificationTools
from tools.marketing_tools import MarketingTools

# All available tool schemas + callables, keyed by tool name
_ALL_SCHEMAS: dict[str, dict] = {
    s["name"]: s for s in (
        AnalyticsTools.SCHEMAS
        + SearchTools.SCHEMAS
        + SupplierTools.SCHEMAS
        + NotificationTools.SCHEMAS
        + MarketingTools.SCHEMAS
    )
}

_ALL_MAP: dict = {
    **AnalyticsTools.MAP,
    **SearchTools.MAP,
    **{
        "search_supplier_products": SupplierTools.search_supplier_products,
        "place_supplier_order": SupplierTools.place_supplier_order,
        "get_supplier_tracking": SupplierTools.get_supplier_tracking,
    },
    **NotificationTools.MAP,
    **MarketingTools.MAP,
}


class DynamicAgent(BaseAgent):
    """
    Instantiated at runtime from an AgentDefinition row.
    tools_names: list of tool names the agent is allowed to use.
    """

    def __init__(self, name: str, model: str, system_prompt: str, tool_names: list[str]) -> None:
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self._tool_names = tool_names
        super().__init__()

    def _define_tools(self) -> list[dict]:
        return [_ALL_SCHEMAS[n] for n in self._tool_names if n in _ALL_SCHEMAS]

    def _build_tool_map(self) -> dict:
        return {n: _ALL_MAP[n] for n in self._tool_names if n in _ALL_MAP}
