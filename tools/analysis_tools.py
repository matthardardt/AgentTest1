"""
Business-analysis tools.

These power the Business Analysis Agent: read the real catalog economics,
build a transparent month-by-month financial projection, post recommendations
to the other agents, and record a go/no-go verdict on the business plan.

The projection math lives in `compute_projection` — a pure function with no DB
or network dependency — so the deck generator and the agent always produce the
same numbers.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    AsyncSessionLocal, BusinessMetric, Order, OrderItem,
    OrderStatus, Product, ProductStatus,
)


# ── The financial model (pure, deterministic) ──────────────────────────────────

# Default assumptions reflect the "optimized" plan the agents converge toward:
# scaling paid spend as ROAS proves out, a growing organic/email channel, a
# rising conversion rate and AOV (bundles + free-ship threshold), and repeat
# purchases that carry no acquisition cost.
DEFAULT_ASSUMPTIONS: dict[str, Any] = {
    "months": 12,
    "ad_spend":        [1500, 2000, 2600, 3300, 4100, 5000, 5800, 6500, 7200, 7800, 8300, 8800],
    "organic_sessions": [400,  900, 1600, 2500, 3600, 4800, 6000, 7200, 8300, 9300, 10200, 11000],
    "paid_cpc": 0.75,            # blended cost per paid session (improves with creative)
    "cvr_start": 0.013,          # conversion rate month 1
    "cvr_end": 0.031,            # conversion rate month 12 (trust, reviews, UX)
    "aov_start": 38.0,           # average order value month 1
    "aov_end": 49.0,             # average order value month 12 (bundles + free-ship threshold)
    "cogs_pct": 0.30,            # product cost as a share of revenue (~70% gross margin)
    "ship_per_order": 4.0,       # outbound shipping we absorb (free shipping)
    "processing_pct": 0.029,     # Stripe %
    "processing_fixed": 0.30,    # Stripe per-transaction fee
    "returns_pct": 0.03,         # refunds / defects allowance
    "fixed_opex_start": 350.0,   # hosting, email, SerpAPI, Claude API, tools
    "fixed_opex_end": 750.0,
    "repeat_rate_start": 0.0,    # share of existing customers who reorder each month
    "repeat_rate_end": 0.18,     # email/retention channel matures
}

# A naive, paid-only plan with no AOV optimisation, organic, or retention — what
# the analyst rejects on round one. Used in the deck to show the gap that the
# agent iterations close.
BASELINE_ASSUMPTIONS: dict[str, Any] = {
    "months": 12,
    "ad_spend":        [1500, 2000, 2600, 3300, 4100, 5000, 6000, 6900, 7700, 8400, 9000, 9500],
    "organic_sessions": [100,  150,  200,  260,  320,  380,  440,  500,  560,  620,  680,  740],
    "paid_cpc": 0.90,
    "cvr_start": 0.010, "cvr_end": 0.013,
    "aov_start": 34.0, "aov_end": 36.0,
    "cogs_pct": 0.30, "ship_per_order": 4.0,
    "processing_pct": 0.029, "processing_fixed": 0.30, "returns_pct": 0.03,
    "fixed_opex_start": 350.0, "fixed_opex_end": 750.0,
    "repeat_rate_start": 0.0, "repeat_rate_end": 0.02,
}


def _ramp(start: float, end: float, i: int, n: int) -> float:
    if n <= 1:
        return start
    return start + (end - start) * i / (n - 1)


def compute_projection(assumptions: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the month-by-month model. Returns {'months': [...], 'summary': {...},
    'assumptions': {...}}. Pure function — safe to call anywhere."""
    a = {**DEFAULT_ASSUMPTIONS, **(assumptions or {})}
    n = int(a["months"])

    rows: list[dict[str, Any]] = []
    cum_customers = 0.0
    cum_revenue = 0.0
    cum_profit = 0.0
    cum_marketing = 0.0
    cum_new_orders = 0.0
    breakeven_month = None
    cashflow_positive_month = None

    for i in range(n):
        m = i + 1
        ad = float(a["ad_spend"][i])
        organic = float(a["organic_sessions"][i])
        cvr = _ramp(a["cvr_start"], a["cvr_end"], i, n)
        aov = _ramp(a["aov_start"], a["aov_end"], i, n)
        repeat_rate = _ramp(a["repeat_rate_start"], a["repeat_rate_end"], i, n)
        fixed = _ramp(a["fixed_opex_start"], a["fixed_opex_end"], i, n)

        paid_sessions = ad / a["paid_cpc"] if a["paid_cpc"] else 0.0
        sessions = paid_sessions + organic

        new_orders = sessions * cvr                      # each new order ≈ one new customer
        repeat_orders = repeat_rate * cum_customers      # reorders from existing base
        orders = new_orders + repeat_orders

        revenue = orders * aov
        cogs = revenue * a["cogs_pct"]
        shipping = orders * a["ship_per_order"]
        processing = revenue * a["processing_pct"] + orders * a["processing_fixed"]
        returns = revenue * a["returns_pct"]
        marketing = ad

        variable_cost = cogs + shipping + processing + returns
        contribution = revenue - variable_cost          # before marketing & fixed
        profit = contribution - marketing - fixed

        cum_customers += new_orders
        cum_new_orders += new_orders
        cum_revenue += revenue
        cum_profit += profit
        cum_marketing += marketing

        if breakeven_month is None and profit > 0:
            breakeven_month = m
        if cashflow_positive_month is None and cum_profit > 0:
            cashflow_positive_month = m

        cac = marketing / new_orders if new_orders else 0.0
        roas = revenue / marketing if marketing else 0.0

        rows.append({
            "month": m,
            "ad_spend": round(ad, 2),
            "sessions": round(sessions),
            "cvr": round(cvr * 100, 2),
            "orders": round(orders),
            "new_orders": round(new_orders),
            "repeat_orders": round(repeat_orders),
            "aov": round(aov, 2),
            "revenue": round(revenue, 2),
            "cogs": round(cogs, 2),
            "shipping": round(shipping, 2),
            "processing": round(processing, 2),
            "returns": round(returns, 2),
            "marketing": round(marketing, 2),
            "fixed_opex": round(fixed, 2),
            "contribution": round(contribution, 2),
            "profit": round(profit, 2),
            "cum_profit": round(cum_profit, 2),
            "cac": round(cac, 2),
            "roas": round(roas, 2),
            "contribution_margin_pct": round(contribution / revenue * 100, 1) if revenue else 0.0,
        })

    avg_aov = sum(r["aov"] for r in rows) / n
    blended_cac = cum_marketing / cum_new_orders if cum_new_orders else 0.0
    total_orders = sum(r["orders"] for r in rows)
    avg_contribution_per_order = (
        sum(r["contribution"] for r in rows) / total_orders if total_orders else 0.0
    )
    # Lifetime orders per customer, grounded in the model's own realized repeat
    # dynamics (total orders / new customers), nudged up modestly to account for
    # repeats that land beyond the 12-month horizon.
    realized_orders_per_customer = total_orders / cum_new_orders if cum_new_orders else 1.0
    est_lifetime_orders = realized_orders_per_customer * 1.15
    ltv = avg_contribution_per_order * est_lifetime_orders

    summary = {
        "horizon_months": n,
        "annual_revenue": round(cum_revenue, 2),
        "annual_profit": round(cum_profit, 2),
        "annual_marketing": round(cum_marketing, 2),
        "net_margin_pct": round(cum_profit / cum_revenue * 100, 1) if cum_revenue else 0.0,
        "breakeven_month": breakeven_month,
        "cashflow_positive_month": cashflow_positive_month,
        "exit_run_rate_annual": round(rows[-1]["revenue"] * 12, 2),
        "exit_monthly_profit": rows[-1]["profit"],
        "avg_aov": round(avg_aov, 2),
        "blended_cac": round(blended_cac, 2),
        "ltv": round(ltv, 2),
        "ltv_cac_ratio": round(ltv / blended_cac, 2) if blended_cac else 0.0,
        "blended_roas": round(cum_revenue / cum_marketing, 2) if cum_marketing else 0.0,
        "total_customers": round(cum_new_orders),
    }
    return {"months": rows, "summary": summary, "assumptions": a}


# ── Tool implementations ────────────────────────────────────────────────────────

async def get_catalog_economics() -> dict[str, Any]:
    """Inspect the live catalog and compute real unit economics the projection
    should be grounded in (avg price, avg cost, blended gross margin)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Product).where(Product.status == ProductStatus.ACTIVE)
        )
        products = result.scalars().all()

    if not products:
        return {"product_count": 0, "note": "No active products — seed the catalog first."}

    prices = [p.selling_price for p in products]
    costs = [p.cost_price or 0.0 for p in products]
    margins_pct = [
        round((p.selling_price - (p.cost_price or 0)) / p.selling_price * 100, 1)
        for p in products if p.selling_price
    ]
    avg_price = sum(prices) / len(prices)
    avg_cost = sum(costs) / len(costs)
    gross_margin_pct = (avg_price - avg_cost) / avg_price * 100 if avg_price else 0.0

    categories: dict[str, int] = {}
    for p in products:
        categories[p.category or "Uncategorized"] = categories.get(p.category or "Uncategorized", 0) + 1

    return {
        "product_count": len(products),
        "avg_selling_price": round(avg_price, 2),
        "avg_cost_price": round(avg_cost, 2),
        "avg_gross_margin_pct": round(gross_margin_pct, 1),
        "min_price": round(min(prices), 2),
        "max_price": round(max(prices), 2),
        "lowest_margin_pct": min(margins_pct) if margins_pct else 0.0,
        "category_distribution": categories,
    }


async def build_financial_projection(assumptions: dict | None = None) -> dict[str, Any]:
    """Compute the 12-month projection and persist its summary as a business
    metric so the dashboard and other agents can see it."""
    model = compute_projection(assumptions)
    async with AsyncSessionLocal() as db:
        db.add(BusinessMetric(
            metric_name="financial_projection",
            metric_value=model["summary"]["annual_profit"],
            metric_data=json.dumps(model["summary"]),
        ))
        await db.commit()
    # Return the summary + first/last month so the agent can reason without a
    # giant payload.
    return {
        "summary": model["summary"],
        "month_1": model["months"][0],
        "month_12": model["months"][-1],
    }


async def post_recommendation(
    target_agent: str,
    title: str,
    detail: str,
    priority: str = "medium",
) -> dict[str, Any]:
    """Record a recommendation addressed to a specific agent. Operational agents
    read these on their next cycle via get_recommendations and adjust accordingly."""
    async with AsyncSessionLocal() as db:
        db.add(BusinessMetric(
            metric_name=f"recommendation:{target_agent}",
            metric_value={"low": 1, "medium": 2, "high": 3}.get(priority, 2),
            metric_data=json.dumps({
                "target_agent": target_agent,
                "title": title,
                "detail": detail,
                "priority": priority,
                "issued_at": datetime.utcnow().isoformat(),
            }),
        ))
        await db.commit()
    return {"success": True, "target_agent": target_agent, "title": title}


async def get_recommendations(target_agent: str | None = None, days: int = 7) -> dict[str, Any]:
    """Fetch recent recommendations, optionally filtered to one agent. Each
    operational agent calls this with its own name to see what to change."""
    since = datetime.utcnow() - timedelta(days=days)
    name = f"recommendation:{target_agent}" if target_agent else None
    async with AsyncSessionLocal() as db:
        q = select(BusinessMetric).where(BusinessMetric.recorded_at >= since)
        if name:
            q = q.where(BusinessMetric.metric_name == name)
        else:
            q = q.where(BusinessMetric.metric_name.like("recommendation:%"))
        q = q.order_by(BusinessMetric.recorded_at.desc())
        result = await db.execute(q)
        rows = result.scalars().all()
    return {
        "recommendations": [
            {**json.loads(r.metric_data or "{}"), "recorded_at": r.recorded_at.isoformat()}
            for r in rows
        ]
    }


async def assess_business_plan(
    verdict: str,
    score: int,
    rationale: str,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    """Record the analyst's go/no-go verdict on the overall plan.
    verdict: 'sound' | 'needs_work' | 'not_viable'."""
    async with AsyncSessionLocal() as db:
        db.add(BusinessMetric(
            metric_name="business_plan_assessment",
            metric_value=float(score),
            metric_data=json.dumps({
                "verdict": verdict,
                "score": score,
                "rationale": rationale,
                "blockers": blockers or [],
                "assessed_at": datetime.utcnow().isoformat(),
            }),
        ))
        await db.commit()
    return {"success": True, "verdict": verdict, "score": score}


# ── Tool schemas ────────────────────────────────────────────────────────────────

class AnalysisTools:
    SCHEMAS = [
        {
            "name": "get_catalog_economics",
            "description": "Inspect the live product catalog and return real unit "
                           "economics: average price, average cost, blended gross "
                           "margin, price range, and category mix.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "build_financial_projection",
            "description": "Compute a transparent 12-month financial projection "
                           "(sessions, conversions, revenue, costs, profit) and "
                           "persist its summary. Optionally override assumptions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "assumptions": {
                        "type": "object",
                        "description": "Optional overrides: paid_cpc, cvr_start, cvr_end, "
                                       "aov_start, aov_end, cogs_pct, repeat_rate_end, "
                                       "ad_spend (array), organic_sessions (array), etc.",
                    },
                },
            },
        },
        {
            "name": "post_recommendation",
            "description": "Send a specific, actionable recommendation to another "
                           "agent (e.g. pricing, product_hunting, website, design, "
                           "manager). They read it on their next cycle and adjust.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_agent": {"type": "string"},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["target_agent", "title", "detail"],
            },
        },
        {
            "name": "get_recommendations",
            "description": "Read recent recommendations, optionally filtered to a "
                           "single target agent.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_agent": {"type": "string"},
                    "days": {"type": "integer", "default": 7},
                },
            },
        },
        {
            "name": "assess_business_plan",
            "description": "Record a go/no-go verdict on the overall business plan "
                           "with a 0-100 confidence score and rationale.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "verdict": {"type": "string", "enum": ["sound", "needs_work", "not_viable"]},
                    "score": {"type": "integer"},
                    "rationale": {"type": "string"},
                    "blockers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["verdict", "score", "rationale"],
            },
        },
    ]

    MAP = {
        "get_catalog_economics": get_catalog_economics,
        "build_financial_projection": build_financial_projection,
        "post_recommendation": post_recommendation,
        "get_recommendations": get_recommendations,
        "assess_business_plan": assess_business_plan,
    }

    # Read-only subset handed to operational agents so they can consume the
    # analyst's recommendations without being able to issue or self-assess them.
    READ_SCHEMAS = [s for s in SCHEMAS if s["name"] == "get_recommendations"]
    READ_MAP = {"get_recommendations": get_recommendations}
