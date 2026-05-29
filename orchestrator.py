"""
Orchestrator – runs all agents on their configured schedules in async tasks.

Usage:
    python orchestrator.py          # runs agents only (no store)
    python orchestrator.py --store  # also starts the FastAPI store server
"""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime

from rich.console import Console
from rich.table import Table

from config import get_settings
from database import init_db, AsyncSessionLocal, AgentDefinition
from sqlalchemy import select
import json

from agents.product_hunting_agent import ProductHuntingAgent
from agents.pricing_agent import PricingAgent
from agents.ordering_agent import OrderingAgent
from agents.website_maintenance_agent import WebsiteMaintenanceAgent
from agents.manager_agent import ManagerAgent
from agents.design_agent import DesignAgent
from agents.business_analysis_agent import BusinessAnalysisAgent
from agents.dynamic_agent import DynamicAgent

settings = get_settings()
console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("orchestrator")

_shutdown = asyncio.Event()


def _handle_signal(*_):
    console.print("\n[yellow]Shutting down gracefully…[/yellow]")
    _shutdown.set()


# ── Core scheduler ─────────────────────────────────────────────────────────────

async def run_agent_loop(agent, interval_seconds: int, name: str) -> None:
    """Run an agent repeatedly on a fixed interval until shutdown."""
    while not _shutdown.is_set():
        console.print(f"[cyan][{datetime.utcnow().strftime('%H:%M:%S')}] Running {name}…[/cyan]")
        try:
            result = await asyncio.wait_for(
                agent(),
                timeout=600,  # 10-minute hard timeout per run
            )
            console.print(f"[green]✓ {name} complete.[/green]")
            log.info("%s result: %s", name, result[:200])
        except asyncio.TimeoutError:
            log.warning("%s timed out after 10 min", name)
        except Exception as exc:
            log.error("%s error: %s", name, exc, exc_info=True)

        # Wait for next interval or shutdown signal
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass  # normal – interval elapsed


async def run_store(host: str = "0.0.0.0", port: int | None = None) -> None:
    import os
    import uvicorn
    # Honour the platform-provided $PORT (Render/Railway/Heroku); default to 8000.
    port = port or int(os.environ.get("PORT", "8000"))
    config = uvicorn.Config("store.main:app", host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    # The orchestrator already owns SIGINT/SIGTERM; don't let uvicorn install its
    # own handlers on top (it's running inside our event loop, not standalone).
    server.install_signal_handlers = lambda: None
    await server.serve()


async def main(with_store: bool = False, run_golive: bool = False) -> None:
    console.print(f"[bold cyan]🚀 {settings.store_name} — Agent Orchestrator[/bold cyan]")
    await init_db()

    # Optional pre-flight: run the Go-Live agent once before starting the loops
    if run_golive:
        from agents.golive_agent import GoLiveAgent
        console.rule("[bold]Go-Live pre-flight")
        report = await GoLiveAgent().run_golive()
        console.print(report)
        console.rule()

    # Instantiate agents
    product_agent = ProductHuntingAgent()
    pricing_agent = PricingAgent()
    ordering_agent = OrderingAgent()
    website_agent = WebsiteMaintenanceAgent()
    design_agent  = DesignAgent()
    manager_agent = ManagerAgent()
    analysis_agent = BusinessAnalysisAgent()

    # Print schedule table
    table = Table(title="Agent Schedule", show_header=True)
    table.add_column("Agent", style="cyan")
    table.add_column("Interval")
    table.add_column("Model")

    schedules = [
        (product_agent,  settings.product_agent_interval,  "Product Hunting"),
        (pricing_agent,  settings.pricing_agent_interval,  "Pricing"),
        (ordering_agent, settings.ordering_agent_interval, "Ordering / Fulfillment"),
        (website_agent,  settings.website_agent_interval,  "Website Maintenance"),
        (design_agent,   settings.website_agent_interval,  "Graphic Design"),
        (manager_agent,  settings.manager_agent_interval,  "Manager"),
        (analysis_agent, settings.analysis_agent_interval, "Business Analysis"),
    ]
    for agent, interval, label in schedules:
        table.add_row(label, f"{interval}s", agent.model)
    console.print(table)

    tasks = [
        asyncio.create_task(run_agent_loop(
            product_agent.run_product_hunt,
            settings.product_agent_interval,
            "Product Hunting",
        )),
        asyncio.create_task(run_agent_loop(
            pricing_agent.run_pricing_update,
            settings.pricing_agent_interval,
            "Pricing",
        )),
        asyncio.create_task(run_agent_loop(
            ordering_agent.run_fulfillment_cycle,
            settings.ordering_agent_interval,
            "Ordering",
        )),
        asyncio.create_task(run_agent_loop(
            website_agent.run_maintenance,
            settings.website_agent_interval,
            "Website Maintenance",
        )),
        asyncio.create_task(run_agent_loop(
            design_agent.run_design_cycle,
            settings.website_agent_interval,
            "Graphic Design",
        )),
        asyncio.create_task(run_agent_loop(
            manager_agent.run_management_cycle,
            settings.manager_agent_interval,
            "Manager",
        )),
        asyncio.create_task(run_agent_loop(
            analysis_agent.run_analysis_cycle,
            settings.analysis_agent_interval,
            "Business Analysis",
        )),
    ]

    # Watcher: picks up new dynamic agent definitions created by the manager
    tasks.append(asyncio.create_task(_dynamic_agent_watcher()))

    if with_store:
        import os
        _port = os.environ.get("PORT", "8000")
        console.print(f"[bold]Starting store at http://0.0.0.0:{_port}[/bold]")
        tasks.append(asyncio.create_task(run_store()))

    await asyncio.gather(*tasks, return_exceptions=True)


async def _latest_plan_verdict() -> dict | None:
    """Read the most recent business_plan_assessment metric."""
    from database import BusinessMetric
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(BusinessMetric)
            .where(BusinessMetric.metric_name == "business_plan_assessment")
            .order_by(BusinessMetric.recorded_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return json.loads(row.metric_data) if row and row.metric_data else None


async def run_consensus_loop(max_rounds: int = 4) -> None:
    """Iterate the Business Analyst with the operational agents until the analyst
    signs the plan off as 'sound' (or max_rounds is reached).

    Each round: the analyst evaluates the economics and posts addressed
    recommendations; the operational agents then act on the recommendations
    aimed at them; the analyst re-evaluates next round. Requires ANTHROPIC_API_KEY.
    """
    await init_db()
    analysis = BusinessAnalysisAgent()
    pricing = PricingAgent()
    product = ProductHuntingAgent()
    website = WebsiteMaintenanceAgent()
    design = DesignAgent()

    for rnd in range(1, max_rounds + 1):
        console.rule(f"[bold]Consensus round {rnd}/{max_rounds}")

        console.print("[cyan]Business Analyst evaluating…[/cyan]")
        summary = await analysis.run_analysis_cycle()
        console.print(summary[:600])

        verdict = await _latest_plan_verdict()
        if verdict:
            console.print(f"[bold]Verdict:[/bold] {verdict.get('verdict')} "
                          f"(score {verdict.get('score')})")
            if verdict.get("verdict") == "sound" and verdict.get("score", 0) >= 75:
                console.print("[green bold]✓ Analyst signed off — plan is sound.[/green bold]")
                return

        console.print("[cyan]Operational agents acting on recommendations…[/cyan]")
        await asyncio.gather(
            pricing.run_pricing_update(),
            product.run_product_hunt(),
            website.run_maintenance(),
            design.run_design_cycle(),
            return_exceptions=True,
        )

    console.print("[yellow]Max rounds reached without full sign-off. "
                  "Review the latest recommendations and verdict.[/yellow]")


_running_dynamic: set[str] = set()


async def _dynamic_agent_watcher() -> None:
    """Polls DB every 60s; spins up tasks for new active dynamic agents."""
    while not _shutdown.is_set():
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(AgentDefinition).where(AgentDefinition.is_active == True)
                )
                defs = result.scalars().all()

            for defn in defs:
                if defn.name not in _running_dynamic:
                    _running_dynamic.add(defn.name)
                    tool_names = json.loads(defn.tools_config or "[]")
                    agent = DynamicAgent(
                        name=defn.name,
                        model=defn.model,
                        system_prompt=defn.system_prompt,
                        tool_names=tool_names,
                    )
                    console.print(f"[magenta]🤖 Spinning up dynamic agent: {defn.name}[/magenta]")
                    asyncio.create_task(run_agent_loop(
                        lambda a=agent: a.run(f"Run your scheduled task for: {a.name}"),
                        defn.schedule_seconds,
                        defn.name,
                    ))
        except Exception as exc:
            log.error("Dynamic agent watcher error: %s", exc)

        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dropshipping agent orchestrator")
    parser.add_argument("--store", action="store_true", help="Also run the FastAPI store server")
    parser.add_argument("--golive", action="store_true",
                        help="Run the Go-Live agent once as a pre-flight before starting the loops")
    parser.add_argument("--consensus", action="store_true",
                        help="Run the Business Analyst + operational agents in a consensus "
                             "loop until the plan is signed off, then exit")
    parser.add_argument("--rounds", type=int, default=4,
                        help="Max consensus rounds (with --consensus)")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        if args.consensus:
            asyncio.run(run_consensus_loop(max_rounds=args.rounds))
        else:
            asyncio.run(main(with_store=args.store, run_golive=args.golive))
    except KeyboardInterrupt:
        pass
