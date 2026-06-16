"""
nodes.py — LangGraph node functions for both Phase 1 (eval_graph) and
           Phase 2 (optimize_graph).
"""

from __future__ import annotations

import json
import logging

from src.core.llms import TokenUsageLogger
from src.core.state import EvalState, OptimizeState
from src.core.tools import (
    scrape_linkedin_jobs,
    save_processed_job,
    html_to_pdf,
    upload_optimized_cv,
    update_job_cv_url,
)
from src.workflow.agents import evaluator_chain, optimizer_chain

logger = logging.getLogger(__name__)

# ── Phase 1 nodes ─────────────────────────────────────────────────────────────


def scrape_node(state: EvalState) -> EvalState:
    """Scrape LinkedIn jobs via Apify and store them in state.scraped_jobs."""
    logger.info(
        "scrape_node: fetching jobs for user_id=%s", state["user_prefs"]["user_id"]
    )
    jobs = scrape_linkedin_jobs(state["user_prefs"])
    logger.info("scrape_node: found %d jobs", len(jobs))
    return {**state, "scraped_jobs": jobs}


def evaluator_node(state: EvalState) -> EvalState:
    """
    Evaluate ALL scraped jobs in one pass.

    For each job: call the evaluator chain, parse the JSON response,
    persist the result to Supabase, and accumulate into saved_jobs.
    """
    user_prefs = state["user_prefs"]
    cv_text = state["cv_text"]
    saved: list[dict] = []

    salary_parts = []
    if user_prefs.get("salary_min"):
        salary_parts.append(f"min {user_prefs['salary_min']:,}")
    if user_prefs.get("salary_max"):
        salary_parts.append(f"max {user_prefs['salary_max']:,}")
    salary_range = " – ".join(salary_parts) if salary_parts else "any"

    for job in state["scraped_jobs"]:
        try:
            raw_output = evaluator_chain.invoke(
                {
                    "cv_text": cv_text or "(No CV provided)",
                    "job_title": job["job_title"],
                    "company": job["company"],
                    "location": job["location"],
                    "job_description_md": job["job_description_md"],
                    "target_roles": ", ".join(user_prefs["target_roles"]),
                    "preferred_country": user_prefs["location"],
                    "job_type": user_prefs.get("job_type", "any"),
                    "experience_level": user_prefs.get("experience_level", "any"),
                    "date_posted": user_prefs.get("date_posted", "any_time"),
                    "salary_range": salary_range,
                },
                config={"callbacks": [TokenUsageLogger("evaluator")]},
            )

            # The LLM should return plain JSON; strip accidental fences
            raw_output = raw_output.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data = json.loads(raw_output)
            score = float(data.get("score", 0))
            summary = str(data.get("evaluation_summary", ""))
        except Exception as exc:
            logger.warning("evaluator_node: failed for job %s — %s", job["job_title"], exc)
            score = 0.0
            summary = f"Evaluation error: {exc}"

        try:
            row = save_processed_job(
                user_id=user_prefs["user_id"],
                job=job,
                score=score,
                evaluation_summary=summary,
            )
            saved.append(row)
        except Exception as exc:
            logger.error("evaluator_node: failed to save job %s — %s", job["job_title"], exc)

    logger.info("evaluator_node: saved %d jobs", len(saved))
    return {
        **state,
        "saved_jobs": saved,
        "score": saved[-1].get("compatibility_score", 0.0) if saved else 0.0,
        "evaluation_summary": saved[-1].get("evaluation_summary", "") if saved else "",
    }


# ── Phase 2 nodes ─────────────────────────────────────────────────────────────


def _format_cv_links(links: list[dict] | None) -> str:
    """Render extracted CV hyperlinks as a compact list for the optimizer prompt."""
    if not links:
        return "(No embedded links found in the original CV.)"
    lines = []
    for link in links:
        anchor = (link.get("anchor") or "").strip() or "(no anchor text)"
        context = (link.get("context") or "").strip()
        url = (link.get("url") or "").strip()
        if not url:
            continue
        entry = f'- anchor: "{anchor}" | url: {url}'
        if context:
            entry += f' | context: "{context}"'
        lines.append(entry)
    return "\n".join(lines) if lines else "(No embedded links found in the original CV.)"


def optimizer_node(state: OptimizeState) -> OptimizeState:
    """Call the optimizer chain to rewrite the CV as ATS-optimised HTML."""
    logger.info("optimizer_node: generating optimized CV for job_id=%s", state["job_id"])

    html = optimizer_chain.invoke(
        {
            "cv_text": state["cv_text"] or "(No CV provided)",
            "cv_links": _format_cv_links(state.get("cv_links")),
            "job_title": state.get("job_title", ""),
            "company": state.get("company", ""),
            "job_description_md": state["job_description"],
        },
        config={"callbacks": [TokenUsageLogger("optimizer")]},
    )

    # Strip accidental markdown fences the model may add
    html = html.strip()
    if html.startswith("```"):
        html = html.split("\n", 1)[-1]
    if html.endswith("```"):
        html = html.rsplit("```", 1)[0]

    return {**state, "optimized_cv_html": html.strip()}


def pdf_node(state: OptimizeState) -> OptimizeState:
    """Convert the HTML CV to PDF bytes."""
    logger.info("pdf_node: rendering PDF for job_id=%s", state["job_id"])
    pdf_bytes = html_to_pdf(state["optimized_cv_html"])
    return {**state, "pdf_bytes": pdf_bytes}


def upload_node(state: OptimizeState) -> OptimizeState:
    """Upload the PDF to Supabase Storage and update processed_jobs."""
    logger.info("upload_node: uploading PDF for job_id=%s", state["job_id"])

    signed_url = upload_optimized_cv(
        user_id=state["user_id"],
        job_id=state["job_id"],
        pdf_bytes=state["pdf_bytes"],
    )
    update_job_cv_url(state["job_id"], signed_url)

    logger.info("upload_node: uploaded → %s", signed_url)
    return {**state, "storage_url": signed_url}
