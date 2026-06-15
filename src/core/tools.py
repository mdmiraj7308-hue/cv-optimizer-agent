"""
tools.py — all I/O helpers used by the LangGraph nodes:
  - Apify LinkedIn scraper (24-hr filter)
  - Salary range parser
  - HTML-to-PDF converter (xhtml2pdf)
  - Supabase CRUD helpers
  - trigger_pipeline() for APScheduler / manual run
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import httpx
from supabase import create_client, Client

from src.config.settings import settings
from src.core.state import ScrapedJob, UserPrefs

# ── Supabase clients ──────────────────────────────────────────────────────────
# anon client — used by Streamlit (respects RLS via user JWT)
def get_anon_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_anon_key)


# service-role client — used by FastAPI backend (bypasses RLS for writes)
def get_service_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


# ── Salary parser ─────────────────────────────────────────────────────────────

def parse_salary(raw: str) -> tuple[int | None, int | None]:
    """
    Parse a free-text salary string into (min, max) integers (in full currency units).

    Supported formats:
        "50000"     → (50000, None)
        "50k"       → (50000, None)
        "50k-80k"   → (50000, 80000)
        "80k+"      → (80000, None)
        "any" / ""  → (None, None)
    """
    raw = raw.strip().lower().replace(",", "").replace("$", "").replace("£", "")

    if not raw or raw in ("any", "n/a", "-"):
        return None, None

    def to_int(s: str) -> int:
        s = s.strip()
        if s.endswith("k"):
            return int(float(s[:-1]) * 1000)
        return int(float(s))

    # Range pattern: 50k-80k or 50000-80000
    range_match = re.match(r"^(\d+\.?\d*k?)[\s\-–to]+(\d+\.?\d*k?)$", raw)
    if range_match:
        return to_int(range_match.group(1)), to_int(range_match.group(2))

    # Plus pattern: 80k+
    plus_match = re.match(r"^(\d+\.?\d*k?)\+$", raw)
    if plus_match:
        return to_int(plus_match.group(1)), None

    # Single number
    single_match = re.match(r"^(\d+\.?\d*k?)$", raw)
    if single_match:
        return to_int(single_match.group(1)), None

    return None, None


MAX_INPUT_CHARS = 100


def validate_char_limits(fields: dict[str, str], max_chars: int = MAX_INPUT_CHARS) -> list[str]:
    """Return error messages for text fields that exceed the character limit."""
    errors: list[str] = []
    for label, value in fields.items():
        count = len(value)
        if count > max_chars:
            errors.append(f"{label}: {count}/{max_chars} characters — shorten your input.")
    return errors


# Keep old names as aliases so nothing else breaks
MAX_INPUT_WORDS = MAX_INPUT_CHARS


def word_count(text: str) -> int:
    return len(text)


def validate_word_limits(fields: dict[str, str], max_words: int = MAX_INPUT_CHARS) -> list[str]:
    return validate_char_limits(fields, max_words)


# ── Apify scraper ─────────────────────────────────────────────────────────────

def scrape_linkedin_jobs(user_prefs: UserPrefs) -> list[ScrapedJob]:
    """
    Call the Apify curious_coder/linkedin-jobs-scraper actor.

    LinkedIn URL filter params:
      - f_TPR   → date posted   (r86400=24h, r604800=week, r2592000=month)
      - f_WT    → work type     (1=onsite, 2=remote)
      - f_E     → experience    (1=intern,2=entry,3=associate,4=mid-senior,5=director,6=executive)
      - location → country/city
    """
    from urllib.parse import urlencode

    country = (user_prefs.get("location") or "").strip()
    job_type = (user_prefs.get("job_type") or "any").lower()
    experience_level = (user_prefs.get("experience_level") or "any").lower()
    date_posted = (user_prefs.get("date_posted") or "any_time").lower()

    # Map our values → LinkedIn f_TPR param values
    _DATE_PARAM: dict[str, str] = {
        "past_24h": "r86400",
        "past_week": "r604800",
        "past_month": "r2592000",
    }
    # Map our values → LinkedIn f_E param values
    _EXP_PARAM: dict[str, str] = {
        "internship": "1",
        "entry": "2",
        "associate": "3",
        "mid_senior": "4",
        "director": "5",
        "executive": "6",
    }

    def _build_params(role: str) -> dict[str, str]:
        p: dict[str, str] = {"keywords": role}
        tpr = _DATE_PARAM.get(date_posted)
        if tpr:
            p["f_TPR"] = tpr
        if country:
            p["location"] = country
        if job_type == "remote":
            p["f_WT"] = "2"
        elif job_type == "onsite":
            p["f_WT"] = "1"
        exp = _EXP_PARAM.get(experience_level)
        if exp:
            p["f_E"] = exp
        return p

    urls: list[str] = [
        "https://www.linkedin.com/jobs/search/?" + urlencode(_build_params(role))
        for role in (user_prefs.get("target_roles") or [])
    ]

    if not urls:
        urls = ["https://www.linkedin.com/jobs/search/?" + urlencode(_build_params(""))]

    JOBS_PER_URL = 10       # actor scrapes 10 jobs per search URL
    MAX_URLS = 3            # user may provide at most 3 target roles
    TOTAL_JOBS_TARGET = JOBS_PER_URL * MAX_URLS  # absolute max = 30

    # Silently cap at 3 URLs so the actor never exceeds 30 jobs
    urls = urls[:MAX_URLS]

    actor_input: dict[str, Any] = {
        "urls": urls,
        "count": JOBS_PER_URL,  # actor-level field: scrape 10 per URL
    }

    # Apify URL paths require '~' between username and actor name, not '/'
    actor_id_url = settings.apify_actor_id.replace("/", "~")
    run_url = (
        f"https://api.apify.com/v2/acts/{actor_id_url}"
        f"/run-sync-get-dataset-items"
        f"?token={settings.apify_api_token}"
        f"&timeout=300"
        f"&limit={TOTAL_JOBS_TARGET}"  # dataset-level cap: return at most 30 items
    )

    with httpx.Client(timeout=320) as client:
        resp = client.post(run_url, json=actor_input)
        resp.raise_for_status()
        items: list[dict[str, Any]] = resp.json()

    jobs: list[ScrapedJob] = []
    for item in items:
        description = (
            item.get("description")
            or item.get("descriptionHtml")
            or item.get("jobDescription")
            or ""
        )
        description = re.sub(r"<[^>]+>", "", description).strip()

        # Try every field name the curious_coder actor may use for the job URL
        job_url = (
            item.get("jobUrl")
            or item.get("url")
            or item.get("link")
            or item.get("jobPostingUrl")
            or item.get("applyUrl")
            or item.get("externalApplyUrl")
            or ""
        )

        posted_at_raw = item.get("publishedAt") or item.get("postedAt") or item.get("datePosted") or ""
        jobs.append(
            ScrapedJob(
                job_title=item.get("title") or item.get("jobTitle") or item.get("position") or "Unknown Title",
                company=item.get("company") or item.get("companyName") or item.get("employer") or "",
                location=item.get("location") or item.get("jobLocation") or "",
                job_url=job_url,
                job_description_md=description,
                posted_at=posted_at_raw if posted_at_raw else None,
            )
        )

    jobs = jobs[:TOTAL_JOBS_TARGET]
    # LinkedIn URL params (f_WT, f_E, f_TPR) already filter at search level.
    # Do NOT post-filter by location text — remote jobs often show city names only.
    return jobs


# ── HTML-to-PDF generator ─────────────────────────────────────────────────────

def _render_pdf(html: str) -> bytes:
    """Render HTML to PDF bytes with xhtml2pdf (cross-platform, no GTK)."""
    from xhtml2pdf import pisa  # lazy import

    buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=buffer, encoding="utf-8")
    if status.err:
        raise RuntimeError(f"PDF generation failed with {status.err} error(s)")

    pdf_bytes = buffer.getvalue()
    if not pdf_bytes:
        raise RuntimeError("PDF generation produced empty output")

    return pdf_bytes


def _pdf_page_count(pdf_bytes: bytes) -> int:
    """Return the number of pages in a PDF; defaults to 1 on any read error."""
    try:
        from pypdf import PdfReader

        return len(PdfReader(BytesIO(pdf_bytes)).pages)
    except Exception:
        return 1


def _compact_override_css(scale: float) -> str:
    """Build an !important <style> block that shrinks the CV layout by *scale*.

    Mirrors the selectors the optimizer prompt is instructed to emit so the
    overrides reliably win the cascade and force the CV onto a single page.
    """
    body = round(10 * scale, 1)
    h1 = round(16 * scale, 1)
    h2 = round(11 * scale, 1)
    contact = round(9 * scale, 1)
    skill = round(9.5 * scale, 1)
    line_height = 1.3 if scale >= 0.92 else (1.2 if scale >= 0.82 else 1.12)
    margin_mm = 10 if scale >= 0.9 else (8 if scale >= 0.82 else 6)
    h2_top = max(4, round(10 * scale))
    return (
        "<style>"
        f"@page {{ size: A4; margin: {margin_mm}mm !important; }}"
        f"body, .cv {{ font-size: {body}pt !important; line-height: {line_height} !important; }}"
        f"h1 {{ font-size: {h1}pt !important; margin: 0 0 3px 0 !important; }}"
        f"h2 {{ font-size: {h2}pt !important; margin: {h2_top}px 0 3px 0 !important;"
        " padding-bottom: 1px !important; }"
        f"p, li {{ font-size: {body}pt !important; }}"
        f".contact {{ font-size: {contact}pt !important; }}"
        f".skill-line {{ font-size: {skill}pt !important; margin: 1px 0 !important; }}"
        "ul { margin: 2px 0 4px 0 !important; padding-left: 14px !important; }"
        "li { margin-bottom: 1px !important; }"
        ".role { margin-bottom: 4px !important; }"
        ".role-title { margin: 0 0 1px 0 !important; }"
        "</style>"
    )


def _inject_style(html: str, style: str) -> str:
    """Insert *style* so it overrides the document's existing CSS (cascade order)."""
    lowered = html.lower()
    head_close = lowered.find("</head>")
    if head_close != -1:
        return html[:head_close] + style + html[head_close:]
    body_open = lowered.find("<body")
    if body_open != -1:
        insert_at = html.find(">", body_open) + 1
        return html[:insert_at] + style + html[insert_at:]
    return style + html


def html_to_pdf(html: str) -> bytes:
    """Convert HTML to a single-page PDF.

    xhtml2pdf does not scale content to fit, so a CV that is slightly too tall
    overflows to a second page. We render once, and if the result is more than
    one page we re-render with progressively more compact styling until it fits
    (or we reach the smallest acceptable scale).
    """
    pdf_bytes = _render_pdf(html)
    if _pdf_page_count(pdf_bytes) <= 1:
        return pdf_bytes

    for scale in (0.94, 0.88, 0.82, 0.76, 0.70):
        compact_html = _inject_style(html, _compact_override_css(scale))
        candidate = _render_pdf(compact_html)
        if _pdf_page_count(candidate) <= 1:
            return candidate
        pdf_bytes = candidate  # keep the most compact attempt as fallback

    return pdf_bytes


# ── Supabase CRUD ─────────────────────────────────────────────────────────────

def save_processed_job(
    *,
    user_id: str,
    job: ScrapedJob,
    score: float,
    evaluation_summary: str,
) -> dict[str, Any]:
    """Insert a scored job into processed_jobs and return the inserted row."""
    client = get_service_client()

    record = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "job_title": job["job_title"],
        "company": job["company"],
        "location": job["location"],
        "job_url": job["job_url"],
        "job_description_md": job["job_description_md"],
        "posted_at": job.get("posted_at"),
        "compatibility_score": round(score, 2),
        "evaluation_summary": evaluation_summary,
        "optimized_cv_generated": False,
        "optimized_cv_url": None,
    }

    response = client.table("processed_jobs").insert(record).execute()
    return response.data[0] if response.data else record


def get_processed_jobs(user_id: str, supabase_client: Client | None = None) -> list[dict[str, Any]]:
    """Fetch all processed_jobs for a user, sorted by score descending."""
    client = supabase_client or get_anon_client()
    response = (
        client.table("processed_jobs")
        .select("*")
        .eq("user_id", user_id)
        .order("compatibility_score", desc=True)
        .execute()
    )
    return response.data or []


def get_job_by_id(job_id: str) -> dict[str, Any] | None:
    """Fetch a single processed_job row by its UUID."""
    client = get_service_client()
    response = (
        client.table("processed_jobs")
        .select("*")
        .eq("id", job_id)
        .maybe_single()
        .execute()
    )
    return response.data


def update_job_cv_url(job_id: str, cv_url: str) -> None:
    """Mark a job as having an optimized CV and store the signed URL."""
    client = get_service_client()
    client.table("processed_jobs").update(
        {"optimized_cv_generated": True, "optimized_cv_url": cv_url}
    ).eq("id", job_id).execute()


def get_profile(user_id: str, supabase_client: Client | None = None) -> dict[str, Any] | None:
    """Fetch a user profile row."""
    client = supabase_client or get_service_client()
    response = (
        client.table("profiles")
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return response.data


def get_all_scheduled_profiles() -> list[dict[str, Any]]:
    """Return all profiles where run_mode = 'scheduled' (used by APScheduler on startup)."""
    client = get_service_client()
    response = (
        client.table("profiles")
        .select("*")
        .eq("run_mode", "scheduled")
        .execute()
    )
    return response.data or []


def get_cv_text(user_id: str) -> str:
    """Download the user's original CV PDF from Supabase Storage and extract text."""
    import pypdf  # lazy import

    client = get_service_client()
    path = f"original/{user_id}/cv.pdf"

    try:
        pdf_bytes = client.storage.from_("cvs").download(path)
    except Exception:
        return ""

    reader = pypdf.PdfReader(BytesIO(pdf_bytes))
    text_parts = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(text_parts).strip()


def upload_optimized_cv(user_id: str, job_id: str, pdf_bytes: bytes) -> str:
    """Upload optimized CV PDF to Supabase Storage and return a signed URL (1 hour)."""
    client = get_service_client()
    path = f"optimized/{user_id}/{job_id}.pdf"

    client.storage.from_("cvs").upload(
        path,
        pdf_bytes,
        {"content-type": "application/pdf", "upsert": "true"},
    )

    signed = client.storage.from_("cvs").create_signed_url(path, expires_in=3600)
    return signed["signedURL"]


def mark_applied(
    user_id: str, job_id: str, supabase_client: Client | None = None
) -> None:
    """Upsert a row in application_tracking to mark the job as applied."""
    client = supabase_client or get_anon_client()
    client.table("application_tracking").upsert(
        {
            "user_id": user_id,
            "processed_job_id": job_id,
            "marked_applied_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,processed_job_id",
    ).execute()


def mark_cv_downloaded(
    user_id: str, job_id: str, supabase_client: Client | None = None
) -> None:
    """Set cv_downloaded = true in application_tracking."""
    client = supabase_client or get_anon_client()
    client.table("application_tracking").upsert(
        {
            "user_id": user_id,
            "processed_job_id": job_id,
            "cv_downloaded": True,
        },
        on_conflict="user_id,processed_job_id",
    ).execute()


def get_applied_job_ids(
    user_id: str, supabase_client: Client | None = None
) -> set[str]:
    """Return processed_job IDs the user has marked as applied."""
    client = supabase_client or get_anon_client()
    response = (
        client.table("application_tracking")
        .select("processed_job_id")
        .eq("user_id", user_id)
        .execute()
    )
    return {row["processed_job_id"] for row in (response.data or [])}


def get_applied_history(user_id: str, supabase_client: Client | None = None) -> list[dict[str, Any]]:
    """Return application_tracking rows joined with processed_jobs for a user."""
    client = supabase_client or get_anon_client()
    response = (
        client.table("application_tracking")
        .select("*, processed_jobs(*)")
        .eq("user_id", user_id)
        .order("marked_applied_at", desc=True)
        .execute()
    )
    return response.data or []


def delete_user_account(user_id: str) -> None:
    """
    Permanently delete all data for *user_id*:
    storage files, application_tracking, processed_jobs, profile, and auth account.
    Requires service-role key for admin operations.
    """
    client = get_service_client()

    # Remove CV files from storage
    paths_to_remove: list[str] = [f"original/{user_id}/cv.pdf"]
    try:
        optimized = client.storage.from_("cvs").list(f"optimized/{user_id}")
        paths_to_remove.extend(
            f"optimized/{user_id}/{item['name']}"
            for item in (optimized or [])
            if item.get("name")
        )
    except Exception:
        pass

    if paths_to_remove:
        try:
            client.storage.from_("cvs").remove(paths_to_remove)
        except Exception:
            pass

    client.table("application_tracking").delete().eq("user_id", user_id).execute()
    client.table("processed_jobs").delete().eq("user_id", user_id).execute()
    client.table("profiles").delete().eq("user_id", user_id).execute()
    client.auth.admin.delete_user(user_id)


# ── trigger_pipeline() ────────────────────────────────────────────────────────

def trigger_pipeline(user_id: str) -> int:
    """
    Run the full Phase 1 evaluation pipeline for *user_id* synchronously.

    Called by:
      - APScheduler (scheduled mode)
      - POST /api/run/{user_id} (manual mode)

    Returns the number of jobs that were saved.
    """
    # Avoid circular imports by importing graph lazily
    from src.workflow.graph import eval_graph

    profile = get_profile(user_id)
    if not profile:
        raise ValueError(f"No profile found for user_id={user_id}")

    cv_text = get_cv_text(user_id)

    user_prefs: UserPrefs = {
        "user_id": user_id,
        "target_roles": profile.get("target_roles") or [],
        "location": profile.get("location") or "",
        "job_type": profile.get("job_type") or "any",
        "experience_level": profile.get("experience_level") or "any",
        "date_posted": profile.get("date_posted") or "any_time",
        "salary_min": profile.get("salary_min"),
        "salary_max": profile.get("salary_max"),
    }

    initial_state = {
        "user_prefs": user_prefs,
        "cv_text": cv_text,
        "scraped_jobs": [],
        "current_job": None,
        "score": 0.0,
        "evaluation_summary": "",
        "saved_jobs": [],
    }

    final_state = eval_graph.invoke(initial_state)
    return len(final_state.get("saved_jobs", []))
