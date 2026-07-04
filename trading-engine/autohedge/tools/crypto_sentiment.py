"""Crypto news/sentiment for the sentiment agent (Exa optional)."""

from __future__ import annotations

import json
import os

from loguru import logger

from autohedge.tools.blofin_client import BlofinClient
from autohedge.tools.blofin_universe_feed import get_universe_feed
from autohedge.tools.market_analytics import funding_bias, ticker_change_pct


def _ticker_row(client: BlofinClient, inst: str) -> tuple[dict | None, str]:
    try:
        rows = client.get_tickers(inst)
        if rows:
            return rows[0], "rest"
    except Exception as exc:
        logger.warning("crypto_news_search ticker REST failed for {}: {}", inst, exc)
    cached = get_universe_feed().ticker_for(inst)
    if cached:
        return cached, "universe_cache"
    return None, "none"


def crypto_news_search(inst_id: str = "", query: str = "", **_kwargs: object) -> str:
    """
    Search crypto news for an instrument. Uses Exa when EXA_API_KEY is set;
    otherwise returns funding + 24h price sentiment proxy from Blofin.
    """
    inst = inst_id.strip().upper()
    base = inst.split("-")[0] if inst else ""
    search_q = query.strip() or (
        f"{base} cryptocurrency news sentiment last 24 hours" if base else "crypto market sentiment"
    )

    proxy: dict = {"instId": inst or None, "source": "blofin_proxy"}
    client = BlofinClient()
    if inst:
        try:
            ticker_row, ticker_source = _ticker_row(client, inst)
            if ticker_row:
                chg = ticker_change_pct(ticker_row)
                proxy["chg_pct_24h"] = round(chg, 3) if chg is not None else None
                proxy["last"] = ticker_row.get("last")
                proxy["ticker_source"] = ticker_source
                if chg is not None:
                    if chg > 3:
                        proxy["price_sentiment"] = 0.7
                        proxy["note"] = "Strong 24h gain — bullish momentum."
                    elif chg > 0.5:
                        proxy["price_sentiment"] = 0.6
                        proxy["note"] = "Mild positive 24h move."
                    elif chg < -3:
                        proxy["price_sentiment"] = 0.3
                        proxy["note"] = "Sharp 24h decline — bearish momentum."
                    elif chg < -0.5:
                        proxy["price_sentiment"] = 0.4
                        proxy["note"] = "Mild negative 24h move."
                    else:
                        proxy["price_sentiment"] = 0.5
                        proxy["note"] = "Flat 24h price action."
        except Exception as exc:
            proxy["ticker_error"] = str(exc)
        try:
            fr = client.get_funding_rate(inst)
            rate = float(fr.get("fundingRate") or 0)
            fb = funding_bias(rate)
            proxy["funding"] = fb
        except Exception as exc:
            proxy["funding_error"] = str(exc)

    api_key = os.getenv("EXA_API_KEY", "").strip()
    if not api_key:
        proxy["exa"] = "skipped_no_api_key"
        return json.dumps(proxy, default=str)

    try:
        from autohedge.tools.exa_search_tool import exa_search

        exa_result = exa_search(search_q)
        return json.dumps(
            {"instId": inst, "source": "exa+blofin", "exa": exa_result, "blofin_proxy": proxy},
            default=str,
        )
    except Exception as exc:
        logger.warning("Exa search failed, using proxy: {}", exc)
        proxy["exa_error"] = str(exc)
        return json.dumps(proxy, default=str)
