"""
AutoHedge workers: Pydantic output models and agents for thesis
generation, risk assessment, execution, and quantitative analysis.
"""

import autohedge.swarms_bootstrap  # noqa: F401 — patch tool-calling checks before Agent init
from datetime import datetime

from swarms import Agent

from autohedge.env_loader import load_env
from autohedge.model_config import agent_model_name
from autohedge.prompts import (
    CLIQUE_RUGGED_DOCTRINE,
    COLLECTIVE_CARE_DOCTRINE,
    CROSS_CHECK_DOCTRINE,
    DESKTOP_HYGIENE_DOCTRINE,
    DIRECTOR_PROMPT,
    EXECUTION_PROMPT,
    MARKET_RESEARCHER_PROMPT,
    OPS_MONITOR_PROMPT,
    POLYMORPHIC_MESH_DOCTRINE,
    PORTFOLIO_PROMPT,
    PROFIT_STRATEGIST_PROMPT,
    QUANT_PROMPT,
    RISK_PROMPT,
    SENTIMENT_PROMPT,
    SURFACE_SYNC_DOCTRINE,
    SELF_HEAL_DOCTRINE,
    SWARM_VERIFICATION_DOCTRINE,
    FIELD_TECH_DOCTRINE,
    PENTEST_SCOUT_PROMPT,
    PENTEST_TRADE_HUNTER_PROMPT,
    PENTEST_INTEGRITY_PROMPT,
    PENTEST_OPERATOR_PROMPT,
    TACTICS_RESEARCHER_PROMPT,
    TASK_COMPLETION_DOCTRINE,
    UNIVERSAL_AGENT_DOCTRINE,
    VERIFIER_PROMPT,
)
from autohedge.tools.blofin_tools import (
    blofin_assess_portfolio,
    blofin_cancel_order,
    blofin_close_position,
    blofin_compute_position_size,
    blofin_ensure_position_tpsl,
    blofin_execute_minimum_trade,
    blofin_get_account_balances,
    blofin_get_candles,
    blofin_get_equity_summary,
    blofin_get_funding_rate,
    blofin_get_instrument_specs,
    blofin_get_order_book,
    blofin_get_pending_tpsl,
    blofin_get_positions,
    blofin_get_ticker,
    blofin_get_trade_insights,
    blofin_get_learned_tactics,
    blofin_research_trading_tactics,
    blofin_get_swarm_learning_report,
    blofin_get_stack_health,
    blofin_get_self_heal_playbook,
    blofin_get_universe_snapshot,
    blofin_list_all_instruments,
    blofin_place_order,
    blofin_place_tpsl,
    blofin_rank_opportunities,
    blofin_technical_analysis,
)
from autohedge.tools.pentest_tools import (
    pentest_apply_targeted_fixes,
    pentest_build_mission_queue,
    pentest_diagnose_collective_audit,
    pentest_diagnose_pipeline_handoff,
    pentest_diagnose_trade_pipeline,
    pentest_diagnose_verifier_integrity,
    pentest_get_deterministic_findings,
    pentest_probe_integration,
    pentest_probe_runtime,
    pentest_run_autonomous_heal,
    pentest_scan_critical_files,
    pentest_tail_artifact,
)
from autohedge.tools.crypto_sentiment import crypto_news_search
load_env()
MODEL = agent_model_name()
_LLM_ARGS = {"mcp_call": True}

_NOW = datetime.now()
_DATE_TIME_LINE = _NOW.strftime("%A, %B %d, %Y at %H:%M")
if _NOW.tzinfo:
    _DATE_TIME_LINE += f" {_NOW.tzname() or ''}"
_SYSTEM_SUFFIX = (
    f"\n\nCurrent date and time (use this as now): {_DATE_TIME_LINE.strip()}"
    f"\n{CROSS_CHECK_DOCTRINE}"
    f"\n{UNIVERSAL_AGENT_DOCTRINE}"
    f"\n{COLLECTIVE_CARE_DOCTRINE}"
    f"\n{CLIQUE_RUGGED_DOCTRINE}"
    f"\n{POLYMORPHIC_MESH_DOCTRINE}"
    f"\n{TASK_COMPLETION_DOCTRINE}"
    f"\n{SURFACE_SYNC_DOCTRINE}"
    f"\n{SELF_HEAL_DOCTRINE}"
    f"\n{SWARM_VERIFICATION_DOCTRINE}"
    f"\n{FIELD_TECH_DOCTRINE}"
    f"\n{DESKTOP_HYGIENE_DOCTRINE}"
)

portfolio_agent = Agent(
    agent_name="Portfolio-Manager",
    system_prompt=PORTFOLIO_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=2,
    verbose=False,
    print_on=False,
    context_length=24000,
    tools=[
        blofin_assess_portfolio,
        blofin_get_positions,
        blofin_get_equity_summary,
        blofin_get_account_balances,
        blofin_get_trade_insights,
        blofin_get_learned_tactics,
        blofin_research_trading_tactics,
        blofin_ensure_position_tpsl,
        blofin_get_pending_tpsl,
        blofin_rank_opportunities,
    ],
)

sentiment_agent = Agent(
    agent_name="Sentiment-Agent",
    system_prompt=SENTIMENT_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    verbose=False,
    print_on=False,
    max_loops=2,
    context_length=24000,
    tools=[
        crypto_news_search,
        blofin_get_funding_rate,
        blofin_get_ticker,
        blofin_get_universe_snapshot,
        blofin_get_trade_insights,
        blofin_research_trading_tactics,
        blofin_get_learned_tactics,
    ],
)

risk_agent = Agent(
    agent_name="Risk-Manager",
    system_prompt=RISK_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=2,
    verbose=False,
    print_on=False,
    context_length=24000,
    tools=[
        blofin_assess_portfolio,
        blofin_compute_position_size,
        blofin_technical_analysis,
        blofin_get_funding_rate,
        blofin_get_equity_summary,
        blofin_get_account_balances,
        blofin_get_trade_insights,
        blofin_research_trading_tactics,
        blofin_get_learned_tactics,
    ],
)

execution_agent = Agent(
    agent_name="Execution-Agent",
    system_prompt=EXECUTION_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=4,
    verbose=False,
    print_on=False,
    context_length=24000,
    tools=[
        blofin_execute_minimum_trade,
        blofin_assess_portfolio,
        blofin_get_instrument_specs,
        blofin_place_order,
        blofin_place_tpsl,
        blofin_ensure_position_tpsl,
        blofin_get_pending_tpsl,
        blofin_close_position,
        blofin_cancel_order,
        blofin_get_positions,
    ],
)

quant_agent = Agent(
    agent_name="Quant-Analyst",
    system_prompt=QUANT_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=3,
    verbose=False,
    print_on=False,
    context_length=24000,
    tools=[
        blofin_technical_analysis,
        blofin_get_candles,
        blofin_get_funding_rate,
        blofin_get_order_book,
        blofin_get_ticker,
        blofin_rank_opportunities,
        blofin_get_trade_insights,
        blofin_get_learned_tactics,
        blofin_research_trading_tactics,
        blofin_get_universe_snapshot,
    ],
)

ALL_AGENTS = [
    portfolio_agent,
    sentiment_agent,
    risk_agent,
    execution_agent,
    quant_agent,
]

# ── Support LLM agents (ops, verify, research, profit — original swarm design) ──

verifier_agent = Agent(
    agent_name="Verifier-Agent",
    system_prompt=VERIFIER_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=2,
    verbose=False,
    print_on=False,
    context_length=24000,
    tools=[
        blofin_technical_analysis,
        blofin_get_funding_rate,
        blofin_get_equity_summary,
        blofin_assess_portfolio,
        blofin_get_ticker,
        blofin_get_stack_health,
        blofin_get_swarm_learning_report,
    ],
)

ops_monitor_agent = Agent(
    agent_name="Ops-Monitor-Agent",
    system_prompt=OPS_MONITOR_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=2,
    verbose=False,
    print_on=False,
    context_length=24000,
    tools=[
        blofin_get_stack_health,
        blofin_get_swarm_learning_report,
        blofin_assess_portfolio,
        blofin_get_equity_summary,
        blofin_get_learned_tactics,
        blofin_get_self_heal_playbook,
        blofin_ensure_position_tpsl,
    ],
)

tactics_researcher_agent = Agent(
    agent_name="Tactics-Researcher-Agent",
    system_prompt=TACTICS_RESEARCHER_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=2,
    verbose=False,
    print_on=False,
    context_length=24000,
    tools=[
        blofin_research_trading_tactics,
        blofin_get_learned_tactics,
        blofin_get_trade_insights,
        crypto_news_search,
        blofin_get_swarm_learning_report,
    ],
)

profit_strategist_agent = Agent(
    agent_name="Profit-Strategist-Agent",
    system_prompt=PROFIT_STRATEGIST_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=2,
    verbose=False,
    print_on=False,
    context_length=24000,
    tools=[
        blofin_get_trade_insights,
        blofin_get_learned_tactics,
        blofin_get_equity_summary,
        blofin_rank_opportunities,
        blofin_get_swarm_learning_report,
    ],
)

market_researcher_agent = Agent(
    agent_name="Market-Researcher-Agent",
    system_prompt=MARKET_RESEARCHER_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=2,
    verbose=False,
    print_on=False,
    context_length=24000,
    tools=[
        blofin_technical_analysis,
        blofin_get_candles,
        blofin_get_funding_rate,
        blofin_get_order_book,
        blofin_get_ticker,
        crypto_news_search,
    ],
)

# ── Pentest Special Forces (self-directing mechanics — not in trading handoff) ──

_PENTEST_TOOLS_COMMON = [
    pentest_get_deterministic_findings,
    pentest_build_mission_queue,
    pentest_tail_artifact,
    pentest_probe_runtime,
    pentest_scan_critical_files,
    blofin_get_stack_health,
    blofin_get_self_heal_playbook,
]

pentest_scout_agent = Agent(
    agent_name="Pentest-Scout-Agent",
    system_prompt=PENTEST_SCOUT_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=3,
    verbose=False,
    print_on=False,
    context_length=28000,
    tools=_PENTEST_TOOLS_COMMON + [pentest_probe_integration],
)

pentest_trade_hunter_agent = Agent(
    agent_name="Pentest-Trade-Hunter-Agent",
    system_prompt=PENTEST_TRADE_HUNTER_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=3,
    verbose=False,
    print_on=False,
    context_length=28000,
    tools=_PENTEST_TOOLS_COMMON
    + [
        pentest_diagnose_trade_pipeline,
        pentest_diagnose_pipeline_handoff,
        blofin_get_equity_summary,
        blofin_assess_portfolio,
        blofin_get_trade_insights,
    ],
)

pentest_integrity_agent = Agent(
    agent_name="Pentest-Integrity-Agent",
    system_prompt=PENTEST_INTEGRITY_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=3,
    verbose=False,
    print_on=False,
    context_length=28000,
    tools=_PENTEST_TOOLS_COMMON
    + [
        pentest_diagnose_verifier_integrity,
        pentest_diagnose_collective_audit,
    ],
)

pentest_operator_agent = Agent(
    agent_name="Pentest-Operator-Agent",
    system_prompt=PENTEST_OPERATOR_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    output_type="str",
    max_loops=4,
    verbose=False,
    print_on=False,
    context_length=28000,
    tools=_PENTEST_TOOLS_COMMON
    + [
        pentest_apply_targeted_fixes,
        pentest_run_autonomous_heal,
        pentest_diagnose_trade_pipeline,
        pentest_diagnose_pipeline_handoff,
        pentest_diagnose_verifier_integrity,
        blofin_ensure_position_tpsl,
    ],
)

PENTEST_AGENTS = [
    pentest_scout_agent,
    pentest_trade_hunter_agent,
    pentest_integrity_agent,
    pentest_operator_agent,
]

SUPPORT_AGENTS = [
    verifier_agent,
    ops_monitor_agent,
    tactics_researcher_agent,
    profit_strategist_agent,
    market_researcher_agent,
]

AGENT_REGISTRY = {agent.agent_name: agent for agent in ALL_AGENTS}

director_agent = Agent(
    agent_name="Trading-Director",
    system_prompt=DIRECTOR_PROMPT + _SYSTEM_SUFFIX,
    model_name=MODEL,
    llm_args=_LLM_ARGS,
    max_loops=5,
    verbose=False,
    print_on=False,
    context_length=24000,
    handoffs=ALL_AGENTS,
    tools=[
        blofin_rank_opportunities,
        blofin_get_universe_snapshot,
        blofin_assess_portfolio,
        blofin_get_trade_insights,
        blofin_get_learned_tactics,
        blofin_research_trading_tactics,
        blofin_get_swarm_learning_report,
        blofin_list_all_instruments,
        blofin_get_equity_summary,
        blofin_technical_analysis,
        blofin_get_ticker,
    ],
)

ALL_AGENTS_LIST = [
    portfolio_agent,
    sentiment_agent,
    risk_agent,
    execution_agent,
    quant_agent,
    director_agent,
    verifier_agent,
    ops_monitor_agent,
    tactics_researcher_agent,
    profit_strategist_agent,
    market_researcher_agent,
    pentest_scout_agent,
    pentest_trade_hunter_agent,
    pentest_integrity_agent,
    pentest_operator_agent,
]


def agent_roster() -> list[dict[str, str]]:
    """All LLM agents in the swarm with role."""
    return [
        {
            "name": a.agent_name,
            "role": (
                "trading"
                if a in ALL_AGENTS
                else "pentest"
                if a in PENTEST_AGENTS
                else "support"
            ),
        }
        for a in ALL_AGENTS_LIST
    ]


def reset_agent_memories() -> None:
    """Clear short-term memory between loop cycles."""
    for agent in ALL_AGENTS_LIST:
        if hasattr(agent, "short_memory_init"):
            agent.short_memory = agent.short_memory_init()


if __name__ == "__main__":
    output = director_agent.run(
        "Scan the Blofin universe and provide a short market thesis."
    )
    print(output)
