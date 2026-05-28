"""
Design tools for the Graphic Design agent.

Manages SVG assets, brand CSS, and the visual identity of Vendo's Deals.
All file writes are sandboxed to store/static/img/ and store/static/css/.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from database import AsyncSessionLocal, BusinessMetric

REPO_ROOT    = Path(__file__).resolve().parent.parent
STATIC_IMG   = REPO_ROOT / "store" / "static" / "img"
STATIC_CSS   = REPO_ROOT / "store" / "static" / "css"
TEMPLATES_DIR = REPO_ROOT / "store" / "templates"

# Ensure directories exist
STATIC_IMG.mkdir(parents=True, exist_ok=True)
STATIC_CSS.mkdir(parents=True, exist_ok=True)


# ── Asset creation ─────────────────────────────────────────────────────────────

async def create_or_update_svg(
    filename: str,
    svg_content: str,
    description: str = "",
) -> dict[str, Any]:
    """
    Write or update an SVG file in store/static/img/.
    filename must be a plain filename (no path traversal).
    """
    safe_name = Path(filename).name
    if not safe_name.endswith(".svg"):
        safe_name += ".svg"
    if ".." in filename:
        return {"error": "Path traversal not allowed"}
    (STATIC_IMG / safe_name).write_text(svg_content)
    return {
        "success": True,
        "file": f"store/static/img/{safe_name}",
        "url": f"/static/img/{safe_name}",
        "bytes": len(svg_content),
        "description": description,
    }


async def create_promotional_banner(
    filename: str,
    heading: str,
    subtext: str = "",
    primary_color: str = "#7C3AED",
    accent_color: str = "#FBBF24",
    width: int = 1200,
    height: int = 400,
) -> dict[str, Any]:
    """Generate a hero/promotional banner SVG."""
    mid_y = height // 2
    font_size = max(28, min(72, width // max(len(heading), 1) + 8))
    subtext_block = (
        f'<text x="{width//2}" y="{mid_y + 52}" '
        f'font-family="\'Segoe UI\',\'Helvetica Neue\',Arial,sans-serif" '
        f'font-size="26" font-weight="400" fill="white" opacity="0.88" '
        f'text-anchor="middle" dominant-baseline="middle">{subtext}</text>'
        if subtext else ""
    )
    accent_y = mid_y + (86 if subtext else 46)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">\n'
        f'  <defs>\n'
        f'    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        f'      <stop offset="0%"   stop-color="{primary_color}"/>\n'
        f'      <stop offset="100%" stop-color="{primary_color}CC"/>\n'
        f'    </linearGradient>\n'
        f'    <filter id="blur"><feGaussianBlur stdDeviation="45"/></filter>\n'
        f'  </defs>\n'
        f'  <rect width="{width}" height="{height}" fill="url(#bg)"/>\n'
        f'  <circle cx="{int(width*0.85)}" cy="{int(height*0.2)}" r="220" '
        f'fill="{accent_color}" opacity="0.14" filter="url(#blur)"/>\n'
        f'  <circle cx="{int(width*0.1)}" cy="{int(height*0.88)}" r="180" '
        f'fill="white" opacity="0.07" filter="url(#blur)"/>\n'
        f'  <text x="{width//2}" y="{mid_y - (28 if subtext else 0)}" '
        f'font-family="\'Segoe UI\',\'Helvetica Neue\',Arial,sans-serif" '
        f'font-size="{font_size}" font-weight="800" fill="white" '
        f'text-anchor="middle" dominant-baseline="middle">{heading}</text>\n'
        f'  {subtext_block}\n'
        f'  <rect x="{width//2 - 40}" y="{accent_y}" width="80" height="4" '
        f'rx="2" fill="{accent_color}"/>\n'
        f'</svg>'
    )
    safe_name = Path(filename).name
    if not safe_name.endswith(".svg"):
        safe_name += ".svg"
    (STATIC_IMG / safe_name).write_text(svg)
    return {"success": True, "url": f"/static/img/{safe_name}", "dimensions": f"{width}x{height}"}


# ── Brand CSS ──────────────────────────────────────────────────────────────────

async def update_brand_css(
    primary: str = "#7C3AED",
    primary_dark: str = "#4C1D95",
    primary_light: str = "#A78BFA",
    accent_pink: str = "#EC4899",
    accent_gold: str = "#FBBF24",
) -> dict[str, Any]:
    """Regenerate brand.css with updated color variables."""
    css = f"""/* Vendo's Deals — Brand Stylesheet  (updated {datetime.utcnow().strftime('%Y-%m-%d')}) */
:root {{
  --vd-primary:       {primary};
  --vd-primary-dark:  {primary_dark};
  --vd-primary-light: {primary_light};
  --vd-accent-pink:   {accent_pink};
  --vd-accent-gold:   {accent_gold};
  --vd-glass:         #DBEAFE;
  --vd-text-on-dark:  #EDE9FE;
}}

.text-indigo-600              {{ color: var(--vd-primary) !important; }}
.hover\\:text-indigo-600:hover {{ color: var(--vd-primary) !important; }}
.bg-indigo-600                {{ background-color: var(--vd-primary) !important; }}
.hover\\:bg-indigo-700:hover   {{ background-color: var(--vd-primary-dark) !important; }}
.border-indigo-600            {{ border-color: var(--vd-primary) !important; }}

.vd-nav-logo {{ display:flex; align-items:center; text-decoration:none; }}
.vd-nav-logo:hover {{ opacity:0.88; }}

.vd-btn-primary {{ background-color:var(--vd-primary); color:#fff; transition:background-color 0.18s; }}
.vd-btn-primary:hover {{ background-color:var(--vd-primary-dark); }}

.vd-badge {{ background-color:var(--vd-accent-gold); color:#1E1B4B; font-size:0.65rem;
             font-weight:700; padding:0.15rem 0.48rem; border-radius:9999px; letter-spacing:0.06em; }}
.vd-sale-badge {{ background:var(--vd-accent-pink); color:white; font-size:0.65rem;
                  font-weight:700; padding:0.15rem 0.5rem; border-radius:9999px; }}
.vd-price {{ color:var(--vd-primary); font-weight:700; }}
footer a:hover {{ color:var(--vd-primary) !important; }}
"""
    (STATIC_CSS / "brand.css").write_text(css)
    return {"success": True, "file": "store/static/css/brand.css",
            "colors": {"primary": primary, "primary_dark": primary_dark,
                       "accent_pink": accent_pink, "accent_gold": accent_gold}}


# ── Asset inspection ───────────────────────────────────────────────────────────

async def list_brand_assets() -> dict[str, Any]:
    """List all current SVG and CSS brand assets."""
    return {
        "svg_assets": [
            {"name": f.name, "url": f"/static/img/{f.name}", "bytes": f.stat().st_size}
            for f in sorted(STATIC_IMG.glob("*.svg"))
        ],
        "css_files": [
            {"name": f.name, "url": f"/static/css/{f.name}", "bytes": f.stat().st_size}
            for f in sorted(STATIC_CSS.glob("*.css"))
        ],
    }


async def read_brand_asset(filename: str) -> dict[str, Any]:
    """Read the content of a brand SVG or CSS file."""
    safe_name = Path(filename).name
    for directory in (STATIC_IMG, STATIC_CSS):
        target = directory / safe_name
        if target.exists():
            return {"success": True, "filename": safe_name, "content": target.read_text()}
    return {"error": f"File not found: {safe_name}"}


# ── Template patching ──────────────────────────────────────────────────────────

async def set_nav_logo(logo_html: str) -> dict[str, Any]:
    """
    Replace the logo <a> tag in base.html.
    logo_html: full replacement <a> tag including class and inner content.
    """
    base = TEMPLATES_DIR / "base.html"
    content = base.read_text()
    # Match the current logo link
    old = '<a href="/" class="vd-nav-logo">'
    if old not in content:
        # First time: replace placeholder text logo
        old = '<a href="/" class="text-2xl font-bold text-indigo-600">{{ store_name }}</a>'
    if old not in content:
        return {"error": "Could not locate the logo link in base.html"}
    # Replace from old opening tag through matching </a>
    start = content.index(old)
    end = content.index("</a>", start) + 4
    new_content = content[:start] + logo_html + content[end:]
    base.write_text(new_content)
    return {"success": True}


# ── Audit logging ──────────────────────────────────────────────────────────────

async def record_design_update(asset_name: str, description: str) -> dict[str, Any]:
    """Log a design change to the metrics audit trail."""
    async with AsyncSessionLocal() as db:
        db.add(BusinessMetric(
            metric_name="design_update",
            metric_value=1.0,
            metric_data=json.dumps({
                "asset": asset_name,
                "description": description,
                "updated_at": datetime.utcnow().isoformat(),
            }),
        ))
        await db.commit()
    return {"success": True}


# ── Tool registry ──────────────────────────────────────────────────────────────

class DesignTools:
    SCHEMAS = [
        {
            "name": "create_or_update_svg",
            "description": "Write or update an SVG file in store/static/img/. "
                           "Use for mascot variants, badges, icons, category headers.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filename":    {"type": "string", "description": "SVG filename, e.g. 'banner.svg'"},
                    "svg_content": {"type": "string", "description": "Complete SVG markup"},
                    "description": {"type": "string"},
                },
                "required": ["filename", "svg_content"],
            },
        },
        {
            "name": "create_promotional_banner",
            "description": "Generate a polished promotional hero/banner SVG (sale, seasonal, category).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filename":      {"type": "string"},
                    "heading":       {"type": "string"},
                    "subtext":       {"type": "string"},
                    "primary_color": {"type": "string"},
                    "accent_color":  {"type": "string"},
                    "width":         {"type": "integer"},
                    "height":        {"type": "integer"},
                },
                "required": ["filename", "heading"],
            },
        },
        {
            "name": "update_brand_css",
            "description": "Regenerate brand.css with new color variables. Controls the site-wide palette.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "primary":       {"type": "string"},
                    "primary_dark":  {"type": "string"},
                    "primary_light": {"type": "string"},
                    "accent_pink":   {"type": "string"},
                    "accent_gold":   {"type": "string"},
                },
            },
        },
        {
            "name": "list_brand_assets",
            "description": "List all current brand SVGs and CSS files with URLs and sizes.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "read_brand_asset",
            "description": "Read the content of a brand asset file (SVG or CSS).",
            "input_schema": {
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"],
            },
        },
        {
            "name": "set_nav_logo",
            "description": "Replace the logo link in the site nav (base.html). "
                           "Provide the full replacement <a> tag HTML.",
            "input_schema": {
                "type": "object",
                "properties": {"logo_html": {"type": "string"}},
                "required": ["logo_html"],
            },
        },
        {
            "name": "record_design_update",
            "description": "Log a design change to the metrics audit trail.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "asset_name":  {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["asset_name", "description"],
            },
        },
    ]

    MAP = {
        "create_or_update_svg":      create_or_update_svg,
        "create_promotional_banner": create_promotional_banner,
        "update_brand_css":          update_brand_css,
        "list_brand_assets":         list_brand_assets,
        "read_brand_asset":          read_brand_asset,
        "set_nav_logo":              set_nav_logo,
        "record_design_update":      record_design_update,
    }
