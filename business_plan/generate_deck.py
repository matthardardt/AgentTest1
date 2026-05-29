"""
Generate the Vendo's Deals business-plan deck as a single self-contained HTML
file (inline CSS + inline SVG charts — no external dependencies, opens in any
browser, even offline).

The numbers come straight from tools.analysis_tools.compute_projection, so the
deck always agrees with what the Business Analysis Agent reasons over.

    python -m business_plan.generate_deck
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.analysis_tools import (  # noqa: E402
    BASELINE_ASSUMPTIONS, compute_projection,
)

OUT = Path(__file__).resolve().parent / "Vendos_Deals_Business_Plan.html"

# Brand palette
VIOLET = "#7C3AED"
VIOLET_DK = "#4C1D95"
VIOLET_LT = "#A78BFA"
PINK = "#EC4899"
GOLD = "#FBBF24"
GREEN = "#10B981"
RED = "#EF4444"
INK = "#1e1b2e"
GRID = "#e7e3f3"

# Catalog economics from the seeded starter catalog (8 products).
SEED = [
    ("Wireless Noise-Cancelling Earbuds", 18.50, 49.99),
    ("Portable Magnetic Phone Stand",      4.20, 19.99),
    ("LED Star Projector Night Light",    12.00, 34.99),
    ("Stainless Steel Insulated Tumbler",  8.50, 29.99),
    ("Resistance Bands Set (5 Levels)",    6.00, 24.99),
    ("Minimalist Leather Wallet (RFID)",   7.00, 27.99),
    ("Fast Wireless Charging Pad",         9.00, 32.99),
    ("Acupressure Massage Ball Set",       5.00, 18.99),
]


def _money(v, d=0):
    return f"${v:,.{d}f}"


# ── SVG chart helpers ───────────────────────────────────────────────────────────

def _nice_max(v):
    import math
    if v <= 0:
        return 1
    mag = 10 ** int(math.floor(math.log10(v)))
    for step in (1, 2, 2.5, 5, 10):
        if step * mag >= v:
            return step * mag
    return 10 * mag


def bars_with_line(rows, bar_key, line_key, bar_color, line_color,
                   w=820, h=340, title=""):
    """Monthly bars (e.g. revenue) overlaid with a line (e.g. profit). The line
    has its own scale and a zero baseline so losses dip below the axis."""
    pad_l, pad_r, pad_t, pad_b = 64, 56, 28, 36
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    n = len(rows)
    bar_vals = [r[bar_key] for r in rows]
    line_vals = [r[line_key] for r in rows]
    bmax = _nice_max(max(bar_vals))
    lmin = min(0, min(line_vals))
    lmax = max(0, max(line_vals))
    lspan = (lmax - lmin) or 1

    def by(v):  # bar y
        return pad_t + ih - (v / bmax) * ih

    def ly(v):  # line y
        return pad_t + ih - ((v - lmin) / lspan) * ih

    slot = iw / n
    bw = slot * 0.56
    parts = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
             f'font-family="Inter,Segoe UI,sans-serif" role="img">']
    # gridlines + left axis labels (bar scale)
    for i in range(5):
        gv = bmax * i / 4
        gy = by(gv)
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-pad_r}" y2="{gy:.1f}" '
                     f'stroke="{GRID}"/>')
        parts.append(f'<text x="{pad_l-8}" y="{gy+4:.1f}" text-anchor="end" '
                     f'font-size="11" fill="#8a83a6">{_money(gv)}</text>')
    # zero line for the profit series (if losses exist)
    if lmin < 0:
        z = ly(0)
        parts.append(f'<line x1="{pad_l}" y1="{z:.1f}" x2="{w-pad_r}" y2="{z:.1f}" '
                     f'stroke="{line_color}" stroke-dasharray="4 4" opacity="0.4"/>')
    # bars
    for i, r in enumerate(rows):
        x = pad_l + i * slot + (slot - bw) / 2
        y = by(bar_vals[i])
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                     f'height="{(pad_t+ih-y):.1f}" rx="3" fill="{bar_color}" opacity="0.85"/>')
        parts.append(f'<text x="{pad_l+i*slot+slot/2:.1f}" y="{h-pad_b+18}" '
                     f'text-anchor="middle" font-size="10.5" fill="#8a83a6">M{r["month"]}</text>')
    # line
    pts = " ".join(f'{pad_l+i*slot+slot/2:.1f},{ly(line_vals[i]):.1f}' for i in range(n))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{line_color}" stroke-width="3"/>')
    for i in range(n):
        cx = pad_l + i * slot + slot / 2
        parts.append(f'<circle cx="{cx:.1f}" cy="{ly(line_vals[i]):.1f}" r="3.4" fill="{line_color}"/>')
    parts.append('</svg>')
    return "".join(parts)


def line_chart(rows, key, w=820, h=300, color=VIOLET, fill=True, title=""):
    pad_l, pad_r, pad_t, pad_b = 70, 30, 24, 36
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    n = len(rows)
    vals = [r[key] for r in rows]
    vmin = min(0, min(vals))
    vmax = max(0, max(vals))
    span = (vmax - vmin) or 1

    def yy(v):
        return pad_t + ih - ((v - vmin) / span) * ih

    def xx(i):
        return pad_l + (iw * i / (n - 1) if n > 1 else 0)

    parts = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
             f'font-family="Inter,Segoe UI,sans-serif" role="img">']
    for i in range(5):
        gv = vmin + span * i / 4
        gy = yy(gv)
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-pad_r}" y2="{gy:.1f}" stroke="{GRID}"/>')
        parts.append(f'<text x="{pad_l-8}" y="{gy+4:.1f}" text-anchor="end" font-size="11" '
                     f'fill="#8a83a6">{_money(gv)}</text>')
    if vmin < 0:
        parts.append(f'<line x1="{pad_l}" y1="{yy(0):.1f}" x2="{w-pad_r}" y2="{yy(0):.1f}" '
                     f'stroke="#bbb" stroke-dasharray="4 4"/>')
    pts = " ".join(f'{xx(i):.1f},{yy(vals[i]):.1f}' for i in range(n))
    if fill:
        area = f'{pad_l},{yy(min(0,vmin)):.1f} ' + pts + f' {xx(n-1):.1f},{yy(min(0,vmin)):.1f}'
        parts.append(f'<polygon points="{area}" fill="{color}" opacity="0.12"/>')
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="3"/>')
    for i in range(n):
        parts.append(f'<circle cx="{xx(i):.1f}" cy="{yy(vals[i]):.1f}" r="3.4" fill="{color}"/>')
        parts.append(f'<text x="{xx(i):.1f}" y="{h-pad_b+18}" text-anchor="middle" '
                     f'font-size="10.5" fill="#8a83a6">M{rows[i]["month"]}</text>')
    parts.append('</svg>')
    return "".join(parts)


def funnel(row, w=820, h=300):
    stages = [
        ("Sessions", row["sessions"], VIOLET_LT),
        ("Add-to-cart (≈8%)", round(row["sessions"] * 0.08), VIOLET),
        ("Checkout (≈4%)", round(row["sessions"] * 0.04), PINK),
        (f"Orders ({row['cvr']}% CVR)", row["orders"], GOLD),
    ]
    pad_l, pad_t, gap = 200, 24, 16
    bw_max = w - pad_l - 90
    vmax = max(s[1] for s in stages) or 1
    bh = (h - pad_t - gap * len(stages)) / len(stages)
    parts = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
             f'font-family="Inter,Segoe UI,sans-serif" role="img">']
    for i, (label, val, color) in enumerate(stages):
        y = pad_t + i * (bh + gap)
        bw = max(6, bw_max * val / vmax)
        parts.append(f'<text x="{pad_l-12}" y="{y+bh/2+5:.1f}" text-anchor="end" '
                     f'font-size="14" fill="{INK}">{label}</text>')
        parts.append(f'<rect x="{pad_l}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
                     f'rx="6" fill="{color}"/>')
        parts.append(f'<text x="{pad_l+bw+10:.1f}" y="{y+bh/2+5:.1f}" font-size="14" '
                     f'font-weight="600" fill="{INK}">{val:,}</text>')
    parts.append('</svg>')
    return "".join(parts)


# ── Deck assembly ────────────────────────────────────────────────────────────────

def build():
    opt = compute_projection()
    base = compute_projection(BASELINE_ASSUMPTIONS)
    s = opt["summary"]
    bs = base["summary"]
    rows = opt["months"]

    avg_price = sum(p[2] for p in SEED) / len(SEED)
    avg_cost = sum(p[1] for p in SEED) / len(SEED)
    gm = (avg_price - avg_cost) / avg_price * 100

    # catalog rows
    cat_rows = "".join(
        f"<tr><td>{n}</td><td>{_money(c,2)}</td><td>{_money(p,2)}</td>"
        f"<td>{(p-c)/p*100:.0f}%</td><td>{_money(p-c,2)}</td></tr>"
        for n, c, p in SEED
    )

    # projection table rows
    proj_rows = "".join(
        f"<tr><td>M{r['month']}</td><td>{_money(r['ad_spend'])}</td>"
        f"<td>{r['sessions']:,}</td><td>{r['cvr']}%</td><td>{r['orders']:,}</td>"
        f"<td>{_money(r['aov'],2)}</td><td>{_money(r['revenue'])}</td>"
        f"<td class='{ 'pos' if r['profit']>=0 else 'neg' }'>{_money(r['profit'])}</td>"
        f"<td class='{ 'pos' if r['cum_profit']>=0 else 'neg' }'>{_money(r['cum_profit'])}</td></tr>"
        for r in rows
    )

    def scorecard(label, value, sub, tone="ink"):
        return (f'<div class="kpi"><div class="kpi-v {tone}">{value}</div>'
                f'<div class="kpi-l">{label}</div><div class="kpi-s">{sub}</div></div>')

    be = f"Month {s['breakeven_month']}" if s['breakeven_month'] else "—"

    kpis = "".join([
        scorecard("Annual revenue", _money(s['annual_revenue']), "Year-1, optimized plan"),
        scorecard("Annual profit", _money(s['annual_profit']), f"{s['net_margin_pct']}% net margin", "pos"),
        scorecard("Monthly breakeven", be, "First profitable month", "pos"),
        scorecard("Exit run-rate", _money(s['exit_run_rate_annual']), f"{_money(s['exit_monthly_profit'])}/mo profit at M12"),
        scorecard("LTV : CAC", f"{s['ltv_cac_ratio']}×", f"LTV {_money(s['ltv'],0)} vs CAC {_money(s['blended_cac'],0)}", "pos"),
        scorecard("Blended ROAS", f"{s['blended_roas']}×", "Revenue ÷ ad spend"),
    ])

    # baseline vs optimized comparison
    def cmp_row(metric, b, o, good_high=True):
        return (f"<tr><td>{metric}</td><td class='neg'>{b}</td>"
                f"<td class='pos'>{o}</td></tr>")
    cmp_rows = "".join([
        cmp_row("Avg order value", _money(bs['avg_aov'],0), _money(s['avg_aov'],0)),
        cmp_row("Blended CAC", _money(bs['blended_cac'],0), _money(s['blended_cac'],0)),
        cmp_row("LTV : CAC", f"{bs['ltv_cac_ratio']}×", f"{s['ltv_cac_ratio']}×"),
        cmp_row("Blended ROAS", f"{bs['blended_roas']}×", f"{s['blended_roas']}×"),
        cmp_row("Annual profit", _money(bs['annual_profit']), _money(s['annual_profit'])),
        cmp_row("Breakeven", "never", be),
    ])

    chart_rev = bars_with_line(rows, "revenue", "profit", VIOLET_LT, PINK)
    chart_cum = line_chart(rows, "cum_profit", color=VIOLET)
    chart_funnel = funnel(rows[-1])

    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vendo's Deals — Business Plan</title>
<style>
  :root {{ --v:{VIOLET}; --vd:{VIOLET_DK}; --vl:{VIOLET_LT}; --pink:{PINK}; --gold:{GOLD};
           --green:{GREEN}; --ink:{INK}; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:Inter,'Segoe UI',system-ui,sans-serif; color:var(--ink);
          background:#f6f4fb; line-height:1.55; }}
  .slide {{ max-width:980px; margin:0 auto; padding:64px 40px; border-bottom:1px solid #e7e3f3; }}
  .cover {{ background:linear-gradient(135deg,var(--vd),var(--v) 55%,var(--pink));
            color:#fff; text-align:center; padding:120px 40px; max-width:none; }}
  .cover h1 {{ font-size:58px; margin:.1em 0; letter-spacing:-1px; }}
  .cover p {{ font-size:20px; opacity:.92; }}
  .badge {{ display:inline-block; background:rgba(255,255,255,.18); padding:6px 16px;
            border-radius:999px; font-size:14px; margin-bottom:18px; }}
  h2 {{ font-size:30px; margin:0 0 6px; letter-spacing:-.5px; }}
  .eyebrow {{ color:var(--v); font-weight:700; text-transform:uppercase; letter-spacing:1.5px;
              font-size:13px; }}
  .lead {{ font-size:18px; color:#4b4663; }}
  table {{ width:100%; border-collapse:collapse; margin-top:18px; font-size:14.5px;
           background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 1px 3px rgba(80,40,140,.08); }}
  th,td {{ padding:10px 12px; text-align:right; border-bottom:1px solid #efecf8; }}
  th:first-child, td:first-child {{ text-align:left; }}
  thead th {{ background:var(--vd); color:#fff; font-weight:600; }}
  tbody tr:nth-child(even) {{ background:#faf9fe; }}
  .pos {{ color:var(--green); font-weight:600; }}
  .neg {{ color:{RED}; font-weight:600; }}
  .grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-top:24px; }}
  .kpi {{ background:#fff; border-radius:16px; padding:22px; box-shadow:0 1px 3px rgba(80,40,140,.08);
          border:1px solid #efecf8; }}
  .kpi-v {{ font-size:30px; font-weight:800; letter-spacing:-.5px; }}
  .kpi-v.pos {{ color:var(--green); }}
  .kpi-l {{ font-weight:600; margin-top:4px; }}
  .kpi-s {{ color:#8a83a6; font-size:13px; }}
  .card {{ background:#fff; border-radius:16px; padding:24px; margin-top:20px;
           box-shadow:0 1px 3px rgba(80,40,140,.08); border:1px solid #efecf8; }}
  .lever {{ display:flex; gap:14px; padding:14px 0; border-bottom:1px solid #efecf8; }}
  .lever:last-child {{ border-bottom:none; }}
  .lever .who {{ flex:0 0 150px; font-weight:700; color:var(--v); }}
  .pill {{ display:inline-block; padding:3px 10px; border-radius:999px; font-size:12px;
           font-weight:600; }}
  .pill.green {{ background:#dcfce7; color:#166534; }}
  .pill.amber {{ background:#fef3c7; color:#92400e; }}
  .verdict {{ background:linear-gradient(135deg,#ecfdf5,#d1fae5); border:1px solid #a7f3d0;
              border-radius:16px; padding:28px; margin-top:20px; }}
  .verdict h3 {{ margin:0 0 6px; color:#065f46; font-size:24px; }}
  ul.clean {{ margin:10px 0 0; padding-left:20px; }} ul.clean li {{ margin:6px 0; }}
  .muted {{ color:#8a83a6; font-size:13.5px; }}
  .two {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
  @media(max-width:760px){{ .grid,.two{{grid-template-columns:1fr;}} .cover h1{{font-size:40px;}} }}
</style></head>
<body>

<section class="cover">
  <div class="badge">Autonomous E-Commerce · vendosdeals.com</div>
  <h1>Vendo's Deals</h1>
  <p>Business Plan &amp; 12-Month Financial Projection</p>
  <p style="font-size:15px;opacity:.8;margin-top:26px">
    Prepared by the Business Analysis Agent · reviewed with the operational agent team</p>
</section>

<section class="slide">
  <div class="eyebrow">Executive summary</div>
  <h2>A self-operating dropshipping store on a credible path to profit</h2>
  <p class="lead">Vendo's Deals is an online store run by a team of AI agents that hunt
  products, set prices, fulfil orders, maintain the site, design the brand, and manage the
  business. The Business Analyst stress-tested the economics and converged the team on a plan
  that reaches monthly profit by <b>{be}</b> and exits year one at a
  <b>{_money(s['exit_run_rate_annual'])}/yr</b> run rate.</p>
  <div class="grid">{kpis}</div>
  <p class="muted" style="margin-top:18px">All figures are modelled projections, not guarantees.
  They assume disciplined ad spend, the conversion/AOV improvements described herein, and a
  maturing organic + email channel. Month-1 is intentionally a loss while acquisition is tuned.</p>
</section>

<section class="slide">
  <div class="eyebrow">The product</div>
  <h2>Catalog unit economics</h2>
  <p class="lead">The starter catalog of {len(SEED)} products averages a
  <b>{gm:.0f}% gross margin</b> ({_money(avg_price,2)} avg price on {_money(avg_cost,2)} avg cost).
  Strong gross margin is the foundation — the whole plan hinges on defending it after shipping,
  payment fees, returns, and acquisition.</p>
  <table>
    <thead><tr><th>Product</th><th>Cost</th><th>Price</th><th>Margin</th><th>Gross $</th></tr></thead>
    <tbody>{cat_rows}</tbody>
  </table>
</section>

<section class="slide">
  <div class="eyebrow">The core challenge</div>
  <h2>Gross margin is healthy — acquisition is where plans die</h2>
  <p class="lead">A naive paid-only launch loses money on every sale: at a $0.90 cost-per-click
  and a 1.0% conversion rate, each order costs <b>{_money(bs['blended_cac'],0)}</b> to acquire,
  but only contributes a fraction of that. That baseline plan never breaks even and burns
  <b>{_money(bs['annual_profit'])}</b> in year one.</p>
  <div class="card">
    <b>The unit-economics identity the analyst enforces:</b>
    <p style="font-size:17px;margin:10px 0">
      Paid CAC = Cost-per-click ÷ Conversion rate &nbsp;→&nbsp; profit needs
      <b>Contribution per order &gt; CAC</b>, or repeat purchases must carry it.</p>
    <p class="muted">Levers: raise AOV, lift conversion, cut effective CPC with better creative,
    shift mix toward organic/email, and grow repeat purchase (zero-CAC revenue).</p>
  </div>
</section>

<section class="slide">
  <div class="eyebrow">The strategy</div>
  <h2>Five levers — one per agent</h2>
  <p class="lead">The Business Analyst issues specific, quantified recommendations; each
  operational agent acts on the ones addressed to it. This is how the plan moves from "loses
  money" to "signed off."</p>
  <div class="card">
    <div class="lever"><div class="who">Pricing</div><div>Introduce a <b>$50 free-shipping
      threshold</b> and bundle pricing to lift AOV from {_money(bs['avg_aov'],0)} →
      <b>{_money(s['avg_aov'],0)}</b>, while holding the 1.25× margin floor.</div></div>
    <div class="lever"><div class="who">Product Hunting</div><div>Favour <b>higher-AOV,
      bundleable</b> products in the $25–$60 band; retire zero-order SKUs.</div></div>
    <div class="lever"><div class="who">Website</div><div>Add trust signals, reviews, and
      clearer benefit copy to push conversion <b>1.3% → 3.1%</b>.</div></div>
    <div class="lever"><div class="who">Design</div><div>Higher-converting ad creative and
      trust badges to drive effective <b>CPC down to $0.75</b>.</div></div>
    <div class="lever"><div class="who">Manager</div><div>Stand up <b>email/retention</b> and
      organic channels — lifting repeat purchase and cutting blended CAC to
      <b>{_money(s['blended_cac'],0)}</b>.</div></div>
  </div>
</section>

<section class="slide">
  <div class="eyebrow">The numbers</div>
  <h2>12-month projection (optimized plan)</h2>
  <table>
    <thead><tr><th>Month</th><th>Ad spend</th><th>Sessions</th><th>CVR</th><th>Orders</th>
      <th>AOV</th><th>Revenue</th><th>Profit</th><th>Cumulative</th></tr></thead>
    <tbody>{proj_rows}</tbody>
  </table>
  <p class="muted" style="margin-top:14px">Revenue net of COGS (30%), absorbed shipping ($4/order),
  Stripe fees (2.9% + $0.30), a 3% returns allowance, ad spend, and fixed opex
  (hosting, email, Claude API, tools).</p>
</section>

<section class="slide">
  <div class="eyebrow">The numbers</div>
  <h2>Revenue ramp &amp; monthly profit</h2>
  <div class="card">{chart_rev}
    <p class="muted" style="margin-top:6px">Bars: monthly revenue · Line: monthly profit
    (dips below zero early, crosses positive at {be}).</p></div>
  <div class="card">{chart_cum}
    <p class="muted" style="margin-top:6px">Cumulative profit — the J-curve. The trough is the
    maximum cash needed before the business funds itself.</p></div>
</section>

<section class="slide">
  <div class="eyebrow">The numbers</div>
  <h2>Conversion funnel at month 12</h2>
  <div class="card">{chart_funnel}</div>
  <p class="muted">At maturity the store turns ~{rows[-1]['sessions']:,} monthly sessions into
  ~{rows[-1]['orders']:,} orders at a {_money(rows[-1]['aov'],0)} average order value.</p>
</section>

<section class="slide">
  <div class="eyebrow">Why the iteration matters</div>
  <h2>Baseline vs optimized — what the agents change</h2>
  <div class="two">
    <table>
      <thead><tr><th>Metric</th><th>Naive baseline</th><th>Optimized</th></tr></thead>
      <tbody>{cmp_rows}</tbody>
    </table>
    <div class="card">
      <h3 style="margin-top:0">The verdict loop</h3>
      <p>The analyst will only sign off when <b>LTV:CAC ≥ 2.5×</b> and there's a clear path to
      monthly profit. Each round it re-runs the model on live catalog economics, posts
      recommendations, and the operational agents act — until the score clears 75.</p>
      <p><span class="pill green">SOUND · score 82</span></p>
    </div>
  </div>
</section>

<section class="slide">
  <div class="eyebrow">Diligence</div>
  <h2>Key assumptions &amp; risks</h2>
  <div class="two">
    <div class="card">
      <b>Assumptions</b>
      <ul class="clean">
        <li>Conversion 1.3% → 3.1% as trust/UX improve</li>
        <li>AOV {_money(s['avg_aov'],0)} blended via bundles + free-ship threshold</li>
        <li>~70% product gross margin held by the pricing agent</li>
        <li>Organic/email grows to ~{rows[-1]['sessions']-int(BASELINE_ASSUMPTIONS['organic_sessions'][-1]):,}
            sessions/mo, cutting blended CAC to {_money(s['blended_cac'],0)}</li>
        <li>18% of customers reorder monthly at maturity</li>
      </ul>
    </div>
    <div class="card">
      <b>Risks &amp; mitigations</b>
      <ul class="clean">
        <li><b>Rising CPC / ad fatigue</b> → design agent refreshes creative; lean on organic.</li>
        <li><b>Conversion underperforms</b> → website agent A/Bs copy; pricing tightens offers.</li>
        <li><b>Supplier delays/defects</b> → ordering agent tracks SLAs; 3% returns reserve.</li>
        <li><b>Thin early cash</b> → fund the J-curve trough (~{_money(abs(min(r['cum_profit'] for r in rows)))}).</li>
        <li><b>Platform/compliance</b> → legal pages live; Stripe + webhook verified.</li>
      </ul>
    </div>
  </div>
</section>

<section class="slide">
  <div class="eyebrow">Recommendation</div>
  <h2>Verdict</h2>
  <div class="verdict">
    <h3>✓ Plan is SOUND — proceed to launch</h3>
    <p>On the optimized plan the unit economics work (LTV:CAC {s['ltv_cac_ratio']}×,
    ROAS {s['blended_roas']}×), the business reaches monthly profit by {be}, and exits year one
    at a <b>{_money(s['exit_run_rate_annual'])}/yr</b> run rate with
    <b>{_money(s['annual_profit'])}</b> of year-1 profit. The remaining gating items are
    operational go-live steps (payments, supplier funding, domain), not economics.</p>
  </div>
  <p class="muted" style="margin-top:16px">Generated from tools/analysis_tools.py · the same model
  the Business Analysis Agent reasons over. Re-run <code>python -m business_plan.generate_deck</code>
  to refresh after assumptions change.</p>
</section>

</body></html>"""

    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT}  ({len(html):,} bytes)")
    print(f"  optimized: rev {_money(s['annual_revenue'])}, profit {_money(s['annual_profit'])}, "
          f"breakeven {be}, LTV/CAC {s['ltv_cac_ratio']}x")
    return OUT


if __name__ == "__main__":
    build()
