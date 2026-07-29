"""
Registry of the six specialist agents. Each module exposes a `run(symbol)`
function built from `agents.base.run_data_agent`. `ALL_AGENTS` is the list
`graph.py`'s specialists_node fans out over, once per ticker.
"""

from __future__ import annotations

from agents import (
    fundamentals_agent,
    macro_agent,
    news_agent,
    options_agent,
    risk_agent,
    technical_agent,
)

ALL_AGENTS = [
    news_agent,
    fundamentals_agent,
    technical_agent,
    options_agent,
    macro_agent,
    risk_agent,
]
