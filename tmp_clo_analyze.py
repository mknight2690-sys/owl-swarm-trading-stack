import json
from pathlib import Path

BASE = Path(r"C:\Users\mknig\owl-swarm")


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))


def analyze_candles(path, label):
    raw = json.loads(path.read_text(encoding="utf-8-sig").strip())
    candles = list(reversed(raw))
    closes = [float(c[4]) for c in candles]
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    r = rsi(closes)
    chg = (closes[-1] - closes[0]) / closes[0] * 100
    up5 = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0
    green = sum(1 for c in candles if float(c[4]) > float(c[1]))
    trend = "bearish" if chg < -0.3 else "bullish" if chg > 0.3 else "neutral"
    return {
        "label": label,
        "close": closes[-1],
        "period_chg_pct": round(chg, 3),
        "last5_chg_pct": round(up5, 3),
        "rsi14": round(r, 1) if r else None,
        "green_ratio": round(green / len(candles), 2),
        "high": max(highs),
        "low": min(lows),
        "trend": trend,
    }


book = json.loads((BASE / "tmp_clo_book.json").read_text())
# use live book from earlier run - re-read from bridge output stored
import subprocess
p = subprocess.run(
    [r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe", "blofin_bridge.py", "get_order_book", f"@{BASE / 'tmp_clo_book.json'}"],
    capture_output=True, text=True, cwd=str(BASE)
)
book = json.loads(p.stdout.strip())
bid = float(book["bids"][0][0])
ask = float(book["asks"][0][0])
mid = (bid + ask) / 2
spread_pct = (ask - bid) / mid * 100

p2 = subprocess.run(
    [r"C:\Users\mknig\AppData\Local\Programs\Python\Python312\python.exe", "blofin_bridge.py", "get_funding_rate", f"@{BASE / 'tmp_clo_funding.json'}"],
    capture_output=True, text=True, cwd=str(BASE)
)
fund = json.loads(p2.stdout.strip())
funding = float(fund["fundingRate"])

results = [
    analyze_candles(BASE / "outputs/clo_c1m_live.json", "1m"),
    analyze_candles(BASE / "outputs/clo_c15_live.json", "15m"),
    analyze_candles(BASE / "outputs/clo_c1h_live.json", "1h"),
]
print(json.dumps({"spread_pct": round(spread_pct, 4), "funding": funding, "timeframes": results}, indent=2))
