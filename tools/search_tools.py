"""
Web search and product research tools.
Uses SerpAPI when configured; falls back to DuckDuckGo HTML scraping.
"""

import json
from typing import Any

import httpx

from config import get_settings

settings = get_settings()

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DropshippingBot/1.0)"}


async def search_web(query: str, num_results: int = 10) -> dict[str, Any]:
    """Search the web for a query. Returns list of results with title/url/snippet."""
    if settings.serp_api_key:
        return await _serp_search(query, num_results)
    return await _ddg_search(query, num_results)


async def _serp_search(query: str, num: int) -> dict[str, Any]:
    params = {
        "q": query,
        "api_key": settings.serp_api_key,
        "num": num,
        "engine": "google",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://serpapi.com/search", params=params)
        r.raise_for_status()
        data = r.json()
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in data.get("organic_results", [])[:num]
        ]
        return {"results": results, "query": query}


async def _ddg_search(query: str, num: int) -> dict[str, Any]:
    """DuckDuckGo instant answer API (limited but free, no key needed)."""
    params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1"}
    try:
        async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
            r = await client.get("https://api.duckduckgo.com/", params=params)
            r.raise_for_status()
            data = r.json()
            results = []
            for item in data.get("RelatedTopics", [])[:num]:
                if "Text" in item:
                    results.append({
                        "title": item.get("Text", "")[:80],
                        "url": item.get("FirstURL", ""),
                        "snippet": item.get("Text", ""),
                    })
            return {"results": results, "query": query, "abstract": data.get("Abstract", "")}
    except Exception as exc:
        return {"results": [], "query": query, "error": str(exc)}


async def search_trending_products(niche: str, limit: int = 20) -> dict[str, Any]:
    """Find trending products in a niche by searching multiple signals."""
    queries = [
        f"trending {niche} products 2025",
        f"best selling {niche} dropshipping products",
        f"{niche} products high demand low competition",
    ]
    all_results: list[dict] = []
    for q in queries:
        res = await search_web(q, num_results=5)
        all_results.extend(res.get("results", []))

    return {
        "niche": niche,
        "signals": all_results[:limit],
        "recommendation": (
            f"Review the above signals for {niche}. "
            "Look for products appearing across multiple sources with clear demand."
        ),
    }


async def search_competitor_prices(product_name: str) -> dict[str, Any]:
    """Find competitor prices for a product across major retailers."""
    queries = [
        f'"{product_name}" price site:amazon.com',
        f'"{product_name}" buy online price',
        f'"{product_name}" -amazon price comparison',
    ]
    results: list[dict] = []
    for q in queries:
        r = await search_web(q, num_results=5)
        results.extend(r.get("results", []))

    return {
        "product": product_name,
        "competitor_results": results,
        "note": "Parse prices from snippets/URLs to determine market pricing.",
    }


async def search_supplier_for_product(product_query: str) -> dict[str, Any]:
    """Find dropshipping suppliers for a product."""
    queries = [
        f"{product_query} dropshipping supplier aliexpress",
        f"{product_query} wholesale supplier dropship",
        f"site:aliexpress.com {product_query}",
    ]
    results: list[dict] = []
    for q in queries:
        r = await search_web(q, num_results=5)
        results.extend(r.get("results", []))

    return {
        "product_query": product_query,
        "supplier_results": results,
    }


class SearchTools:
    """Namespace for tool schemas + callables used by agents."""

    SCHEMAS = [
        {
            "name": "search_trending_products",
            "description": "Search for trending products in a specific niche to add to the store.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "niche": {"type": "string", "description": "Product niche, e.g. 'pet accessories', 'home office'"},
                    "limit": {"type": "integer", "description": "Max results", "default": 20},
                },
                "required": ["niche"],
            },
        },
        {
            "name": "search_competitor_prices",
            "description": "Search for competitor prices for a product to benchmark our pricing.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string", "description": "Product name to search"},
                },
                "required": ["product_name"],
            },
        },
        {
            "name": "search_supplier_for_product",
            "description": "Find dropshipping suppliers for a specific product.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "product_query": {"type": "string", "description": "Product search query"},
                },
                "required": ["product_query"],
            },
        },
        {
            "name": "search_web",
            "description": "General web search.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "num_results": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
    ]

    MAP = {
        "search_trending_products": search_trending_products,
        "search_competitor_prices": search_competitor_prices,
        "search_supplier_for_product": search_supplier_for_product,
        "search_web": search_web,
    }
