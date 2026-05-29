"""
Training tools — used exclusively by the Training Agent to store/retrieve
insights, advisories, and session logs, and to query other agents' performance.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    AgentAdvisory, AgentLog, BusinessMetric, TrainingInsight,
    TrainingSession, AsyncSessionLocal,
)


# ── Insight management ─────────────────────────────────────────────────────────

async def store_training_insight(
    category: str,
    insight: str,
    source_site: str = "",
    confidence_score: float = 0.8,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        db.add(TrainingInsight(
            source_site=source_site,
            category=category,
            insight=insight,
            confidence_score=confidence_score,
        ))
        await db.commit()
    return {"success": True, "category": category, "source": source_site}


async def get_training_insights(
    category: str | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        q = select(TrainingInsight).order_by(TrainingInsight.created_at.desc()).limit(limit)
        if category:
            q = q.where(TrainingInsight.category == category)
        result = await db.execute(q)
        rows = result.scalars().all()
    return {
        "insights": [
            {
                "id": r.id,
                "source_site": r.source_site,
                "category": r.category,
                "insight": r.insight,
                "confidence_score": r.confidence_score,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "count": len(rows),
    }


# ── Advisory management ────────────────────────────────────────────────────────

async def store_agent_advisory(
    target_agent: str,
    guidance: str,
    advisory_type: str = "strategic",
    priority: str = "medium",
) -> dict[str, Any]:
    """
    Supersede any existing active advisories for the agent with the same type,
    then store the new one.
    """
    async with AsyncSessionLocal() as db:
        # Supersede old active advisories of the same type for this agent
        old_q = await db.execute(
            select(AgentAdvisory)
            .where(AgentAdvisory.target_agent == target_agent)
            .where(AgentAdvisory.advisory_type == advisory_type)
            .where(AgentAdvisory.status == "active")
        )
        for old in old_q.scalars().all():
            old.status = "superseded"

        db.add(AgentAdvisory(
            target_agent=target_agent,
            guidance=guidance,
            advisory_type=advisory_type,
            priority=priority,
            status="active",
        ))
        await db.commit()
    return {"success": True, "target_agent": target_agent, "advisory_type": advisory_type}


async def get_agent_advisory(
    target_agent: str,
    limit: int = 3,
) -> dict[str, Any]:
    """Return the most recent active advisories for an agent. Called by other agents."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentAdvisory)
            .where(AgentAdvisory.target_agent == target_agent)
            .where(AgentAdvisory.status == "active")
            .order_by(AgentAdvisory.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
    if not rows:
        return {"advisories": [], "message": "No active advisories yet — proceed with defaults."}
    return {
        "advisories": [
            {
                "id": r.id,
                "advisory_type": r.advisory_type,
                "priority": r.priority,
                "guidance": r.guidance,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "count": len(rows),
    }


async def list_all_advisories(status: str = "active") -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentAdvisory)
            .where(AgentAdvisory.status == status)
            .order_by(AgentAdvisory.target_agent, AgentAdvisory.created_at.desc())
        )
        rows = result.scalars().all()
    return {
        "advisories": [
            {
                "target_agent": r.target_agent,
                "advisory_type": r.advisory_type,
                "priority": r.priority,
                "guidance": r.guidance[:200],
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "count": len(rows),
    }


# ── Session logging ────────────────────────────────────────────────────────────

async def record_training_session(
    sites_researched: list[str],
    insights_extracted: int,
    advisories_generated: int,
    self_improvement_notes: str,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        db.add(TrainingSession(
            sites_researched=json.dumps(sites_researched),
            insights_extracted=insights_extracted,
            advisories_generated=advisories_generated,
            self_improvement_notes=self_improvement_notes,
        ))
        await db.commit()
    return {"success": True, "insights": insights_extracted, "advisories": advisories_generated}


async def get_training_history(limit: int = 5) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TrainingSession).order_by(TrainingSession.created_at.desc()).limit(limit)
        )
        rows = result.scalars().all()
    return {
        "sessions": [
            {
                "sites_researched": json.loads(r.sites_researched or "[]"),
                "insights_extracted": r.insights_extracted,
                "advisories_generated": r.advisories_generated,
                "self_improvement_notes": r.self_improvement_notes,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


# ── Performance context for self-improvement ───────────────────────────────────

async def get_agent_performance_summary(days: int = 7) -> dict[str, Any]:
    """Summarize each agent's recent run history so the training agent can evaluate."""
    since = datetime.utcnow() - timedelta(days=days)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentLog)
            .where(AgentLog.created_at >= since)
            .order_by(AgentLog.agent_name, AgentLog.created_at.desc())
        )
        logs = result.scalars().all()

    summary: dict[str, Any] = {}
    for log in logs:
        agent = log.agent_name
        if agent not in summary:
            summary[agent] = {"runs": 0, "errors": 0, "avg_tokens": 0, "recent_results": []}
        summary[agent]["runs"] += 1
        if log.status == "error":
            summary[agent]["errors"] += 1
        summary[agent]["avg_tokens"] = (
            (summary[agent]["avg_tokens"] * (summary[agent]["runs"] - 1) + (log.tokens_used or 0))
            / summary[agent]["runs"]
        )
        if len(summary[agent]["recent_results"]) < 3:
            summary[agent]["recent_results"].append(
                {"status": log.status, "result_snippet": (log.result or "")[:150]}
            )

    return {"period_days": days, "agents": summary}


# ── Tool schemas ───────────────────────────────────────────────────────────────

class TrainingTools:
    SCHEMAS = [
        {
            "name": "store_training_insight",
            "description": "Persist a raw insight extracted from researching top e-commerce sites.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["copy", "pricing", "ux", "trust", "catalog", "promotion", "image", "seo"],
                        "description": "Insight category",
                    },
                    "insight": {"type": "string", "description": "The actionable insight text"},
                    "source_site": {"type": "string", "description": "Domain or store name researched"},
                    "confidence_score": {
                        "type": "number",
                        "description": "0.0–1.0 confidence in this insight",
                    },
                },
                "required": ["category", "insight"],
            },
        },
        {
            "name": "get_training_insights",
            "description": "Retrieve stored insights, optionally filtered by category.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["copy", "pricing", "ux", "trust", "catalog", "promotion", "image", "seo"],
                    },
                    "limit": {"type": "integer", "default": 30},
                },
            },
        },
        {
            "name": "store_agent_advisory",
            "description": (
                "Generate and store a tailored coaching advisory for an operational agent. "
                "Supersedes any previous advisory of the same type for that agent."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_agent": {
                        "type": "string",
                        "enum": [
                            "product_hunting", "pricing", "website_maintenance",
                            "design", "ordering", "image_validation", "manager",
                        ],
                        "description": "Which agent this advisory is for",
                    },
                    "guidance": {
                        "type": "string",
                        "description": "Detailed, actionable coaching guidance (be specific and elite-level)",
                    },
                    "advisory_type": {
                        "type": "string",
                        "enum": ["immediate", "strategic"],
                        "description": "immediate = act this run; strategic = ongoing best practice",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": ["target_agent", "guidance"],
            },
        },
        {
            "name": "get_agent_advisory",
            "description": "Fetch active coaching advisories for a specific agent.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_agent": {"type": "string"},
                    "limit": {"type": "integer", "default": 3},
                },
                "required": ["target_agent"],
            },
        },
        {
            "name": "list_all_advisories",
            "description": "List all current active advisories across all agents.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["active", "superseded"],
                        "default": "active",
                    }
                },
            },
        },
        {
            "name": "record_training_session",
            "description": "Log the results of a completed training cycle including self-improvement notes.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sites_researched": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of sites/sources studied this session",
                    },
                    "insights_extracted": {"type": "integer"},
                    "advisories_generated": {"type": "integer"},
                    "self_improvement_notes": {
                        "type": "string",
                        "description": "What worked, what didn't, how to improve next cycle",
                    },
                },
                "required": [
                    "sites_researched", "insights_extracted",
                    "advisories_generated", "self_improvement_notes",
                ],
            },
        },
        {
            "name": "get_training_history",
            "description": "Get logs of past training sessions for self-evaluation.",
            "input_schema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 5}},
            },
        },
        {
            "name": "get_agent_performance_summary",
            "description": (
                "Summarize each operational agent's recent run history "
                "(error rate, token usage, result snippets) to evaluate advisory effectiveness."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"days": {"type": "integer", "default": 7}},
            },
        },
    ]

    MAP = {
        "store_training_insight": store_training_insight,
        "get_training_insights": get_training_insights,
        "store_agent_advisory": store_agent_advisory,
        "get_agent_advisory": get_agent_advisory,
        "list_all_advisories": list_all_advisories,
        "record_training_session": record_training_session,
        "get_training_history": get_training_history,
        "get_agent_performance_summary": get_agent_performance_summary,
    }
