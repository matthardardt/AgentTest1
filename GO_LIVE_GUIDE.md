# Go-Live Guide

Everything you need to take this from `code_ready` → `revenue_live`.
All commands are copy-paste exact. Do them in order.

---

## Where you stand right now

| | Status | Notes |
|---|---|---|
| Code & store | ✅ Built and smoke-tested | Full FastAPI store + 8 agents |
| Deployment artifacts | ✅ Dockerfile, Render, Fly, Procfile | Render now uses shared PostgreSQL |
| Legal pages | ✅ Privacy, Terms, Refund, Shipping | At `/pages/privacy` etc. |
| Anthropic API key | ✅ Set | Powers all agents |
| Stripe integration | ✅ Code complete | Needs your Stripe account + keys (Step 2) |
| Supplier (fulfilment) | ❌ Needs account + keys | CJ Dropshipping (Step 3) |
| Email (notifications) | ❌ Needs SMTP credentials | Resend or Gmail (Step 4) |
| Deployed to internet | ❌ Not yet | Choose platform (Step 5) |
| Domain | ❌ Not yet | Optional but recommended (Step 6) |

---

## Step 1 — Generate a secure secret key

Run this once locally, keep the output:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

You'll get something like `a3f8d2e1c9b4...`. Save it for any platform that doesn't auto-generate it.

> **Render auto-generates this** — the `render.yaml` already has `generateValue: true` for `SECRET_KEY`, so you can skip this step if you're deploying to Render.

---

## Step 2 — Set up Stripe (payments)

### 2a. Create account
1. Go to **https://dashboard.stripe.com/register**
2. Enter your email, name, country, and set a password.
3. Verify your email.
4. Complete the business profile.

### 2b. Get your API keys
1. In the Stripe dashboard, click **Developers** (top right) → **API keys**.
2. You need **two** keys:
   - **Publishable key** — starts with `pk_test_...` (test) or `pk_live_...`. This is `STRIPE_PUBLISHABLE_KEY`. It's safe to expose to browsers.
   - **Secret key** — starts with `sk_test_...` or `sk_live_...`. This is `STRIPE_API_KEY`. **Never expose this to browsers.**
3. Start with `pk_test_...` / `sk_test_...` while testing; swap for live keys when ready to charge real cards.

### 2c. Set up a webhook
Stripe sends your server a webhook event when a payment succeeds. Without this, orders won't auto-confirm.

1. Stripe dashboard → **Developers** → **Webhooks** → **Add endpoint**.
2. Endpoint URL: `https://yourdomain.com/api/orders/webhook/stripe` (fill in your real domain once deployed — come back after Step 5).
3. Events to listen for: select **`payment_intent.succeeded`**.
4. Click **Add endpoint**.
5. On the webhook detail page, reveal and copy the **Signing secret** (starts with `whsec_...`). This is `STRIPE_WEBHOOK_SECRET`.

### 2d. Add to your .env

```
STRIPE_API_KEY=sk_test_xxxxxxxxxxxxxxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_test_xxxxxxxxxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxx
```

---

## Step 3 — Set up CJ Dropshipping (fulfilment)

CJ Dropshipping is the primary supplier integration built into the ordering agent.

### 3a. Create account
1. Go to **https://app.cjdropshipping.com**
2. Click **Sign Up** — use your business email.
3. Verify your email address.
4. Complete your account profile (name, address — required to place orders).

### 3b. Get your API key
1. Log in → click your avatar (top right) → **API**.
2. Click **Get API Key** (or it may already be shown).
3. Copy the **API Key** value. This is `CJDROPSHIPPING_API_KEY`.
4. The email you registered with is `CJDROPSHIPPING_EMAIL`.

### 3c. Fund your CJ wallet (required to place real orders)
CJ Dropshipping requires a prepaid wallet balance to place supplier orders.
1. Dashboard → **Wallet** → **Recharge**.
2. Add at least $50–$100 to start (you can top up anytime).

### 3d. Add to your .env

```
CJDROPSHIPPING_API_KEY=your_cj_api_key_here
CJDROPSHIPPING_EMAIL=your@email.com
```

---

## Step 4 — Set up email notifications (SMTP)

Customers receive order confirmation and shipping update emails. The easiest option is **Resend** (free tier: 3,000 emails/month) or Gmail.

### Option A — Resend (recommended, free)
1. Go to **https://resend.com** → Sign up.
2. Dashboard → **API Keys** → **Create API Key** → copy it.
3. Dashboard → **Domains** → **Add Domain** → verify DNS records for your domain. Or use the Resend shared domain for testing.
4. SMTP settings for Resend:

```
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USER=resend
SMTP_PASSWORD=re_xxxxxxxxxxxxxxxxxxxx   ← your API key
FROM_EMAIL=orders@yourdomain.com
```

### Option B — Gmail (quick for testing)
1. Google Account → **Security** → **2-Step Verification** (must be enabled).
2. Google Account → **Security** → **App passwords** → generate one for "Mail".
3. Use the 16-character app password:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx   ← the 16-char app password (no spaces)
FROM_EMAIL=your@gmail.com
```

---

## Step 5 — Deploy the app

Pick **one** platform. Render is the easiest for a first deployment.

---

### Option A — Render (recommended, ~$21/month)

Render reads `render.yaml` from the repo and provisions everything automatically: a web service, a background worker, and a **shared PostgreSQL database** so both services see the same data.

**One-time setup:**

1. Go to **https://render.com** → sign up with GitHub.
2. Dashboard → **New** → **Blueprint**.
3. Connect your GitHub repo (`matthardardt/AgentTest1`).
4. Render reads `render.yaml` and shows you the services it will create:
   - `dropshop-db` (PostgreSQL, free tier)
   - `dropshop-store` (web)
   - `dropshop-agents` (worker)
5. Before clicking **Apply**, fill in the secret environment variables. Click each service and add:

   For **dropshop-store** (web):
   | Key | Value |
   |---|---|
   | `ANTHROPIC_API_KEY` | `sk-ant-api03-...` |
   | `STRIPE_API_KEY` | from Step 2 — `sk_test_...` |
   | `STRIPE_PUBLISHABLE_KEY` | from Step 2 — `pk_test_...` |
   | `STRIPE_WEBHOOK_SECRET` | from Step 2 — `whsec_...` (set after deploy) |
   | `CJDROPSHIPPING_API_KEY` | from Step 3 |
   | `CJDROPSHIPPING_EMAIL` | from Step 3 |
   | `STORE_URL` | `https://dropshop-store.onrender.com` (your Render URL) |
   | `SMTP_HOST` | from Step 4 |
   | `SMTP_USER` | from Step 4 |
   | `SMTP_PASSWORD` | from Step 4 |
   | `FROM_EMAIL` | from Step 4 |

   For **dropshop-agents** (worker):
   | Key | Value |
   |---|---|
   | `ANTHROPIC_API_KEY` | same as above |
   | `CJDROPSHIPPING_API_KEY` | from Step 3 |
   | `CJDROPSHIPPING_EMAIL` | from Step 3 |

   > `SECRET_KEY` and `DATABASE_URL` are auto-managed — no action needed.

6. Click **Apply** — Render builds and deploys (~3 minutes).
7. Your store URL will be something like `https://dropshop-store.onrender.com`.

**After deploy:** seed the catalog if the DB is empty:

```bash
# In Render dashboard → dropshop-store → Shell
python -m scripts.seed
# OR use the one-click endpoint:
curl "https://dropshop-store.onrender.com/api/admin/seed?key=YOUR_SECRET_KEY"
```

> **Free PostgreSQL note:** Render's free Postgres tier expires after 90 days. Before expiry, upgrade to the Starter plan ($7/month) in the Render dashboard → your database → Settings → Change Plan.

---

### Option B — Fly.io (~$5–10/month)

```bash
# Install flyctl: https://fly.io/docs/getting-started/installing-flyctl/
fly auth login

# From the repo root:
fly launch --no-deploy        # reads fly.toml, creates the app
fly volumes create dropdata --region iad --size 1

fly secrets set \
  ANTHROPIC_API_KEY="sk-ant-api03-..." \
  STRIPE_API_KEY="sk_test_..." \
  STRIPE_PUBLISHABLE_KEY="pk_test_..." \
  STRIPE_WEBHOOK_SECRET="whsec_..." \
  CJDROPSHIPPING_API_KEY="..." \
  CJDROPSHIPPING_EMAIL="your@email.com" \
  SECRET_KEY="your-32-char-random-string" \
  SMTP_HOST="smtp.resend.com" \
  SMTP_PORT="465" \
  SMTP_USER="resend" \
  SMTP_PASSWORD="re_..." \
  FROM_EMAIL="orders@yourdomain.com" \
  STORE_NAME="MyDropShop" \
  STORE_URL="https://dropshop.fly.dev"

fly deploy
```

App URL: `https://dropshop.fly.dev` (or your chosen app name).

> **Note:** Fly.io runs only the web service from `fly.toml`. To also run the agents, you can either add a second `fly launch` for the worker, or run both together with `python orchestrator.py --store` as the start command (change `fly.toml` accordingly).

---

### Option C — Docker on a VPS (DigitalOcean, Hetzner, etc.)

**On your local machine** — create a production `.env`:

```bash
cp .env.example .env
# Fill in all values from steps 1-4
nano .env
```

**On the VPS** (Ubuntu 22.04 example):

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Copy your repo and .env to the server
scp -r . user@your-server-ip:/app/dropshop
scp .env user@your-server-ip:/app/dropshop/.env

# SSH in and start
ssh user@your-server-ip
cd /app/dropshop
docker compose up -d --build
```

Store runs at `http://your-server-ip:8000`.

---

### Option D — Railway

1. **https://railway.app** → New Project → Deploy from GitHub repo.
2. Railway reads `Procfile` → creates a `web` dyno and a `worker` dyno.
3. Add all env vars in the Railway dashboard under **Variables**.
4. Railway assigns a URL like `https://dropshop.up.railway.app`.

> Railway's `Procfile` runs both processes from the same repo. You'll also need to add a PostgreSQL plugin in the Railway dashboard and connect it via `DATABASE_URL`.

---

## Step 6 — Point a custom domain

Once the app is deployed and you have a public URL, add your domain.

### Buy a domain (if you don't have one)
- **Namecheap**: https://namecheap.com (~$10–15/year for .com)
- **Cloudflare Registrar**: https://cloudflare.com (at-cost pricing, no markup)

### Add domain to Render
1. Render dashboard → `dropshop-store` → **Settings** → **Custom Domains** → **Add Domain**.
2. Enter your domain (e.g. `shop.yourdomain.com` or `yourdomain.com`).
3. Render gives you a CNAME value (e.g. `dropshop-store.onrender.com`).

### Point DNS
In your domain registrar's DNS settings:

| Type | Name | Value |
|---|---|---|
| `CNAME` | `shop` (or `@` for root) | `dropshop-store.onrender.com` |

DNS propagates in 5–30 minutes. Render provisions a free SSL certificate automatically once DNS resolves.

### Update STORE_URL
Once the domain is live, update `STORE_URL` in your platform's env vars:

```
STORE_URL=https://shop.yourdomain.com
```

Redeploy the web service for the change to take effect.

---

## Step 7 — Update the Stripe webhook URL

Now that you have a real domain, go back to Stripe and update the webhook:

1. Stripe dashboard → **Developers** → **Webhooks** → click your endpoint.
2. Click **Update endpoint**.
3. Change the URL to `https://shop.yourdomain.com/api/orders/webhook/stripe`.
4. Save.

If you skipped creating the webhook in Step 2c, create it now with the real URL.

---

## Step 8 — Verify everything is working

Run through this checklist after deploy:

```
[ ] https://shop.yourdomain.com/health  →  {"status":"ok","store":"MyDropShop"}
[ ] Homepage loads with products
[ ] Click a product → product page loads
[ ] Add to cart → cart shows correct total
[ ] Stripe test checkout:
      card: 4242 4242 4242 4242
      exp:  any future date
      CVC:  any 3 digits
      → Stripe card element appears, payment processes, order confirmation page shows
[ ] Check Stripe dashboard → Payments → test charge is there
[ ] Check order status in DB → should be PAID (set by webhook)
[ ] Legal pages load:
      /pages/privacy
      /pages/terms
      /pages/refund
      /pages/shipping
[ ] Agents are running (check /api/admin/logs or orchestrator logs)
```

---

## Step 9 — Switch Stripe to live mode

When you're satisfied everything works on test cards:

1. Stripe dashboard → toggle **Test mode → Live mode** (top left).
2. **Developers → API Keys** → reveal and copy the **live** secret key (`sk_live_...`) and publishable key (`pk_live_...`).
3. **Developers → Webhooks** → create a new webhook for live mode (same URL as before). Copy the new `whsec_...` signing secret.
4. Update `STRIPE_API_KEY`, `STRIPE_PUBLISHABLE_KEY`, and `STRIPE_WEBHOOK_SECRET` in your platform dashboard with the live values.
5. Redeploy the web service.

**Now real cards will be charged.**

---

## Step 10 — Optional: SERP API for competitor pricing

The pricing agent can monitor competitor prices automatically with a search API key.

1. Go to **https://serpapi.com** → sign up (free tier: 100 searches/month).
2. Dashboard → **API Key** → copy it.
3. Add to your platform env vars: `SERP_API_KEY=your_key_here`.

Without this, the pricing agent still works but uses heuristic pricing instead of live competitor data.

---

## Step 11 — Start the agents

If your platform starts agents automatically (Render worker / Railway worker / Docker CMD), this is already running. Otherwise, to start manually:

```bash
# Agents only (no store server)
python orchestrator.py

# Agents + store server together
python orchestrator.py --store

# One-shot go-live audit (run readiness check again)
python launch.py
```

Agent schedule (all configurable in `.env`):

| Agent | Default interval | What it does |
|---|---|---|
| Product Hunting | Every 60 min | Finds new trending products, updates catalog |
| Pricing | Every 30 min | Adjusts prices to stay competitive |
| Ordering | Every 5 min | Picks up PAID orders, places with supplier, tracks shipping |
| Website Maintenance | Every 2 hrs | Reviews and updates store content |
| Image Validation | Every 10 min | Verifies product images match listings |
| Graphic Design | Every 2 hrs | Creates/updates branded visuals |
| Manager | Every 4 hrs | Audits all agents, spawns new ones as needed |

---

## Full .env reference (production)

```bash
# ── REQUIRED ──────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-...       # from console.anthropic.com
SECRET_KEY=a3f8d2e1c9b4...              # from: python -c "import secrets; print(secrets.token_hex(32))"
STORE_NAME=Your Store Name
STORE_URL=https://shop.yourdomain.com

# ── DATABASE ───────────────────────────────────────────
# Leave as-is for SQLite (local/Docker). For Postgres (Render/Railway):
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
# Render auto-sets this; postgres:// URLs are normalised to postgresql+asyncpg:// automatically.
DATABASE_URL=sqlite+aiosqlite:///./dropshipping.db

# ── PAYMENTS ───────────────────────────────────────────
STRIPE_API_KEY=sk_live_...              # sk_test_... while testing — NEVER send to browser
STRIPE_PUBLISHABLE_KEY=pk_live_...      # pk_test_... while testing — safe to expose to browser
STRIPE_WEBHOOK_SECRET=whsec_...

# ── SUPPLIER ───────────────────────────────────────────
CJDROPSHIPPING_API_KEY=...
CJDROPSHIPPING_EMAIL=your@email.com

# ── EMAIL ──────────────────────────────────────────────
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USER=resend
SMTP_PASSWORD=re_...
FROM_EMAIL=orders@yourdomain.com

# ── OPTIONAL ───────────────────────────────────────────
SERP_API_KEY=...                        # competitor pricing searches

# ── AGENT MODELS (defaults are fine) ──────────────────
PRODUCT_AGENT_MODEL=claude-opus-4-8
PRICING_AGENT_MODEL=claude-sonnet-4-6
ORDERING_AGENT_MODEL=claude-sonnet-4-6
WEBSITE_AGENT_MODEL=claude-sonnet-4-6
MANAGER_AGENT_MODEL=claude-opus-4-8
```

---

## Estimated costs

| Service | Free tier | Paid |
|---|---|---|
| Anthropic API | — | ~$5–30/month depending on agent activity |
| Render (web + worker) | 750 hrs/month free | $14/month for two starter services |
| Render PostgreSQL | Free (90-day expiry) | $7/month starter after expiry |
| Stripe | Free | 2.9% + 30¢ per transaction |
| CJ Dropshipping | Free account | Wallet balance consumed per order |
| Resend (email) | 3,000/month free | $20/month for 50K |
| Domain | — | ~$10–15/year |
| **Total to launch** | **$0 (test mode)** | **~$27–52/month running** |

---

## Troubleshooting

**Store not showing products**
```bash
python -m scripts.seed    # seed the catalog
# OR hit the API endpoint:
curl "https://yourstore.com/api/admin/seed?key=YOUR_SECRET_KEY"
```

**Stripe card element not showing**
- Make sure `STRIPE_PUBLISHABLE_KEY` (not the secret key) is set correctly.
- Check browser console for JS errors.

**Orders stuck as PENDING after payment**
- Stripe webhook not configured or wrong endpoint URL.
- Check: Stripe dashboard → Developers → Webhooks → recent deliveries.
- Webhook URL must be `https://yourstore.com/api/orders/webhook/stripe`.

**Supplier orders not being placed**
- CJ Dropshipping keys not set, or wallet balance is zero. Check Step 3.
- Orders must be in `PAID` status for the ordering agent to pick them up.

**Emails not sending**
- Check SMTP credentials. Test with:
```bash
python -c "
import smtplib, os
s = smtplib.SMTP_SSL('smtp.resend.com', 465)
s.login('resend', os.environ['SMTP_PASSWORD'])
s.sendmail('test@example.com', 'test@example.com', 'Subject: test\n\ntest')
print('OK')
"
```

**Render: web and worker seeing different data**
- This shouldn't happen with the new `render.yaml` (both use the shared PostgreSQL).
- If you deployed the old SQLite config, delete both services and re-deploy using Blueprint.

**Agent logs**
```bash
# View last 20 agent runs
python -c "
import asyncio
from database import AsyncSessionLocal, AgentLog
from sqlalchemy import select
async def t():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AgentLog).order_by(AgentLog.created_at.desc()).limit(20))).scalars().all()
        for r in rows: print(r.created_at, r.agent_name, r.status, r.tokens_used, 'tok |', r.result[:100])
asyncio.run(t())
"
```

**Check current readiness status**
```bash
python launch.py
```
