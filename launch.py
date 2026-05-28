"""
Go-Live entry point.

Runs the Go-Live agent once: it audits readiness, generates deployment artifacts
and legal pages, smoke-tests the store, and reports the exact remaining steps to
flip the business to fully live.

Usage:
    python launch.py
"""

import asyncio

from rich.console import Console

from database import init_db
from agents.golive_agent import GoLiveAgent

console = Console()


async def main() -> None:
    console.print("[bold cyan]🚀 Go-Live process starting…[/bold cyan]\n")
    await init_db()
    agent = GoLiveAgent()
    report = await agent.run_golive()
    console.rule("[bold green]Go-Live Report")
    console.print(report)


if __name__ == "__main__":
    asyncio.run(main())
