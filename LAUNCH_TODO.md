# 🚀 Vendo's Deals — Unified Launch Checklist

**One list. Everything left between here and taking real orders.**
Items marked ✅ are done (in code, this session). Items marked ⬜ need **you** — they
require accounts, secrets, money, or DNS that an agent can't create.

Last updated: 2026-05-29

---

## Where we stand

| | Status |
|---|---|
| Storefront code (catalog, cart, checkout, order pages) | ✅ Done |
| **Stripe Checkout + payment webhook** | ✅ **Built this session** (was missing) |
| Admin API authentication | ✅ Built this session |
| Supplier safety (no fake tracking in prod) | ✅ Built this session |
| Business Analysis agent + 12-mo projection + deck | ✅ Built this session |
| Render web service `vendos-deals` | ✅ Running ([vendos-deals.onrender.com](https://vendos-deals.onrender.com)) |
| Custom domain `vendosdeals.com` | ⬜ **Pending DNS verification** |
| Stripe keys + webhook configured | ⬜ You |
| Supplier (CJ) account + funds | ⬜ You |
| Email (SMTP/Resend) | ⬜ You |
| Agents actually running in prod | ⬜ Deploy decision needed (see §6) |

---

## ✅ What I changed this session (no action needed from you)

1. **Stripe Checkout** — `POST /api/orders/create-checkout-session` creates a PENDING
   order and a hosted Stripe Checkout session, returns the redirect URL. Checkout page
   now uses it. (Previously the checkout form couldn't actually charge anyone.)
2. **Stripe webhook** — `POST /api/orders/webhook/stripe` verifies the signature and
   flips the order to **PAID**, which is what the fulfillment agent watches for. (This
   endpoint was referenced in the old guide but didn't exist.)
3. **Security fix** — the checkout page was being handed your Stripe **secret** key.
   Removed; the hosted-checkout flow needs no key in the browser.
4. **Admin lockdown** — `/api/admin/stats|agents|logs|metrics` now require an
   `X-API-Key` header (defaults to `SECRET_KEY`). They were fully public.
5. **Supplier safety** — with `ALLOW_MOCK_SUPPLIERS=false`, agents refuse to "ship"
   orders without real CJ credentials instead of inventing fake tracking numbers.
6. **DB indexes** on the hot columns (order/product status, FKs, agent logs).
7. **Business Analysis Agent** + analysis tools + a consensus loop, wired into the
   orchestrator. The other agents now read recommendations addressed to them.
8. **Business plan deck** → `business_plan/Vendos_Deals_Business_Plan.html`.

---

## ⬜ YOUR remaining tasks (in order)

### 1. Finish the domain — *in progress*
- [ ] In **Cloudflare → DNS**, confirm two **CNAME** records (both **DNS-only / grey cloud**):
      `www → vendos-deals.onrender.com` and `@ → vendos-deals.onrender.com`.
- [ ] In **Render → Settings → Custom Domains**, click **Retry Verification** until both
      `vendosdeals.com` and `www.vendosdeals.com` show **Verified** + a green certificate.
- [ ] Once verified, set `STORE_URL=https://vendosdeals.com` in Render (used for Stripe
      success/return URLs). Already defaulted in `render.yaml`.

### 2. Payments — Stripe
- [ ] Create/confirm your Stripe account.
- [ ] Copy your **Secret key** → set `STRIPE_API_KEY` in Render (start with `sk_test_…`).
- [ ] Stripe → Developers → **Webhooks → Add endpoint**:
      - URL: `https://vendosdeals.com/api/orders/webhook/stripe`
      - Events: **`checkout.session.completed`** and **`payment_intent.succeeded`**
      - Copy the **Signing secret** (`whsec_…`) → set `STRIPE_WEBHOOK_SECRET` in Render.
- [ ] (Optional) set `STRIPE_PUBLISHABLE_KEY` (`pk_…`).
- [ ] Test with Stripe test card `4242 4242 4242 4242` → confirm the order flips to PAID.
- [ ] When happy, swap test keys for **live** keys (`sk_live_…`, new `whsec_…`).

### 3. Suppliers — CJ Dropshipping (so orders actually ship)
- [ ] Create a CJ Dropshipping account; fund the wallet.
- [ ] Set `CJDROPSHIPPING_API_KEY` and `CJDROPSHIPPING_EMAIL` in Render.
- [ ] Keep `ALLOW_MOCK_SUPPLIERS=false` in production (already set in `render.yaml`).
      Until real keys are in, the fulfillment agent will (correctly) refuse to ship.

### 4. Email — customer notifications
- [ ] Pick a sender (Resend, Gmail SMTP, etc.).
- [ ] Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `FROM_EMAIL` in Render.
      Without these, order/shipping emails are logged but not actually sent.

### 5. Secrets & config
- [ ] Set a strong `SECRET_KEY` (Render's blueprint auto-generates one).
- [ ] Set `ADMIN_API_KEY` to a separate random string (don't reuse `SECRET_KEY`).
- [ ] Confirm `ANTHROPIC_API_KEY` is set (powers every agent).

### 6. ⚠️ Deploy-topology decision (needed for the agents to run)
Right now only the **store** is live; the **agents aren't running in production**, and
the current `render.yaml` can't deploy as-is because the web service and the worker both
try to mount the **same 1 GB disk** — Render only allows one service per disk. Pick one:

- **Option A (simplest, recommended to start):** run store **and** agents in the one
  existing service. Change the Render **Start Command** to
  `python orchestrator.py --store`. One process, one disk, shared SQLite. Note: on the
  **Free** plan the service sleeps when idle, which pauses the agents — upgrade to
  **Starter** ($7/mo) for always-on agents.
- **Option B (scales better):** add a **Render PostgreSQL** instance, point both services
  at it via `DATABASE_URL`, and drop the shared disk. Lets the store and worker run
  separately. (Requires adding `asyncpg` to `requirements.txt`.)

→ Tell me which you want and I'll wire it up.

### 7. Seed & verify
- [ ] Seed the catalog once: visit `https://vendosdeals.com/api/admin/seed?key=YOUR_SECRET_KEY`
- [ ] Walk the go-live checklist in `DEPLOYMENT.md`: `/health` OK, homepage shows products,
      a test checkout creates a PAID order, legal pages reachable.

---

## Notes / known trade-offs
- **SQLite** is fine for launch but won't scale past one instance — see §6 Option B.
- The **Manager agent** can spawn new agents autonomously. Consider reviewing
  `/api/admin/agents` periodically (now behind `X-API-Key`).
- The financial projection in the deck is a **model**, not a guarantee — month 1 is a
  planned loss; breakeven is ~month 6 on the optimized plan.
