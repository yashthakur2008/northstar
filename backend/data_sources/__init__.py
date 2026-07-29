"""
Six free, mostly-keyless data sources, one module per specialist agent's
input: market_data (fundamentals), technical_data, options_data,
macro_data, news_data, risk_data. Each exposes a single `get_*(symbol)`
function returning a plain dict, or None if no data is available -- the
agent that calls it (see backend/agents/base.py) turns a None into a
graceful data_available=False opinion rather than a crash.
"""

from __future__ import annotations
