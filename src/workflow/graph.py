"""
graph.py — Two compiled LangGraph StateGraphs:

  eval_graph     — Phase 1: scrape → evaluate+save  (triggered by scheduler / manual run)
  optimize_graph — Phase 2: optimize → pdf → upload  (triggered on-demand per job)
"""

from langgraph.graph import StateGraph, END

from src.core.state import EvalState, OptimizeState
from src.workflow.nodes import (
    scrape_node,
    evaluator_node,
    optimizer_node,
    pdf_node,
    upload_node,
)

# ── Phase 1: eval_graph ───────────────────────────────────────────────────────

_eval_builder = StateGraph(EvalState)

_eval_builder.add_node("scrape", scrape_node)
_eval_builder.add_node("evaluate", evaluator_node)

_eval_builder.set_entry_point("scrape")
_eval_builder.add_edge("scrape", "evaluate")
_eval_builder.add_edge("evaluate", END)

eval_graph = _eval_builder.compile()

# ── Phase 2: optimize_graph ───────────────────────────────────────────────────

_opt_builder = StateGraph(OptimizeState)

_opt_builder.add_node("optimize", optimizer_node)
_opt_builder.add_node("pdf", pdf_node)
_opt_builder.add_node("upload", upload_node)

_opt_builder.set_entry_point("optimize")
_opt_builder.add_edge("optimize", "pdf")
_opt_builder.add_edge("pdf", "upload")
_opt_builder.add_edge("upload", END)

optimize_graph = _opt_builder.compile()
