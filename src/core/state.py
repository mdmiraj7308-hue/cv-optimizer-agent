from typing import TypedDict, Any


class UserPrefs(TypedDict):
    user_id: str
    target_roles: list[str]
    location: str         # preferred country
    job_type: str         # remote | onsite | any
    experience_level: str # internship | entry | associate | mid_senior | director | executive | any
    date_posted: str      # any_time | past_month | past_week | past_24h
    salary_min: int | None
    salary_max: int | None


class ScrapedJob(TypedDict):
    job_title: str
    company: str
    location: str
    job_url: str
    job_description_md: str
    posted_at: str | None


# ── Phase 1 ───────────────────────────────────────────────────────────────────


class EvalState(TypedDict):
    """State passed through the Phase 1 evaluation graph."""

    user_prefs: UserPrefs
    cv_text: str
    scraped_jobs: list[ScrapedJob]
    current_job: ScrapedJob | None
    score: float
    evaluation_summary: str
    saved_jobs: list[dict[str, Any]]


# ── Phase 2 ───────────────────────────────────────────────────────────────────


class OptimizeState(TypedDict):
    """State passed through the Phase 2 on-demand optimization graph."""

    cv_text: str
    job_description: str
    job_id: str
    user_id: str
    job_title: str
    company: str
    optimized_cv_html: str
    pdf_bytes: bytes
    storage_url: str
