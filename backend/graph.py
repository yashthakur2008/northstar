"""
LangGraph orchestration: fan out the six specialist agents per ticker, run
an N-round Bull/Bear debate per ticker, then synthesize everything into a
ranked AnalysisReport via the Portfolio Manager judge.

Flow: START -> specialists -> debate --(loop until round == debate_rounds)--> judge -> END

Known limitation (documented, not yet fixed): every agent call is
sequential. Worst case (5 tickers, 4 rounds) is roughly 5*6 specialist
calls + 5*4*2 debate calls + 1 judge call = ~71 sequential LLM calls,
which is slow and can burn through a free-tier rate limit fast. Fine for
validating correctness; parallelizing the independent calls (asyncio.gather
across tickers and agents) is the next real optimization once this is
confirmed working end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agents import ALL_AGENTS
from agents.debate import run_bear, run_bull
from agents.judge import run_judge
from models import AgentOpinion, AnalysisReport, DebateTurn


class GraphState(TypedDict):
    tickers: list[str]
    debate_rounds: int
    round_counter: int
    opinions: dict[str, list[AgentOpinion]]
    transcript: dict[str, list[DebateTurn]]
    final_trades: list[dict]
    market_context: str


def specialists_node(state: GraphState) -> dict:
    opinions: dict[str, list[AgentOpinion]] = {}
    for symbol in state["tickers"]:
        opinions[symbol] = [agent_module.run(symbol) for agent_module in ALL_AGENTS]
    return {
        "opinions": opinions,
        "round_counter": 0,
        "transcript": {symbol: [] for symbol in state["tickers"]},
    }


def debate_node(state: GraphState) -> dict:
    round_number = state["round_counter"] + 1
    transcript = {symbol: list(turns) for symbol, turns in state["transcript"].items()}

    for symbol in state["tickers"]:
        bull_turn = run_bull(symbol, state["opinions"][symbol], transcript[symbol], round_number)
        transcript[symbol].append(bull_turn)
        bear_turn = run_bear(symbol, state["opinions"][symbol], transcript[symbol], round_number)
        transcript[symbol].append(bear_turn)

    return {"transcript": transcript, "round_counter": round_number}


def should_continue_debate(state: GraphState) -> str:
    return "debate" if state["round_counter"] < state["debate_rounds"] else "judge"


def judge_node(state: GraphState) -> dict:
    trades, market_context = run_judge(state["opinions"], state["transcript"])
    return {
        "final_trades": [t.model_dump() for t in trades],
        "market_context": market_context or "No market context returned by the judge.",
    }


def build_graph():
    graph = StateGraph(GraphState)
    graph.add_node("specialists", specialists_node)
    graph.add_node("debate", debate_node)
    graph.add_node("judge", judge_node)
    graph.add_edge(START, "specialists")
    graph.add_edge("specialists", "debate")
    graph.add_conditional_edges(
        "debate", should_continue_debate, {"debate": "debate", "judge": "judge"}
    )
    graph.add_edge("judge", END)
    return graph.compile()


_compiled_graph = None


def run_analysis(tickers: list[str], debate_rounds: int) -> AnalysisReport:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()

    result = _compiled_graph.invoke(
        {
            "tickers": tickers,
            "debate_rounds": debate_rounds,
            "round_counter": 0,
            "opinions": {},
            "transcript": {},
            "final_trades": [],
            "market_context": "",
        }
    )

    return AnalysisReport(
        top_trades=result["final_trades"],
        market_context=result["market_context"],
        generated_at=datetime.now(timezone.utc),
        is_mocked=False,
    )
