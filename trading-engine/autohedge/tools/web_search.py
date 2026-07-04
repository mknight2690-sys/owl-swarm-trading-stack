"""Internet search for tactic research — Exa when available, DuckDuckGo fallback."""

from __future__ import annotations

import json
import os
import re
import time
from html import unescape
from typing import Any

import httpx
from loguru import logger

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 3600.0


def _cache_get(key: str) -> str | None:
    row = _CACHE.get(key)
    if not row:
        return None
    if time.time() - row[0] > _CACHE_TTL:
        return None
    return row[1]


def _cache_set(key: str, value: str) -> None:
    _CACHE[key] = (time.time(), value)


def search_exa(query: str, *, num_results: int = 3) -> dict[str, Any]:
    api_key = os.getenv("EXA_API_KEY", "").strip()
    if not api_key:
        return {"source": "exa", "skipped": "no_api_key"}

    payload = {
        "query": query,
        "type": "auto",
        "numResults": num_results,
        "contents": {"text": True, "summary": True},
    }
    resp = httpx.post(
        "https://api.exa.ai/search",
        json=payload,
        headers={"x-api-key": api_key, "content-type": "application/json"},
        timeout=45,
    )
    resp.raise_for_status()
    data = resp.json()
    snippets: list[dict[str, str]] = []
    for row in data.get("results") or []:
        snippets.append(
            {
                "title": str(row.get("title") or ""),
                "url": str(row.get("url") or ""),
                "text": str(row.get("text") or row.get("summary") or "")[:1200],
            }
        )
    return {"source": "exa", "query": query, "results": snippets}


def search_duckduckgo(query: str, *, max_results: int = 5) -> dict[str, Any]:
    """HTML fallback when Exa is unavailable."""
    resp = httpx.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query, "b": ""},
        headers={"User-Agent": _UA},
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    html = resp.text
    snippets: list[dict[str, str]] = []
    for block in re.findall(r'class="result__body".*?</div>\s*</div>', html, flags=re.S):
        title_m = re.search(r'class="result__a"[^>]*>(.*?)</a>', block, flags=re.S)
        snippet_m = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, flags=re.S)
        if not title_m:
            continue
        title = unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip()
        snippet = ""
        if snippet_m:
            snippet = unescape(re.sub(r"<[^>]+>", "", snippet_m.group(1))).strip()
        if title:
            snippets.append({"title": title, "url": "", "text": snippet[:800]})
        if len(snippets) >= max_results:
            break
    return {"source": "duckduckgo", "query": query, "results": snippets}


def web_search(query: str, *, use_cache: bool = True) -> str:
    """Search the web; returns JSON string of summaries."""
    q = query.strip()
    if not q:
        return json.dumps({"error": "empty_query"})
    if use_cache:
        cached = _cache_get(q.lower())
        if cached:
            return cached

    out: dict[str, Any] = {"query": q, "ts": time.time()}
    try:
        exa = search_exa(q)
        if exa.get("results"):
            out["engine"] = "exa"
            out["results"] = exa["results"]
        else:
            raise RuntimeError(exa.get("skipped") or "exa_empty")
    except Exception as exc:
        logger.warning("Exa search failed ({}), using DuckDuckGo", exc)
        try:
            ddg = search_duckduckgo(q)
            out["engine"] = "duckduckgo"
            out["results"] = ddg.get("results") or []
            out["exa_error"] = str(exc)
        except Exception as ddg_exc:
            out["engine"] = "none"
            out["error"] = str(ddg_exc)
            out["results"] = []

    text = json.dumps(out, default=str)
    _cache_set(q.lower(), text)
    return text
