# Vendo's Deals — Launch Guide

Everything you need to go from code to live store. Do the steps in order.

---

## Current Status

| Item | Status |
|---|---|
| Code & store | ✅ Built and tested |
| All 8 agents wired up | ✅ Running on schedule |
| Training Agent (elite consultant) | ✅ Active, advising all agents |
| Legal pages | ✅ Privacy, Terms, Refund, Shipping |
| Deployment configs | ✅ Render, Fly, Docker, Railway |
| `.env` scaffold | ✅ Created (with a generated `SECRET_KEY`) |
| `SECRET_KEY` | ✅ Generated and written to `.env` |
| `ANTHROPIC_API_KEY` | ❌ Paste yours into `.env` |
| Stripe (payments) | ❌ Needs account + keys |
| AliExpress (product sourcing) | ⚠️ Optional — mock data without keys |
| Order fulfilment | ℹ️ Manual (you place AliExpress orders by hand) |
| Email notifications | ❌ Needs SMTP credentials |
| Deployed to internet | ❌ Not yet |
| Custom domain | ❌ Not yet |

> **About your keys:** I created a `.env` file at the project root with everything
> non-secret pre-filled and a freshly generated `SECRET_KEY`. I could **not** fill in
> your actual API keys (Anthropic, Stripe, AliExpress, SMTP) — they were never shared
> with me and aren't in this environment. Open `.env` and replace each
> `PASTE_YOUR_..._HERE` placeholder with your real value.
>
> Note: `.env` is gitignored (correctly — secrets must never be committed) and this is
> an ephemeral container, so treat the `.env` here as a template. The durable copy lives
> in your deploy platform's environment variables (Step 6).

---

## Step 1 — Get your Anthropic API key

The agents can't run without this.

1. Go to **https://console.anthropic.com** → sign in or create an account.
2. **API Keys** → **Create Key** → copy it (`sk-ant-api03-...`).
3. Paste it into `ANTHROPIC_API_KEY` in your `.env` (replacing the placeholder).
4. Add usage limits under **Plans & Billing** to avoid surprises.

---

## Step 2 — Secret key (already done)

A secure `SECRET_KEY` has already been generated and written to your `.env`. Nothing to do.

If you ever want to rotate it:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

…then paste the new value into `SECRET_KEY`.

---

## Step 3 — Set up Stripe (payments)

### 3a. Create account
1. **https://dashboard.stripe.com/register** — sign up, verify email.
2. Complete the business profile (country required to process payments).

### 3b. Get API keys
1. Dashboard → **Developers** → **API Keys**.
2. Copy the **Secret key** (`sk_test_...` for now, `sk_live_...` when ready to go live).

### 3c. Set up webhook
Stripe must notify your server when a payment succeeds — without this, orders won't confirm.

1. Dashboard → **Developers** → **Webhooks** → **Add endpoint**.
2. URL: `https://yourdomain.com/api/orders/webhook/stripe`  
   *(use your real domain — come back here after Step 6)*
3. Events: check **`payment_intent.succeeded`** and **`checkout.session.completed`**.
4. Save, then reveal and copy the **Signing secret** (`whsec_...`).

---

## Step 4 — Product sourcing & fulfilment (AliExpress)

You're sourcing products from **AliExpress**. Fulfilment is **manual** — AliExpress has
no automated order API, so the system queues each paid order as a "manual ticket" for you
to place on AliExpress by hand, then you record the tracking number back on the order.
This means **no supplier API key is required to go live** — but adding AliExpress keys
upgrades the product-hunting agent from mock data to live product search.

### 4a. (Optional) Get AliExpress API keys for live product data
1. Go to **https://portals.aliexpress.com** (AliExpress Affiliate / Open Platform) and
   sign up for a developer/affiliate account.
2. Create an app to obtain an **App Key** and **App Secret**.
3. Paste them into `ALIEXPRESS_APP_KEY` and `ALIEXPRESS_APP_SECRET` in your `.env`.

> Skip this and the agents still run — product search just uses mock data until keys are added.

### 4b. How manual fulfilment works day-to-day
1. A customer pays → order becomes `PAID`.
2. The ordering agent queues a manual-fulfilment ticket and sets status to `ordered_from_supplier`.
3. **You** place that order on AliExpress, shipping to the customer's address.
4. When AliExpress gives you a tracking number, record it on the order (admin) — the agent
   then sets the order to `shipped` and emails the customer the tracking link.

> Tip: when you're ready to fully automate fulfilment, you can later add a supplier with an
> order API (e.g. CJ Dropshipping, Zendrop, Spocket). The integration point is
> `tools/supplier_tools.py`.

---

## Step 5 — Set up email notifications

Customers receive order confirmation and shipping update emails.

**Resend (recommended — free for 3,000 emails/month):**
1. **https://resend.com** → sign up.
2. **API Keys** → **Create API Key** → copy it.
3. **Domains** → **Add Domain** → verify DNS (follow their instructions, takes ~5 min).

```
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USER=resend
SMTP_PASSWORD=re_xxxxxxxxxxxxxxxxxxxx
FROM_EMAIL=orders@yourdomain.com
```

**Gmail (quick for testing):**
1. Google Account → Security → **App passwords** → generate one for "Mail".
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx
FROM_EMAIL=your@gmail.com
```

---

## Step 6 — Deploy

Pick one platform. **Render is the easiest.**

---

### Option A — Render *(recommended, ~$14/month)*

1. **https://render.com** → sign in with GitHub.
2. **New** → **Blueprint** → connect your repo (`matthardardt/AgentTest1`).
3. Render reads `render.yaml` and creates:
   - `dropshop-store` (web server)
   - `dropshop-agents` (background worker)
4. Before clicking **Apply**, add environment variables for both services:

   | Key | Both services | Web only |
   |---|---|---|
   | `ANTHROPIC_API_KEY` | ✅ | |
   | `ALIEXPRESS_APP_KEY` *(optional)* | ✅ | |
   | `ALIEXPRESS_APP_SECRET` *(optional)* | ✅ | |
   | `STRIPE_API_KEY` | | ✅ |
   | `STRIPE_WEBHOOK_SECRET` | | ✅ |
   | `SECRET_KEY` | | ✅ |
   | `STORE_NAME` | | ✅ |
   | `SMTP_HOST/PORT/USER/PASSWORD` | | ✅ |
   | `FROM_EMAIL` | | ✅ |

5. Click **Apply** — build takes ~3 minutes.
6. Seed the catalog:

```bash
# Render dashboard → dropshop-store → Shell
python -m scripts.seed
```

---

### Option B — Fly.io *(~$5–10/month)*

```bash
# Install flyctl: https://fly.io/docs/getting-started/installing-flyctl/
fly auth login
fly launch --no-deploy
fly volumes create dropdata --region iad --size 1

fly secrets set \
  ANTHROPIC_API_KEY="sk-ant-..." \
  STRIPE_API_KEY="sk_test_..." \
  STRIPE_WEBHOOK_SECRET="whsec_..." \
  SECRET_KEY="your-32-char-random-string" \
  ALIEXPRESS_APP_KEY="..." \
  ALIEXPRESS_APP_SECRET="..." \
  SMTP_HOST="smtp.resend.com" \
  SMTP_PORT="465" \
  SMTP_USER="resend" \
  SMTP_PASSWORD="re_..." \
  FROM_EMAIL="orders@yourdomain.com" \
  STORE_NAME="Vendo's Deals"

fly deploy
```

---

### Option C — Docker on a VPS *(DigitalOcean, Hetzner, etc.)*

```bash
# Local: fill in your .env
cp .env.example .env
nano .env   # fill in all values from steps 1–5

# On VPS (Ubuntu 22.04)
curl -fsSL https://get.docker.com | sh
scp -r . user@server-ip:/app/vendos
scp .env user@server-ip:/app/vendos/.env
ssh user@server-ip
cd /app/vendos && docker compose up -d --build
```

---

### Option D — Railway

1. **https://railway.app** → New Project → Deploy from GitHub.
2. Railway reads `Procfile` and creates web + worker dynos.
3. Add all env vars in the **Variables** tab.

---

## Step 7 — Point your domain

### Buy a domain (if needed)
- **Cloudflare Registrar**: https://cloudflare.com *(at-cost, no markup)*
- **Namecheap**: https://namecheap.com *(~$10–15/year for .com)*

### Connect to Render
1. Render → `dropshop-store` → **Settings** → **Custom Domains** → **Add Domain**.
2. Add your domain; Render gives you a CNAME target.
3. In your DNS settings, add:

   | Type | Name | Value |
   |---|---|---|
   | `CNAME` | `@` or `shop` | `dropshop-store.onrender.com` |

   DNS propagates in 5–30 minutes. SSL is automatic.

4. Update env var: `STORE_URL=https://yourdomain.com` and redeploy.

---

## Step 8 — Update the Stripe webhook URL

Now that you have a real domain:

1. Stripe → **Developers** → **Webhooks** → click your endpoint → **Update endpoint**.
2. Change the URL to `https://yourdomain.com/api/orders/webhook/stripe`.

---

## Step 9 — Run the verification checklist

```
[ ] https://yourdomain.com/health  →  {"status":"ok"}
[ ] Homepage loads and shows products
[ ] Product page loads, images display correctly
[ ] Add to cart works
[ ] Stripe test checkout (card: 4242 4242 4242 4242 / any future date / any CVC)
      → order confirmation page appears
      → Stripe dashboard shows the test charge
[ ] All legal pages load:
      /pages/privacy  /pages/terms  /pages/refund  /pages/shipping
[ ] Agents show activity in: /api/admin/agents
```

---

## Step 10 — Switch Stripe to live mode

When testing is complete and you're ready for real payments:

1. Stripe → toggle **Test mode → Live mode**.
2. **Developers → API Keys** → copy the **live** secret key (`sk_live_...`).
3. **Developers → Webhooks** → create a new webhook in live mode (same URL). Copy the new `whsec_...` signing secret.
4. Update `STRIPE_API_KEY` and `STRIPE_WEBHOOK_SECRET` in your platform dashboard.
5. Redeploy the web service.

**You are now live and charging real cards.**

---

## Step 11 (optional) — Add SERP API for live competitor pricing

Without this, the pricing agent uses heuristic pricing. With it, it monitors live competitor data.

1. **https://serpapi.com** → sign up (100 free searches/month).
2. Copy your API key.
3. Add to your platform env vars: `SERP_API_KEY=your_key`

---

## Full .env reference

```bash
# ── REQUIRED ──────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-...
SECRET_KEY=                          # generate: python -c "import secrets; print(secrets.token_hex(32))"
STORE_NAME=Vendo's Deals
STORE_URL=https://yourdomain.com

# ── DATABASE ───────────────────────────────────────────────────────
# Default SQLite is fine. For Postgres (recommended at scale):
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
DATABASE_URL=sqlite+aiosqlite:///./dropshipping.db

# ── PAYMENTS ───────────────────────────────────────────────────────
STRIPE_API_KEY=sk_live_...           # use sk_test_... while testing
STRIPE_WEBHOOK_SECRET=whsec_...

# ── SUPPLIER — AliExpress (optional; product sourcing only) ────────
# Without these, product search uses mock data. Fulfilment is manual either way.
ALIEXPRESS_APP_KEY=...
ALIEXPRESS_APP_SECRET=...

# ── EMAIL ──────────────────────────────────────────────────────────
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USER=resend
SMTP_PASSWORD=re_...
FROM_EMAIL=orders@yourdomain.com

# ── OPTIONAL ───────────────────────────────────────────────────────
SERP_API_KEY=...                     # competitor pricing searches (serpapi.com)

# ── AGENT MODELS (defaults are sensible — only change if needed) ───
PRODUCT_AGENT_MODEL=claude-opus-4-8
PRICING_AGENT_MODEL=claude-sonnet-4-6
ORDERING_AGENT_MODEL=claude-sonnet-4-6
WEBSITE_AGENT_MODEL=claude-sonnet-4-6
MANAGER_AGENT_MODEL=claude-opus-4-8
TRAINING_AGENT_MODEL=claude-opus-4-8

# ── AGENT INTERVALS (seconds — override if needed) ─────────────────
# PRODUCT_AGENT_INTERVAL=3600
# PRICING_AGENT_INTERVAL=1800
# ORDERING_AGENT_INTERVAL=300
# WEBSITE_AGENT_INTERVAL=7200
# MANAGER_AGENT_INTERVAL=14400
# IMAGE_VALIDATION_AGENT_INTERVAL=600
# TRAINING_AGENT_INTERVAL=28800
```

---

## Agent schedule

| Agent | Interval | Model | What it does |
|---|---|---|---|
| Training / Consultant | Every 8 hrs | Opus 4.8 | Studies top e-commerce sites, generates coaching for all other agents, self-improves each cycle |
| Product Hunting | Every 60 min | Opus 4.8 | Discovers trending products, updates catalog, discontinues underperformers |
| Pricing | Every 30 min | Sonnet 4.6 | Monitors competitor prices, applies psychological pricing, protects margins |
| Ordering | Every 5 min | Sonnet 4.6 | Queues paid orders for manual AliExpress fulfilment, records tracking, sends customer updates |
| Website Maintenance | Every 2 hrs | Sonnet 4.6 | Rewrites weak copy, fills SEO gaps, balances categories |
| Graphic Design | Every 2 hrs | Sonnet 4.6 | Maintains brand assets, mascot variants, promotional banners |
| Image Validation | Every 10 min | Sonnet 4.6 | Verifies product images match listings, replaces mismatches |
| Manager | Every 4 hrs | Opus 4.8 | Audits all agents, spawns new specialised agents as the business grows |

---

## Running the agents

If your platform starts agents automatically (Render worker, Railway worker, Docker CMD) — they're already running after deploy.

To run manually:
```bash
python orchestrator.py           # agents only
python orchestrator.py --store   # agents + store server
python launch.py                 # one-shot go-live audit, then exit
```

---

## Cost estimates

| Service | Free tier | Paid tier |
|---|---|---|
| Anthropic API | — | ~$5–30/month (agent activity) |
| Render (web + worker) | 750 hrs/month | ~$14/month for two starter services |
| Render disk | — | $0.25/month (1 GB) |
| Stripe | Free | 2.9% + $0.30 per transaction |
| AliExpress | Free | Product cost + shipping, paid per order when you fulfil |
| Resend email | 3,000/month free | $20/month for 50K |
| Domain | — | ~$10–15/year |
| **Total (running)** | | **~$20–45/month** |

---

## Troubleshooting

**Store shows no products**
```bash
python -m scripts.seed
```

**Orders stuck in PENDING** — Stripe keys missing or webhook not configured. Revisit Step 3.

**Orders stuck in ORDERED_FROM_SUPPLIER** — this is expected: fulfilment is manual. Place
the order on AliExpress, then record the tracking number on the order. The ordering agent
moves it to `shipped` once tracking is present. (See Step 4b.)

**Product search returns generic/mock products** — add `ALIEXPRESS_APP_KEY` /
`ALIEXPRESS_APP_SECRET` for live AliExpress data. (Optional — Step 4a.)

**Emails not sending** — Test SMTP directly:
```bash
python -c "
import smtplib, os
s = smtplib.SMTP_SSL('smtp.resend.com', 465)
s.login('resend', os.environ['SMTP_PASSWORD'])
print('SMTP OK')
"
```

**Check agent activity**
```bash
python -c "
import asyncio, sys
sys.path.insert(0, '.')
from database import AsyncSessionLocal, AgentLog
from sqlalchemy import select
async def t():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(AgentLog).order_by(AgentLog.created_at.desc()).limit(20)
        )).scalars().all()
        for r in rows:
            print(r.created_at.strftime('%H:%M'), r.agent_name.ljust(22),
                  r.status.ljust(8), f'{r.tokens_used or 0:>6} tok |', r.result[:80])
asyncio.run(t())
"
```

**Run a fresh readiness audit**
```bash
python launch.py
```
