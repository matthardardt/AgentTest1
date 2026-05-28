# Deployment Guide

This project ships with artifacts for several platforms. Pick one.

## Prerequisites (all platforms)
1. Copy `.env.example` to `.env` and fill in:
   - `ANTHROPIC_API_KEY` (required — powers all agents)
   - `STRIPE_API_KEY` + `STRIPE_WEBHOOK_SECRET` (to take real payments)
   - `CJDROPSHIPPING_API_KEY` + `CJDROPSHIPPING_EMAIL` (to fulfill real orders)
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
fly secrets set ANTHROPIC_API_KEY=... STRIPE_API_KEY=... CJDROPSHIPPING_API_KEY=...
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
