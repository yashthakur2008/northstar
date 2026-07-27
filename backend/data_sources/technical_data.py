"""
Technical indicators computed directly from yfinance price history --
no separate technical-analysis API or key needed, and no ta-lib (its C
bindings are painful to install on Render's free tier). Just pandas.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf


def _rsi(closes: pd.Series, period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    value = rsi.iloc[-1]
    return None if pd.isna(value) else round(float(value), 2)


def get_technical_snapshot(symbol: str) -> dict | None:
    hist = yf.Ticker(symbol).history(period="6mo", interval="1d")
    if hist is None or hist.empty or "Close" not in hist:
        return None

    closes = hist["Close"]
    sma20 = closes.rolling(20).mean().iloc[-1] if len(closes) >= 20 else None
    sma50 = closes.rolling(50).mean().iloc[-1] if len(closes) >= 50 else None
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()

    last_close = float(closes.iloc[-1])
    period_start = float(closes.iloc[0])

    return {
        "last_close": round(last_close, 2),
        "pct_change_6mo": (
            round((last_close / period_start - 1) * 100, 2) if period_start else None
        ),
        "sma_20": round(float(sma20), 2) if sma20 is not None and not pd.isna(sma20) else None,
        "sma_50": round(float(sma50), 2) if sma50 is not None and not pd.isna(sma50) else None,
        "rsi_14": _rsi(closes),
        "macd": round(float(macd_line.iloc[-1]), 3),
        "macd_signal": round(float(signal_line.iloc[-1]), 3),
        "volume_avg_20d": (
            int(hist["Volume"].rolling(20).mean().iloc[-1]) if len(hist) >= 20 else None
        ),
    }
