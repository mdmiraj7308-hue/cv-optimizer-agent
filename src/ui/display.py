"""
display.py — Streamlit main panel:
  Tab 1 — Job Results: job cards with score badge, highlights, Generate CV / Download
  Tab 2 — Applied History: jobs the user has marked as applied
"""

from __future__ import annotations

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

# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_supabase():
    """Return a Supabase client, cached per access token.

    Re-creating the client and calling set_session() on every button click
    triggers a network round-trip that makes the UI feel stuck and blocks
    other widgets. Caching avoids that overhead.
    """
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


def _score_badge(score: float) -> str:
    """Return an HTML badge coloured by score threshold."""
    if score >= 70:
        bg, fg = "#2d6a2d", "#e8f5e9"
    elif score >= 50:
        bg, fg = "#7a5c00", "#fff8e1"
    else:
        bg, fg = "#8b2000", "#fce4ec"
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 10px;'
        f'border-radius:12px;font-weight:bold;font-size:0.9rem;">'
        f'{score:.0f}/100</span>'
    )


_ABOUT_THE_JOB_RE = re.compile(r"about\s+the\s+job\s*:?\s*", re.IGNORECASE)


def _extract_about_the_job(description_md: str) -> str:
    """Return the original 'About the job' section, kept as-is.

    Slices from the 'About the job' header to the end of the posting. If the
    header is not present, the full description is returned unchanged.
    """
    text = (description_md or "").strip()
    if not text:
        return ""

    match = _ABOUT_THE_JOB_RE.search(text)
    if match:
        return text[match.end():].strip()
    return text


def _optimistic_mark_applied(user_id: str, job_id: str, job: dict) -> None:
    """Persist to Supabase and update session caches so the UI reflects instantly."""
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
            *(
                h for h in history
                if h.get("processed_job_id") != job_id
            ),
        ]

    st.toast("Added to Applied History", icon="✅")


def _render_applied_button(job_id: str, user_id: str, job: dict, is_applied: bool) -> None:
    """One-click apply button with instant feedback (no full-page reload)."""
    if is_applied:
        st.button("✅ Marked as Applied", key=f"applied_{job_id}", disabled=True,
                  use_container_width=True)
        return

    if st.button("Mark as Applied", key=f"apply_{job_id}", use_container_width=True):
        with st.spinner("Saving…"):
            try:
                _optimistic_mark_applied(user_id, job_id, job)
            except Exception as exc:
                st.error(f"Could not mark as applied: {exc}")
                return
        # Full rerun (cheap — all data is cached) so the card flips to the
        # disabled state AND the Applied History tab reflects the new entry.
        st.rerun()


def _render_job_highlights(summary: str, description_md: str) -> None:
    """Render score rationale and the original 'About the job' description."""
    st.markdown("**Why this score?**")
    if summary:
        st.markdown(summary)
    else:
        st.caption("No evaluation summary available.")

    about = _extract_about_the_job(description_md)
    st.markdown("**About the job**")
    if about:
        _render_about_the_job(about)
    else:
        st.caption("No job description available for this posting.")


def _render_about_the_job(about: str) -> None:
    """Render the original description preserving its paragraph gaps and bullets.

    Converting to HTML with nl2br keeps single line breaks, blank-line paragraph
    spacing, and bullet lists exactly like the original posting.
    """
    import markdown as _md  # lazy import; declared in requirements.txt

    body_html = _md.markdown(about, extensions=["nl2br", "sane_lists"])
    st.markdown(
        f'<div class="about-job" style="line-height:1.5;">{body_html}</div>',
        unsafe_allow_html=True,
    )


# ── Tab 1 — Job Results ───────────────────────────────────────────────────────


def _render_job_card(job: dict, user_id: str, applied_ids: set[str]):
    """Render one job as an st.expander card."""
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

    label_parts = [f"**{title}**"]
    if company:
        label_parts.append(f"@ {company}")
    label = " ".join(label_parts)

    with st.expander(label, expanded=False):
        col_score, col_meta = st.columns([1, 3])
        with col_score:
            st.markdown(_score_badge(score), unsafe_allow_html=True)
        with col_meta:
            meta_parts = []
            if location:
                meta_parts.append(f"📍 {location}")
            if job_url:
                meta_parts.append(f"[🔗 See details and apply]({job_url})")
            st.markdown("  |  ".join(meta_parts) if meta_parts else "")

        st.markdown("---")
        _render_job_highlights(summary, description_md)

        st.markdown("---")

        if cv_url:
            if st.button("⬇ Download Optimized CV", key=f"dl_{job_id}"):
                mark_cv_downloaded(user_id, job_id, supabase_client=_get_supabase())
                st.markdown(
                    f'<a href="{cv_url}" target="_blank">Click here if download did not start automatically</a>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"[Open PDF]({cv_url})")
        else:
            gen_key = f"gen_{job_id}"
            if st.session_state.get(gen_key) == "generating":
                st.spinner("Generating optimized CV…")
                try:
                    resp = httpx.post(
                        f"{settings.fastapi_base_url}/api/optimize/{job_id}",
                        timeout=300,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    signed_url = data.get("signed_url", "")
                    st.session_state[gen_key] = "done"
                    st.session_state[f"cv_url_{job_id}"] = signed_url
                    st.success("Optimized CV ready!")
                    st.rerun()
                except Exception as exc:
                    st.session_state[gen_key] = "error"
                    st.error(f"Failed to generate CV: {exc}")
            else:
                if st.button(
                    "✨ Generate Optimized CV",
                    key=f"btn_gen_{job_id}",
                    disabled=(st.session_state.get(gen_key) == "generating"),
                ):
                    st.session_state[gen_key] = "generating"
                    with st.spinner("Generating optimized CV…"):
                        try:
                            resp = httpx.post(
                                f"{settings.fastapi_base_url}/api/optimize/{job_id}",
                                timeout=300,
                            )
                            resp.raise_for_status()
                            data = resp.json()
                            signed_url = data.get("signed_url", "")
                            st.session_state[gen_key] = "done"
                            st.session_state[f"cv_url_{job_id}"] = signed_url
                            st.success("Optimized CV ready!")
                            st.rerun()
                        except Exception as exc:
                            st.session_state[gen_key] = "error"
                            st.error(f"CV generation failed: {exc}")

                if st.session_state.get(gen_key) == "done":
                    signed_url = st.session_state.get(f"cv_url_{job_id}", "")
                    st.markdown(f"[⬇ Download Optimized CV (PDF)]({signed_url})")

        st.markdown("---")
        _render_applied_button(job_id, user_id, job, is_applied)


def _render_jobs_tab(user_id: str):
    st.subheader("Your Matched Jobs")

    if st.button("🔄 Refresh", key="btn_refresh_jobs"):
        st.session_state.pop("cached_jobs", None)
        st.session_state.pop("cached_applied_ids", None)

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
    applied_ids = st.session_state.get("cached_applied_ids", set())

    if not jobs:
        st.info(
            "No jobs evaluated yet. Use **Run Now** (manual mode) or wait for your scheduled scan."
        )
        return

    st.caption(f"{len(jobs)} job(s) found, sorted by compatibility score.")

    for job in jobs:
        _job_card_fragment(job, user_id)


@st.fragment
def _job_card_fragment(job: dict, user_id: str) -> None:
    """Isolated rerun scope — button clicks only refresh this card, not the whole app."""
    applied_ids = st.session_state.get("cached_applied_ids", set())
    if not isinstance(applied_ids, set):
        applied_ids = set(applied_ids)
    _render_job_card(job, user_id, applied_ids)


# ── Tab 2 — Applied History ───────────────────────────────────────────────────


def _render_history_tab(user_id: str):
    st.subheader("Applied Jobs History")

    if st.button("🔄 Refresh", key="btn_refresh_history"):
        st.session_state.pop("cached_history", None)

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
    """Render one history row; fragment keeps tab responsive on refresh actions."""
    job = entry.get("processed_jobs") or {}
    title = job.get("job_title", "Unknown")
    company = job.get("company", "")
    location = job.get("location", "")
    score = float(job.get("compatibility_score", 0))
    cv_url = job.get("optimized_cv_url")
    applied_at = entry.get("marked_applied_at", "")
    cv_downloaded = entry.get("cv_downloaded", False)

    with st.expander(f"**{title}** @ {company}", expanded=False):
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
            st.markdown(_score_badge(score), unsafe_allow_html=True)

        status_parts = []
        if cv_downloaded:
            status_parts.append("📄 CV Downloaded")
        status_parts.append("✅ Applied")
        st.markdown(" · ".join(status_parts))

        if cv_url:
            st.markdown(f"[⬇ Re-download Optimized CV]({cv_url})")


# ── Main render function (called from app.py) ─────────────────────────────────


def render_display():
    """Render the main panel tabs. Entry point called by app.py."""
    st.title("🎯 AI Career Assistant")

    if not st.session_state.get("user_id"):
        st.markdown(
            """
            ### Welcome!
            Sign in using the sidebar to get started.

            **What this app does:**
            1. Scrapes LinkedIn job postings matching your target roles every day (or on demand).
            2. Uses GPT-4o-mini to score each job's compatibility with your CV (0–100).
            3. On request, generates an ATS-optimised PDF CV tailored to any specific job.
            """
        )
        return

    user_id = st.session_state["user_id"]
    tab1, tab2 = st.tabs(["📋 Job Results", "✅ Applied History"])

    with tab1:
        _render_jobs_tab(user_id)

    with tab2:
        _render_history_tab(user_id)
