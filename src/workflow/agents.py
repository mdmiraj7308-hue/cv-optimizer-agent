"""
agents.py — LangChain agent runnables for the Evaluator and Optimizer.
Each agent is a simple (prompt | llm) chain; nodes.py invokes them.
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.core.llms import get_llm
from src.prompts.system_prompts import (
    EVALUATOR_SYSTEM_PROMPT,
    EVALUATOR_USER_TEMPLATE,
    OPTIMIZER_SYSTEM_PROMPT,
    OPTIMIZER_USER_TEMPLATE,
)

# ── Evaluator chain ───────────────────────────────────────────────────────────

_eval_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", EVALUATOR_SYSTEM_PROMPT),
        ("human", EVALUATOR_USER_TEMPLATE),
    ]
)

evaluator_chain = _eval_prompt | get_llm(temperature=0.1) | StrOutputParser()

# ── Optimizer chain ───────────────────────────────────────────────────────────

_opt_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", OPTIMIZER_SYSTEM_PROMPT),
        ("human", OPTIMIZER_USER_TEMPLATE),
    ]
)

optimizer_chain = (
    _opt_prompt
    | get_llm(temperature=0.2, max_tokens=8192)
    | StrOutputParser()
)
