import json

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period-1) + gains[i]) / period
        avg_loss = (avg_loss * (period-1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def analyze(candles, label):
    # candles newest first from API
    candles = list(reversed(candles))
    closes = [float(c[4]) for c in candles]
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    r = rsi(closes)
    first, last = closes[0], closes[-1]
    chg = (last - first) / first * 100
  # simple momentum: last 5 vs prior 5
    mom5 = (sum(closes[-5:])/5 - sum(closes[-10:-5])/5) / sum(closes[-10:-5])/5 * 100 if len(closes)>=10 else 0
    print(f"{label}: first={first:.4f} last={last:.4f} chg%={chg:.3f} RSI14={r:.1f} mom5%={mom5:.3f} high={max(highs):.4f} low={min(lows):.4f}")

# load from stdin - paste data
import sys
