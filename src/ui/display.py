"""
display.py — Streamlit main panel:
  Tab 1 — Job Results: KPI row + SaaS job cards
  Tab 2 — Applied History: jobs the user has marked as applied
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import streamlit as st
import httpx
from supabase import create_client

from src.config.settings import settings
from src.core.tools import (
    get_processed_jobs,
    get_applied_history,
    get_applied_job_ids,
    mark_applied,
    mark_cv_downloaded,
)
from src.ui.theme import (
    detail_panel,
    hero_title,
    kpi_row,
    score_badge_html,
    score_progress_bar,
    section_header,
    welcome_card,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_supabase():
    """Return a Supabase client, cached per access token."""
    token = st.session_state.get("access_token")
    if (
        st.session_state.get("_sb_client") is not None
        and st.session_state.get("_sb_token") == token
    ):
        return st.session_state["_sb_client"]

    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    if token:
        client.auth.set_session(token, st.session_state.get("refresh_token", ""))

    st.session_state["_sb_client"] = client
    st.session_state["_sb_token"] = token
    return client


_ABOUT_THE_JOB_RE = re.compile(r"about\s+the\s+job\s*:?\s*", re.IGNORECASE)


def _extract_about_the_job(description_md: str) -> str:
    text = (description_md or "").strip()
    if not text:
        return ""
    match = _ABOUT_THE_JOB_RE.search(text)
    if match:
        return text[match.end():].strip()
    return text


def _optimistic_mark_applied(user_id: str, job_id: str, job: dict) -> None:
    mark_applied(user_id, job_id, supabase_client=_get_supabase())

    applied_ids = st.session_state.get("cached_applied_ids", set())
    if not isinstance(applied_ids, set):
        applied_ids = set(applied_ids)
    applied_ids.add(job_id)
    st.session_state["cached_applied_ids"] = applied_ids

    entry = {
        "processed_job_id": job_id,
        "marked_applied_at": datetime.now(timezone.utc).isoformat(),
        "cv_downloaded": False,
        "processed_jobs": job,
    }
    history = st.session_state.get("cached_history")
    if history is None:
        st.session_state["cached_history"] = [entry]
    else:
        st.session_state["cached_history"] = [
            entry,
            *(h for h in history if h.get("processed_job_id") != job_id),
        ]

    st.toast("Added to Applied History", icon="✅")


def _render_applied_button(job_id: str, user_id: str, job: dict, is_applied: bool) -> None:
    if is_applied:
        st.button(
            "✅ Marked as Applied",
            key=f"applied_{job_id}",
            disabled=True,
            use_container_width=True,
        )
        return

    if st.button("Mark as Applied", key=f"apply_{job_id}", use_container_width=True):
        with st.spinner("Saving…"):
            try:
                _optimistic_mark_applied(user_id, job_id, job)
            except Exception as exc:
                st.error(f"Could not mark as applied: {exc}")
                return
        # Rerun ONLY this card (not the whole app) so the page keeps its styling
        # and the active tab doesn't reset. The history cache is already updated.
        st.rerun(scope="fragment")


def _render_about_the_job(about: str) -> None:
    import markdown as _md

    body_html = _md.markdown(about, extensions=["nl2br", "sane_lists"])
    st.markdown(
        '<div style="background:rgba(15,23,42,0.4);border:1px solid rgba(99,102,241,0.1);'
        'border-radius:8px;padding:1rem;line-height:1.55;font-size:0.88rem;'
        f'max-height:420px;overflow-y:auto;">{body_html}</div>',
        unsafe_allow_html=True,
    )


def _count_tailored_cvs(jobs: list[dict]) -> int:
    count = sum(1 for j in jobs if j.get("optimized_cv_url"))
    for j in jobs:
        jid = j.get("id", "")
        if st.session_state.get(f"gen_{jid}") == "done":
            count += 1 if not j.get("optimized_cv_url") else 0
    return count


# ── Job card ──────────────────────────────────────────────────────────────────


def _render_job_card(job: dict, user_id: str, applied_ids: set[str]):
    title = job.get("job_title", "Unknown")
    company = job.get("company", "")
    location = job.get("location", "")
    job_url = job.get("job_url", "")
    score = float(job.get("compatibility_score", 0))
    summary = job.get("evaluation_summary", "")
    description_md = job.get("job_description_md", "")
    job_id = job.get("id", "")
    cv_url = job.get("optimized_cv_url")
    is_applied = job_id in applied_ids
    salary = (st.session_state.get("profile") or {}).get("salary_raw") or "—"

    label = f"[{score:.0f}%]  {title}"
    if company:
        label += f"  @  {company}"

    with st.expander(label, expanded=False):
        st.markdown(score_progress_bar(score), unsafe_allow_html=True)

        # ── 3-column SaaS layout ──────────────────────────────────────────────
        col_details, col_insight, col_actions = st.columns([1.2, 1.5, 1])

        details_body = f"<p><strong>📍 Location</strong><br>{html.escape(location or '—')}</p>"
        details_body += f"<p><strong>💰 Salary filter</strong><br>{html.escape(salary)}</p>"
        if job_url:
            details_body += (
                f'<p><a href="{html.escape(job_url)}" target="_blank" '
                f'style="color:#818CF8;">🔗 View on LinkedIn</a></p>'
            )

        insight_body = (
            f"<p>{html.escape(summary or 'No evaluation summary available.')}</p>"
        )

        with col_details:
            st.markdown(detail_panel("Details", details_body), unsafe_allow_html=True)
        with col_insight:
            st.markdown(
                detail_panel("AI Match Insight", insight_body),
                unsafe_allow_html=True,
            )
        with col_actions:
            st.markdown(
                detail_panel("Actions", "<p>Use the buttons below ↓</p>"),
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # ── About the job (full width) ────────────────────────────────────────
        section_header("About the job")
        about = _extract_about_the_job(description_md)
        if about:
            _render_about_the_job(about)
        else:
            st.caption("No job description available for this posting.")

        st.markdown("---")

        # ── CV actions ────────────────────────────────────────────────────────
        if cv_url:
            if st.button("⬇ Download Tailored CV", key=f"dl_{job_id}", use_container_width=True):
                mark_cv_downloaded(user_id, job_id, supabase_client=_get_supabase())
                st.markdown(
                    f'<a href="{cv_url}" target="_blank" style="color:#818CF8;">'
                    f'Click here if download did not start</a>',
                    unsafe_allow_html=True,
                )
        else:
            gen_key = f"gen_{job_id}"
            if st.session_state.get(gen_key) == "done":
                signed_url = st.session_state.get(f"cv_url_{job_id}", "")
                st.success("Tailored CV ready!")
                st.markdown(f"[⬇ Download Tailored CV (PDF)]({signed_url})")
            else:
                if st.button(
                    "✨ Generate Tailored CV",
                    key=f"btn_gen_{job_id}",
                    use_container_width=True,
                    type="primary",
                ):
                    with st.spinner("Generating your tailored CV… (~20s)"):
                        try:
                            resp = httpx.post(
                                f"{settings.fastapi_base_url}/api/optimize/{job_id}",
                                timeout=300,
                            )
                            resp.raise_for_status()
                            data = resp.json()
                            st.session_state[gen_key] = "done"
                            st.session_state[f"cv_url_{job_id}"] = data.get("signed_url", "")
                        except Exception as exc:
                            st.error(f"Failed to generate CV: {exc}")
                            st.stop()
                    # Refresh only this card so the page keeps its design/tab.
                    st.rerun(scope="fragment")

        if job_url:
            st.link_button("🌐 Apply on LinkedIn", job_url, use_container_width=True)

        _render_applied_button(job_id, user_id, job, is_applied)


@st.fragment
def _job_card_fragment(job: dict, user_id: str) -> None:
    applied_ids = st.session_state.get("cached_applied_ids", set())
    if not isinstance(applied_ids, set):
        applied_ids = set(applied_ids)
    _render_job_card(job, user_id, applied_ids)


# ── Tab 1 — Job Results ───────────────────────────────────────────────────────


def _render_jobs_tab(user_id: str):
    col_title, col_refresh = st.columns([4, 1])
    with col_title:
        section_header("Your Matched Jobs", "📋")
    with col_refresh:
        if st.button("🔄 Refresh", key="btn_refresh_jobs", use_container_width=True):
            st.session_state.pop("cached_jobs", None)
            st.session_state.pop("cached_applied_ids", None)
            st.rerun()

    if "cached_jobs" not in st.session_state or st.session_state.get("jobs_refreshed"):
        with st.spinner("Loading jobs…"):
            try:
                sb = _get_supabase()
                jobs = get_processed_jobs(user_id, supabase_client=sb)
                applied_ids = get_applied_job_ids(user_id, supabase_client=sb)
                st.session_state["cached_jobs"] = jobs
                st.session_state["cached_applied_ids"] = applied_ids
                st.session_state["jobs_refreshed"] = False
            except Exception as exc:
                st.error(f"Failed to load jobs: {exc}")
                return

    jobs = st.session_state.get("cached_jobs", [])

    if not jobs:
        st.info(
            "No jobs evaluated yet. Use **Run Now** in the sidebar or wait for your scheduled scan."
        )
        return

    top = jobs[0]
    kpi_row(
        total_jobs=len(jobs),
        top_score=float(top.get("compatibility_score", 0)),
        top_company=top.get("company", ""),
        cvs_tailored=_count_tailored_cvs(jobs),
        period_label="Sorted by compatibility",
    )

    for job in jobs:
        _job_card_fragment(job, user_id)


# ── Tab 2 — Applied History ───────────────────────────────────────────────────


def _render_history_tab(user_id: str):
    col_title, col_refresh = st.columns([4, 1])
    with col_title:
        section_header("Applied Jobs History", "✅")
    with col_refresh:
        if st.button("🔄 Refresh", key="btn_refresh_history", use_container_width=True):
            st.session_state.pop("cached_history", None)
            st.rerun()

    if "cached_history" not in st.session_state:
        with st.spinner("Loading history…"):
            try:
                sb = _get_supabase()
                history = get_applied_history(user_id, supabase_client=sb)
                st.session_state["cached_history"] = history
            except Exception as exc:
                st.error(f"Failed to load history: {exc}")
                return

    history = st.session_state.get("cached_history", [])

    if not history:
        st.info("You haven't marked any jobs as applied yet.")
        return

    for entry in history:
        _history_entry_fragment(entry)


@st.fragment
def _history_entry_fragment(entry: dict) -> None:
    job = entry.get("processed_jobs") or {}
    title = job.get("job_title", "Unknown")
    company = job.get("company", "")
    location = job.get("location", "")
    score = float(job.get("compatibility_score", 0))
    cv_url = job.get("optimized_cv_url")
    applied_at = entry.get("marked_applied_at", "")
    cv_downloaded = entry.get("cv_downloaded", False)

    label = f"[{score:.0f}%]  {title}  @  {company}"

    with st.expander(label, expanded=False):
        st.markdown(score_progress_bar(score), unsafe_allow_html=True)
        col1, col2 = st.columns([2, 1])
        with col1:
            if location:
                st.markdown(f"📍 {location}")
            if applied_at:
                try:
                    dt = datetime.fromisoformat(applied_at.replace("Z", "+00:00"))
                    st.caption(f"Applied: {dt.strftime('%B %d, %Y at %H:%M %Z')}")
                except Exception:
                    st.caption(f"Applied: {applied_at}")
        with col2:
            st.markdown(score_badge_html(score), unsafe_allow_html=True)

        status = "📄 CV Downloaded · ✅ Applied" if cv_downloaded else "✅ Applied"
        st.markdown(status)

        if cv_url:
            st.link_button("⬇ Re-download Tailored CV", cv_url, use_container_width=True)


# ── Main render ───────────────────────────────────────────────────────────────


def render_display():
    hero_title("AI Career Assistant", "Smart job matching · ATS-optimised CVs · One-click apply tracking")

    if not st.session_state.get("user_id"):
        welcome_card()
        return

    user_id = st.session_state["user_id"]
    tab1, tab2 = st.tabs(["📋  Job Results", "✅  Applied History"])

    with tab1:
        _render_jobs_tab(user_id)

    with tab2:
        _render_history_tab(user_id)
