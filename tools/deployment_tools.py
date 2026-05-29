"""
Deployment & go-live tools.

These let the Go-Live agent take the project from source code to a publicly
running, revenue-ready product: validating readiness, generating deployment
artifacts (Docker, Render, Fly, Procfile), creating legal/policy pages, and
running an end-to-end smoke test of the live purchase flow.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from config import get_settings
from database import (
    AsyncSessionLocal, BusinessMetric, Order, OrderItem,
    Product, ProductStatus, init_db,
)

settings = get_settings()

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "store" / "templates"


# ── Readiness audit ────────────────────────────────────────────────────────────

async def check_launch_readiness() -> dict[str, Any]:
    """
    Audit the project for go-live readiness.

    Returns a structured report separating:
      - blockers: things that stop the app/site from functioning at all
      - human_actions_required: external setup the agent cannot do itself
        (create accounts, add secret keys, point a domain)
      - warnings: degraded-but-launchable conditions
      - passed: checks that are already satisfied
    """
    blockers: list[str] = []
    human_actions: list[str] = []
    warnings: list[str] = []
    passed: list[str] = []

    # 1. Anthropic key — without it, no agent can run
    if settings.anthropic_api_key:
        passed.append("ANTHROPIC_API_KEY is set — agents can run.")
    else:
        human_actions.append(
            "Set ANTHROPIC_API_KEY in .env (get one at console.anthropic.com). "
            "Without it the autonomous agents cannot run."
        )

    # 2. Database reachable + product catalog populated
    try:
        await init_db()
        async with AsyncSessionLocal() as db:
            count = (await db.execute(
                select(func.count(Product.id)).where(Product.status == ProductStatus.ACTIVE)
            )).scalar() or 0
        if count > 0:
            passed.append(f"Database reachable with {count} active product(s).")
        else:
            blockers.append(
                "No active products in catalog. Run `python -m scripts.seed` or let the "
                "product hunting agent populate the store before going live."
            )
    except Exception as exc:
        blockers.append(f"Database not reachable: {exc}")

    # 3. Payments — required to actually take money
    if settings.stripe_api_key:
        passed.append("Stripe API key configured — store can accept payments.")
        if not settings.stripe_webhook_secret:
            warnings.append(
                "STRIPE_WEBHOOK_SECRET is not set — payment confirmation webhooks "
                "won't be verified. Add it for production."
            )
    else:
        human_actions.append(
            "Create a Stripe account, then set STRIPE_API_KEY and STRIPE_WEBHOOK_SECRET. "
            "Until then orders are saved as PENDING and no money is collected."
        )

    # 4. Supplier integration — AliExpress for product sourcing
    if settings.aliexpress_app_key:
        passed.append(
            "AliExpress API configured — product sourcing uses live data. "
            "Orders are fulfilled manually (queued as manual tickets for the operator)."
        )
    else:
        warnings.append(
            "ALIEXPRESS_APP_KEY/SECRET not set — product search runs in MOCK mode. "
            "Add AliExpress credentials for live product sourcing. Order fulfilment is "
            "manual either way: paid orders are queued for you to place on AliExpress."
        )

    # 5. Email notifications
    if settings.smtp_host:
        passed.append("SMTP configured — customers receive order/shipping emails.")
    else:
        warnings.append(
            "SMTP not configured — order/shipping emails are logged instead of sent. "
            "Set SMTP_HOST/USER/PASSWORD for real customer notifications."
        )

    # 6. Production secret key
    if settings.secret_key and settings.secret_key not in ("change-me-in-production",
                                                            "change_this_to_a_random_secret_key"):
        passed.append("SECRET_KEY has been changed from the default.")
    else:
        human_actions.append(
            "Change SECRET_KEY to a random value before exposing the site publicly."
        )

    # 7. Store URL configured for production
    if settings.store_url and "localhost" not in settings.store_url:
        passed.append(f"STORE_URL points to a public address ({settings.store_url}).")
    else:
        human_actions.append(
            "Set STORE_URL to your public domain (e.g. https://shop.example.com) "
            "once deployed — used in emails and metadata."
        )

    # 8. Legal pages present
    legal_slugs = ["privacy", "terms", "refund", "shipping"]
    missing = [s for s in legal_slugs if not (TEMPLATES_DIR / f"legal_{s}.html").exists()]
    if not missing:
        passed.append("All legal pages present (privacy, terms, refund, shipping).")
    else:
        blockers.append(
            f"Missing legal pages: {', '.join(missing)}. Payment processors and app "
            "stores require these. Use generate_legal_page to create them."
        )

    # 9. Deployment artifacts present
    deploy_files = ["Dockerfile", "docker-compose.yml", "Procfile"]
    missing_deploy = [f for f in deploy_files if not (REPO_ROOT / f).exists()]
    if not missing_deploy:
        passed.append("Deployment artifacts present (Dockerfile, compose, Procfile).")
    else:
        blockers.append(
            f"Missing deployment files: {', '.join(missing_deploy)}. "
            "Use generate_deployment_files to create them."
        )

    code_ready = len(blockers) == 0
    return {
        "code_ready": code_ready,
        "revenue_ready": code_ready and bool(settings.stripe_api_key),
        "blockers": blockers,
        "human_actions_required": human_actions,
        "warnings": warnings,
        "passed": passed,
        "summary": (
            f"{len(passed)} checks passed, {len(blockers)} blockers, "
            f"{len(human_actions)} human actions, {len(warnings)} warnings."
        ),
    }


# ── Deployment artifact generation ──────────────────────────────────────────────

_DOCKERFILE = """\
FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist SQLite database to a mounted volume
RUN mkdir -p /app/data
ENV DATABASE_URL=sqlite+aiosqlite:////app/data/dropshipping.db

EXPOSE 8000

# Runs both the storefront and the agent orchestrator in one process
CMD ["python", "orchestrator.py", "--store"]
"""

_DOCKERIGNORE = """\
__pycache__/
*.pyc
.env
*.db
*.sqlite3
.git/
.venv/
venv/
.DS_Store
"""

_DOCKER_COMPOSE = """\
services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - DATABASE_URL=sqlite+aiosqlite:////app/data/dropshipping.db
    volumes:
      - dropdata:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  dropdata:
"""

_PROCFILE = """\
web: uvicorn store.main:app --host 0.0.0.0 --port $PORT
worker: python orchestrator.py
"""

_RENDER_YAML = """\
services:
  - type: web
    name: dropshop-store
    runtime: python
    plan: starter
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn store.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: STRIPE_API_KEY
        sync: false
      - key: STRIPE_WEBHOOK_SECRET
        sync: false
      - key: ALIEXPRESS_APP_KEY
        sync: false
      - key: ALIEXPRESS_APP_SECRET
        sync: false
      - key: SECRET_KEY
        generateValue: true
      - key: DATABASE_URL
        value: sqlite+aiosqlite:////var/data/dropshipping.db
    disk:
      name: dropdata
      mountPath: /var/data
      sizeGB: 1

  - type: worker
    name: dropshop-agents
    runtime: python
    plan: starter
    buildCommand: pip install -r requirements.txt
    startCommand: python orchestrator.py
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: ALIEXPRESS_APP_KEY
        sync: false
      - key: ALIEXPRESS_APP_SECRET
        sync: false
      - key: SERP_API_KEY
        sync: false
      - key: DATABASE_URL
        value: sqlite+aiosqlite:////var/data/dropshipping.db
    disk:
      name: dropdata
      mountPath: /var/data
      sizeGB: 1
"""

_FLY_TOML = """\
# fly.toml — deploy with `fly launch --no-deploy` then `fly deploy`
app = "dropshop"
primary_region = "iad"

[build]

[env]
  PORT = "8000"
  DATABASE_URL = "sqlite+aiosqlite:////data/dropshipping.db"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

[[mounts]]
  source = "dropdata"
  destination = "/data"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"
"""

_DEPLOYMENT_MD = """\
# Deployment Guide

This project ships with artifacts for several platforms. Pick one.

## Prerequisites (all platforms)
1. Copy `.env.example` to `.env` and fill in:
   - `ANTHROPIC_API_KEY` (required — powers all agents)
   - `STRIPE_API_KEY` + `STRIPE_WEBHOOK_SECRET` (to take real payments)
   - `ALIEXPRESS_APP_KEY` + `ALIEXPRESS_APP_SECRET` (for live product sourcing; orders fulfilled manually)
   - `SMTP_*` (to email customers)
   - `SECRET_KEY` (random string)
   - `STORE_URL` (your public domain)
2. Seed the catalog once: `python -m scripts.seed`

## Option A — Docker (any VPS)
```bash
docker compose up -d --build
```
The store is at `http://<host>:8000`. The SQLite DB persists in the `dropdata` volume.

## Option B — Render
Commit `render.yaml`, then in the Render dashboard: New > Blueprint > pick this repo.
Set the `sync:false` env vars (secrets) in the dashboard. Render provisions a web
service + worker + a shared disk automatically.

## Option C — Fly.io
```bash
fly launch --no-deploy   # accept the existing fly.toml
fly volumes create dropdata --size 1
fly secrets set ANTHROPIC_API_KEY=... STRIPE_API_KEY=... ALIEXPRESS_APP_KEY=...
fly deploy
```

## Option D — Railway / Heroku (Procfile)
Push the repo; the platform reads the `Procfile` (web + worker dynos).
Add the env vars in the platform dashboard.

## Going live checklist
- [ ] Public URL responds at `/health`
- [ ] Homepage shows products
- [ ] A test checkout creates an order
- [ ] Stripe live keys in place and a real test charge succeeds
- [ ] Supplier credentials in place (ordering agent out of mock mode)
- [ ] Domain pointed (DNS A/CNAME) and HTTPS active
- [ ] Legal pages reachable: /pages/privacy, /pages/terms, /pages/refund, /pages/shipping
"""

_DEPLOY_FILES: dict[str, str] = {
    "Dockerfile": _DOCKERFILE,
    ".dockerignore": _DOCKERIGNORE,
    "docker-compose.yml": _DOCKER_COMPOSE,
    "Procfile": _PROCFILE,
    "render.yaml": _RENDER_YAML,
    "fly.toml": _FLY_TOML,
    "DEPLOYMENT.md": _DEPLOYMENT_MD,
}


async def generate_deployment_files(platform: str = "all") -> dict[str, Any]:
    """
    Generate deployment artifacts. platform: 'docker' | 'render' | 'fly' |
    'procfile' | 'all' (default).
    """
    selection: dict[str, str]
    if platform == "docker":
        selection = {k: _DEPLOY_FILES[k] for k in
                     ("Dockerfile", ".dockerignore", "docker-compose.yml", "DEPLOYMENT.md")}
    elif platform == "render":
        selection = {k: _DEPLOY_FILES[k] for k in ("render.yaml", "DEPLOYMENT.md")}
    elif platform == "fly":
        selection = {k: _DEPLOY_FILES[k] for k in ("Dockerfile", "fly.toml", "DEPLOYMENT.md")}
    elif platform == "procfile":
        selection = {k: _DEPLOY_FILES[k] for k in ("Procfile", "DEPLOYMENT.md")}
    else:
        selection = _DEPLOY_FILES

    created = []
    for name, content in selection.items():
        (REPO_ROOT / name).write_text(content)
        created.append(name)

    return {
        "success": True,
        "platform": platform,
        "files_created": created,
        "note": "Review DEPLOYMENT.md for platform-specific launch steps.",
    }


# ── Legal / policy page generation ───────────────────────────────────────────────

async def generate_legal_page(slug: str, title: str, body_html: str) -> dict[str, Any]:
    """
    Create a legal/policy page served at /pages/{slug}.

    slug: one of 'privacy', 'terms', 'refund', 'shipping' (or custom).
    title: page heading.
    body_html: the page body as HTML (paragraphs, headings, lists).
    """
    safe_slug = "".join(c for c in slug.lower() if c.isalnum() or c in ("-", "_"))
    if not safe_slug:
        return {"error": "Invalid slug"}

    template = f"""{{% extends "base.html" %}}
{{% block title %}}{title} – {{{{ store_name }}}}{{% endblock %}}
{{% block content %}}
<div class="max-w-3xl mx-auto px-4 py-12">
  <h1 class="text-3xl font-bold mb-2">{title}</h1>
  <p class="text-sm text-gray-400 mb-8">Last updated: {datetime.utcnow().strftime('%B %d, %Y')}</p>
  <div class="prose prose-sm max-w-none text-gray-600 space-y-4 leading-relaxed">
    {body_html}
  </div>
</div>
{{% endblock %}}
"""
    path = TEMPLATES_DIR / f"legal_{safe_slug}.html"
    path.write_text(template)
    return {
        "success": True,
        "slug": safe_slug,
        "url": f"/pages/{safe_slug}",
        "file": str(path.relative_to(REPO_ROOT)),
    }


# ── End-to-end smoke test ────────────────────────────────────────────────────────

async def run_smoke_test() -> dict[str, Any]:
    """
    Run an end-to-end smoke test against the storefront in-process:
    health → list products → product detail → cart validate → create order →
    fetch order. Verifies the full customer purchase path works. Cleans up the
    test order afterward.
    """
    import httpx
    await init_db()

    # Lazy import to avoid circulars and heavy load at module import time
    from store.main import app

    steps: list[dict] = []
    created_order_id: str | None = None

    def record(name: str, ok: bool, detail: str = "") -> None:
        steps.append({"step": name, "ok": ok, "detail": detail})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://smoketest") as client:
        # 1. Health
        try:
            r = await client.get("/health")
            record("health", r.status_code == 200, f"status={r.status_code}")
        except Exception as exc:
            record("health", False, str(exc))

        # 1b. Homepage renders (HTML template)
        try:
            r = await client.get("/")
            ok = r.status_code == 200 and "<html" in r.text.lower()
            record("homepage_render", ok, f"status={r.status_code}")
        except Exception as exc:
            record("homepage_render", False, str(exc))

        # 2. List products
        product_id = None
        price = None
        try:
            r = await client.get("/api/products/")
            data = r.json()
            products = data.get("products", [])
            ok = r.status_code == 200 and len(products) > 0
            record("list_products", ok, f"{len(products)} products")
            if products:
                product_id = products[0]["id"]
                price = products[0]["selling_price"]
        except Exception as exc:
            record("list_products", False, str(exc))

        # 3. Product detail (API + rendered HTML page)
        if product_id:
            try:
                r = await client.get(f"/api/products/{product_id}")
                record("product_detail", r.status_code == 200, f"status={r.status_code}")
            except Exception as exc:
                record("product_detail", False, str(exc))

            try:
                r = await client.get(f"/product/{product_id}")
                ok = r.status_code == 200 and "<html" in r.text.lower()
                record("product_page_render", ok, f"status={r.status_code}")
            except Exception as exc:
                record("product_page_render", False, str(exc))

            # 4. Cart validate
            try:
                r = await client.post("/api/cart/validate",
                                      json={"items": [{"product_id": product_id, "quantity": 2}]})
                data = r.json()
                record("cart_validate", r.status_code == 200 and data.get("total", 0) > 0,
                       f"total={data.get('total')}")
            except Exception as exc:
                record("cart_validate", False, str(exc))

            # 5. Create order
            try:
                r = await client.post("/api/orders/", json={
                    "email": "smoketest@example.com",
                    "shipping_address": {
                        "name": "Smoke Test",
                        "address_line1": "123 Test St",
                        "city": "Testville",
                        "state": "TS",
                        "country": "US",
                        "postal_code": "00000",
                        "phone": "555-0100",
                    },
                    "items": [{"product_id": product_id, "quantity": 1}],
                    "payment_id": "",
                })
                data = r.json()
                created_order_id = data.get("order_id")
                record("create_order", r.status_code == 200 and bool(created_order_id),
                       f"order={data.get('order_number')}")
            except Exception as exc:
                record("create_order", False, str(exc))

            # 6. Fetch order
            if created_order_id:
                try:
                    r = await client.get(f"/api/orders/{created_order_id}")
                    record("fetch_order", r.status_code == 200, f"status={r.status_code}")
                except Exception as exc:
                    record("fetch_order", False, str(exc))
        else:
            record("order_flow", False, "skipped — no products to order")

    # Cleanup the smoke-test order so we don't pollute real data
    if created_order_id:
        try:
            async with AsyncSessionLocal() as db:
                items = (await db.execute(
                    select(OrderItem).where(OrderItem.order_id == created_order_id)
                )).scalars().all()
                for it in items:
                    await db.delete(it)
                order = (await db.execute(
                    select(Order).where(Order.id == created_order_id)
                )).scalar_one_or_none()
                if order:
                    await db.delete(order)
                await db.commit()
        except Exception:
            pass  # cleanup is best-effort

    passed = sum(1 for s in steps if s["ok"])
    total = len(steps)
    return {
        "passed": passed == total,
        "score": f"{passed}/{total}",
        "steps": steps,
    }


# ── Generic project file writer (sandboxed) ──────────────────────────────────────

async def write_project_file(relative_path: str, content: str) -> dict[str, Any]:
    """
    Write a file inside the project (for deployment configs, docs, etc.).
    Sandboxed to the repo; refuses to overwrite existing .py source or .env.
    """
    target = (REPO_ROOT / relative_path).resolve()
    if not str(target).startswith(str(REPO_ROOT)):
        return {"error": "Path escapes project root — refused."}
    if target.name == ".env":
        return {"error": "Refusing to overwrite .env (contains secrets)."}
    if target.suffix == ".py" and target.exists():
        return {"error": f"Refusing to overwrite existing source file {relative_path}."}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"success": True, "path": relative_path, "bytes": len(content)}


# ── Launch report recording ──────────────────────────────────────────────────────

async def finalize_launch_report(
    status: str,
    completed_items: list[str],
    remaining_human_actions: list[str],
    notes: str = "",
) -> dict[str, Any]:
    """
    Record the final go-live report as a business metric for the manager/audit trail.
    status: 'live' | 'code_ready' | 'blocked'
    """
    score_map = {"live": 100.0, "code_ready": 75.0, "blocked": 25.0}
    async with AsyncSessionLocal() as db:
        db.add(BusinessMetric(
            metric_name="go_live_status",
            metric_value=score_map.get(status, 0.0),
            metric_data=json.dumps({
                "status": status,
                "completed": completed_items,
                "remaining_human_actions": remaining_human_actions,
                "notes": notes,
                "recorded_at": datetime.utcnow().isoformat(),
            }),
        ))
        await db.commit()
    return {"success": True, "status": status}


# ── Tool schemas ──────────────────────────────────────────────────────────────────

class DeploymentTools:
    SCHEMAS = [
        {
            "name": "check_launch_readiness",
            "description": "Audit the entire project for go-live readiness. Returns blockers, "
                           "required human actions, warnings, and passed checks.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "generate_deployment_files",
            "description": "Generate deployment artifacts (Dockerfile, docker-compose, Procfile, "
                           "render.yaml, fly.toml, DEPLOYMENT.md).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "enum": ["all", "docker", "render", "fly", "procfile"],
                        "description": "Which platform's files to generate (default: all)",
                    },
                },
            },
        },
        {
            "name": "generate_legal_page",
            "description": "Create a legal/policy page (privacy, terms, refund, shipping) served "
                           "at /pages/{slug}. Provide the title and full body HTML.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "e.g. privacy, terms, refund, shipping"},
                    "title": {"type": "string"},
                    "body_html": {"type": "string", "description": "Page body as HTML"},
                },
                "required": ["slug", "title", "body_html"],
            },
        },
        {
            "name": "run_smoke_test",
            "description": "Run an end-to-end smoke test of the live purchase flow "
                           "(health, products, cart, order). Verifies the store actually works.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "write_project_file",
            "description": "Write a file into the project (deployment configs, docs). Sandboxed; "
                           "cannot overwrite existing Python source or .env.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "relative_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["relative_path", "content"],
            },
        },
        {
            "name": "finalize_launch_report",
            "description": "Record the final go-live report (status, completed items, remaining "
                           "human actions) to the metrics/audit trail.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["live", "code_ready", "blocked"]},
                    "completed_items": {"type": "array", "items": {"type": "string"}},
                    "remaining_human_actions": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "required": ["status", "completed_items", "remaining_human_actions"],
            },
        },
    ]

    MAP = {
        "check_launch_readiness": check_launch_readiness,
        "generate_deployment_files": generate_deployment_files,
        "generate_legal_page": generate_legal_page,
        "run_smoke_test": run_smoke_test,
        "write_project_file": write_project_file,
        "finalize_launch_report": finalize_launch_report,
    }
