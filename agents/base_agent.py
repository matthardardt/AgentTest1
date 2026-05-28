import json
import time
from typing import Any, Callable

import anthropic

from config import get_settings
from database import AgentLog, AsyncSessionLocal

settings = get_settings()


class BaseAgent:
    """
    Wraps the Anthropic SDK agentic loop: send task → handle tool_use blocks
    until end_turn, log results.
    """

    name: str = "base"
    model: str = "claude-sonnet-4-6"
    system_prompt: str = "You are a helpful agent."
    max_iterations: int = 20

    def __init__(self) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.tools: list[dict] = self._define_tools()
        self.tool_map: dict[str, Callable] = self._build_tool_map()

    # ── Subclasses implement these ─────────────────────────────────────────────

    def _define_tools(self) -> list[dict]:
        """Return list of Anthropic tool schema dicts."""
        return []

    def _build_tool_map(self) -> dict[str, Callable]:
        """Return mapping of tool name → async callable."""
        return {}

    # ── Public interface ───────────────────────────────────────────────────────

    async def run(self, task: str) -> str:
        start = time.monotonic()
        messages: list[dict] = [{"role": "user", "content": task}]
        result = ""
        status = "success"
        tokens = 0

        try:
            for _ in range(self.max_iterations):
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=self.system_prompt,
                    tools=self.tools if self.tools else anthropic.NOT_GIVEN,
                    messages=messages,
                )
                tokens += response.usage.input_tokens + response.usage.output_tokens

                if response.stop_reason == "end_turn":
                    result = self._extract_text(response.content)
                    break

                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": response.content})
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_result = await self._call_tool(block.name, block.input)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": (
                                    json.dumps(tool_result)
                                    if not isinstance(tool_result, str)
                                    else tool_result
                                ),
                            })
                    messages.append({"role": "user", "content": tool_results})
            else:
                result = "Max iterations reached."
        except Exception as exc:
            result = f"Agent error: {exc}"
            status = "error"

        duration = time.monotonic() - start
        await self._log(task, result, status, tokens, duration)
        return result

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _call_tool(self, name: str, args: dict) -> Any:
        fn = self.tool_map.get(name)
        if fn is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            return await fn(**args)
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _extract_text(content: list) -> str:
        return " ".join(
            block.text for block in content if hasattr(block, "text")
        )

    async def _log(
        self,
        task: str,
        result: str,
        status: str,
        tokens: int,
        duration: float,
    ) -> None:
        async with AsyncSessionLocal() as session:
            session.add(AgentLog(
                agent_name=self.name,
                task=task[:500],
                result=result[:2000],
                status=status,
                tokens_used=tokens,
                duration_seconds=round(duration, 2),
            ))
            await session.commit()
