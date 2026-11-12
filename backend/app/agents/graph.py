"""LangGraph definition of the SolveX audit workflow with persistent checkpointing and a human-review interrupt."""
from __future__ import annotations

from typing import Callable

from langgraph.graph import END, START, StateGraph

from app.agents import (anomaly_agent, decision_agent, explanation_agent, extraction_agent, filing_agent, report_agent,
                        validation_agent, xbrl_agent)
from app.agents.state import AuditState, Deps

NODES: list[tuple[str, Callable]] = [
    ("sec_retrieval", filing_agent.retrieve),                 # 1  Filing Retrieval Agent
    ("parsing", filing_agent.parse),                          # 2  Parsing Agent
    ("extraction", extraction_agent.extract),                 # 3  Financial Extraction Agent (+ Evidence Verification)
    ("confidence", extraction_agent.confidence),              # 4  Confidence Scoring Node
    ("validation", validation_agent.validate),                # 5  Validation Agent
    ("anomaly", anomaly_agent.anomalies),                     # 6  Anomaly Detection Agent
    ("xbrl_verification", xbrl_agent.verify),                 # 7  XBRL Verification Agent
    ("decision", decision_agent.decision),                    # 8  Decision Engine
    ("explainability", explanation_agent.explain),            # 9  Explainability Agent (runs BEFORE the pause so reviewers see it)
    ("review_preparation", decision_agent.review_preparation),  # 10 Human review preparation
    ("human_review", decision_agent.human_review),            # 11 Human Review Interrupt (checkpoint + pause)
    ("post_review", decision_agent.post_review),              # 12 Post-review revalidation on reviewer-resolved values
    ("report", report_agent.report),                          # 13 Report Generation Agent
]


def build_graph(deps: Deps, checkpointer):
    g = StateGraph(AuditState)
    for name, fn in NODES:
        g.add_node(name, (lambda state, _fn=fn: _fn(deps, state["workflow_id"]) or {}))
    g.add_edge(START, NODES[0][0])
    for (a, _), (b, _) in zip(NODES, NODES[1:]):
        g.add_edge(a, b)
    g.add_edge(NODES[-1][0], END)
    return g.compile(checkpointer=checkpointer)
