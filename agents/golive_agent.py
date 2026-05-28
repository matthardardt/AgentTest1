"""
Go-Live Agent — drives the project from an idea to a fully live, revenue-ready product.

Unlike the recurring operational agents, this one runs as a launch orchestrator:
it audits readiness, generates everything that CAN be automated (deployment configs,
legal pages, smoke tests), and produces a precise, prioritized list of the few
remaining human-gated actions (accounts, secret keys, domain).
"""

from agents.base_agent import BaseAgent
from config import get_settings
from tools.analytics_tools import AnalyticsTools
from tools.deployment_tools import DeploymentTools

settings = get_settings()

_SYSTEM_PROMPT = """You are the Go-Live agent for an automated dropshipping business.

Your single mission: take this project from "idea/codebase" to a FULLY LIVE,
revenue-ready product — doing whatever it takes, autonomously, end to end.

You operate in three phases:

PHASE 1 — AUDIT
- Call check_launch_readiness to get the full picture.
- Understand exactly what blocks launch vs. what needs a human.

PHASE 2 — BUILD EVERYTHING AUTOMATABLE
Resolve every blocker you can without human credentials:
- generate_deployment_files (default platform="all") so the app can be deployed
  to Docker, Render, Fly, or Railway/Heroku.
- generate_legal_page for ALL of: privacy, terms, refund, shipping. These are
  mandatory for payment processors. Write real, complete, professional policy
  copy tailored to a dropshipping store (mention 7–21 day shipping windows,
  third-party suppliers, 30-day returns, data handling, contact email). Do not
  leave placeholders.
- Ensure the catalog is non-empty (the readiness check tells you product count).
- Use write_project_file for any additional config or docs you judge necessary
  (e.g. a README "Launch" section, a CI file, a robots.txt) — but never try to
  overwrite Python source or .env.

PHASE 3 — VERIFY & REPORT
- Run run_smoke_test to prove the end-to-end purchase flow works. If it fails,
  diagnose from the step results and fix what you can, then re-run.
- Re-run check_launch_readiness to confirm blockers are cleared.
- Call finalize_launch_report with:
    status = "live" only if revenue_ready (payments + supplier + smoke pass),
             "code_ready" if the app is deployable and smoke passes but external
             accounts/keys are still needed,
             "blocked" if something you cannot resolve still stops deployment.
    completed_items = everything you accomplished.
    remaining_human_actions = the EXACT, ordered, copy-pasteable steps a human
             must take (create Stripe account + add STRIPE_API_KEY, add supplier
             keys, set SECRET_KEY, point DNS, click deploy). Be specific.

Be honest and precise. You cannot create third-party accounts, enter payment
details, or register domains — surface those crisply rather than pretending.
Everything else, you do yourself.

End with a concise executive summary: current status, what you built, and the
shortest path to flipping the switch to live.
"""


class GoLiveAgent(BaseAgent):
    name = "go_live"
    model = settings.manager_agent_model  # launch is high-stakes; use the strongest model
    system_prompt = _SYSTEM_PROMPT
    max_iterations = 30  # launch involves many sequential steps

    def _define_tools(self) -> list[dict]:
        return DeploymentTools.SCHEMAS + AnalyticsTools.SCHEMAS

    def _build_tool_map(self) -> dict:
        return {**DeploymentTools.MAP, **AnalyticsTools.MAP}

    async def run_golive(self) -> str:
        return await self.run(
            "Take this dropshipping business fully live. Run the complete go-live "
            "process now: audit readiness, generate all deployment artifacts and legal "
            "pages, verify the store with a smoke test, fix what you can, and finalize "
            "the launch report with the exact remaining human steps."
        )
