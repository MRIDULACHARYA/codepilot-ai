r"""LangGraph StateGraph wiring the agents together.

START -> intent -> router -> {debugging | code_review | explanation} -> retrieve -> static -> bug_finder -> style
      -> fixer -> tests -> validate --(tests failed & attempts < max)--> repair -> validate (bounded loop)
                                    \--(otherwise)--> report -> END

Each intent has its own plan (see ``agents.intent_router.PLANS``); conditional edges follow the plan so
steps that do not apply to an intent are not executed (and are not shown as if they were).
"""
from __future__ import annotations

from typing import Callable

from langgraph.graph import END, START, StateGraph

from agents import bug_finder, explain_agent, fixer_agent, intent_router, report_agent, style_agent, test_writer, validator
from agents.state import ReviewState, traced
from agents.static_analysis import analyze
from backend.core.config import get_settings
from rag.retriever import retrieve

BRANCH_NODES = ["debugging", "code_review", "explanation"]


@traced("router", "Request routing")
def router(state: ReviewState) -> dict:
    return {"_summary": f"Routing {state['intent']} through plan: {' → '.join(state['plan'])}."}


def _branch(name: str):
    @traced(name, f"Workflow: {name.replace('_', ' ')}")
    def node(state: ReviewState) -> dict:
        return {"_summary": f"Entered the {name.replace('_', ' ')} workflow."}

    node.__name__ = name
    return node


@traced("retrieve", "Context retrieval")
def retrieve_node(state: ReviewState) -> dict:
    res = retrieve(state["intent"], state["code"], state["language"], state.get("request", "")[:300])
    d = res.to_dict()
    n = len(res.contexts)
    return {
        "context": res.contexts, "retrieval": d,
        "_status": "completed" if res.performed else "skipped",
        "_summary": (f"Retrieved {n} passage(s) using {res.method}." if res.performed else f"Retrieval not performed: {res.reason}"),
        "_details": {"sources": [f"{c['source']} § {c['section']}" for c in res.contexts]},
    }


@traced("static", "Static code analysis")
def static_node(state: ReviewState) -> dict:
    r = analyze(state["code"], state["language"])
    sev = {}
    for f in r["findings"]:
        sev[f["severity"]] = sev.get(f["severity"], 0) + 1
    return {
        "static_findings": r["findings"], "static_metrics": r["metrics"], "static_tools": r["tools"],
        "_summary": f"{len(r['findings'])} finding(s) via {', '.join(r['tools'])}" + (f" ({sev})" if sev else "") + ".",
    }


def _next(current: str) -> Callable[[ReviewState], str]:
    def fn(state: ReviewState) -> str:
        plan = state["plan"]
        if current in plan:
            idx = plan.index(current)
            return plan[idx + 1] if idx + 1 < len(plan) else END
        return "report"

    return fn


def after_validate(state: ReviewState) -> str:
    if state.get("needs_repair") and state.get("repair_attempts", 0) < get_settings().max_repair_attempts:
        return "repair"
    return _next("validate")(state)


def to_branch(state: ReviewState) -> str:
    return intent_router.BRANCH[state["intent"]]


def build_graph():
    g = StateGraph(ReviewState)
    g.add_node("intent", intent_router.detect_intent)
    g.add_node("router", router)
    for b in BRANCH_NODES:
        g.add_node(b, _branch(b))
    g.add_node("retrieve", retrieve_node)
    g.add_node("static", static_node)
    g.add_node("bug_finder", bug_finder.run)
    g.add_node("style", style_agent.run)
    g.add_node("explain", explain_agent.run)
    g.add_node("fixer", fixer_agent.run)
    g.add_node("tests", test_writer.run)
    g.add_node("validate", validator.run)
    g.add_node("repair", fixer_agent.repair)
    g.add_node("report", report_agent.run)

    g.add_edge(START, "intent")
    g.add_edge("intent", "router")
    g.add_conditional_edges("router", to_branch, {b: b for b in BRANCH_NODES})
    for b in BRANCH_NODES:
        g.add_edge(b, "retrieve")
    g.add_conditional_edges("retrieve", _next("retrieve"), ["static"])
    all_next = ["bug_finder", "style", "explain", "fixer", "tests", "validate", "report", END]
    for n in ("static", "bug_finder", "style", "explain", "fixer", "tests"):
        g.add_conditional_edges(n, _next(n), all_next)
    g.add_conditional_edges("validate", after_validate, ["repair", "report", END])
    g.add_edge("repair", "validate")  # bounded: after_validate stops at max attempts
    g.add_edge("report", END)
    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def initial_state(code: str, language: str = "python", request: str = "", requested_intent: str | None = None,
                  sample_id: str | None = None, demo: bool = False, run_validation: bool = True) -> ReviewState:
    return {
        "code": code, "language": (language or "python").lower(), "request": request or "",
        "requested_intent": requested_intent if requested_intent and requested_intent.upper() != "AUTO" else None,
        "sample_id": sample_id, "demo": demo, "run_validation": run_validation,
        "trace": [], "notes": [], "repair_attempts": 0, "repair_log": [],
    }


def run_workflow(state: ReviewState, on_update: Callable[[ReviewState], None] | None = None) -> ReviewState:
    """Run to completion; ``on_update`` receives the full state after every node (for live progress)."""
    final: ReviewState = state
    # recursion limit: bounded repair loop (3 x [validate, repair]) + ~12 nodes, with headroom
    for snapshot in get_graph().stream(state, stream_mode="values", config={"recursion_limit": 40}):
        final = snapshot
        if on_update:
            on_update(snapshot)
    return final
