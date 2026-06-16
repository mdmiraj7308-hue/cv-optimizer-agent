"""
backend.py — FastAPI backend entry point.

Run with:
    uvicorn backend:fastapi_app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.config.settings import settings
from src.core.tools import (
    get_all_scheduled_profiles,
    get_anon_client,
    get_processed_jobs,
    get_job_by_id,
    get_cv_text,
    get_cv_links,
    trigger_pipeline,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Auth & rate limiting ──────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    """Resolve the real client IP behind nginx (uses X-Forwarded-For when present)."""
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else get_remote_address(request)


limiter = Limiter(key_func=_client_ip)


async def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    """Validate the Supabase JWT in the Authorization header and return the user id.

    Every protected endpoint depends on this, so requests must carry a valid
    `Authorization: Bearer <access_token>` issued by Supabase Auth.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        resp = get_anon_client().auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    user = getattr(resp, "user", None)
    if not user or not getattr(user, "id", None):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return user.id

# ── APScheduler ───────────────────────────────────────────────────────────────

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)


def _schedule_user(user_id: str, run_hour: int) -> None:
    """Add (or replace) a daily cron job for a specific user."""
    job_id = f"eval_{user_id}"
    scheduler.add_job(
        func=_run_pipeline_job,
        trigger=CronTrigger(hour=run_hour, minute=0),
        id=job_id,
        args=[user_id],
        replace_existing=True,
        name=f"Daily eval for {user_id}",
    )
    logger.info("Scheduled daily eval for user_id=%s at hour=%d", user_id, run_hour)


def _run_pipeline_job(user_id: str) -> None:
    """Sync wrapper called by APScheduler."""
    try:
        count = trigger_pipeline(user_id)
        logger.info("Scheduled pipeline for %s — saved %d jobs", user_id, count)
    except Exception as exc:
        logger.error("Scheduled pipeline for %s failed: %s", user_id, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load scheduled users from Supabase and start the APScheduler on startup."""
    try:
        profiles = get_all_scheduled_profiles()
        for profile in profiles:
            uid = profile.get("user_id")
            hour = profile.get("run_hour")
            if uid and hour is not None:
                _schedule_user(uid, hour)
        scheduler.start()
        logger.info(
            "APScheduler started with %d scheduled users", len(scheduler.get_jobs())
        )
    except Exception as exc:
        logger.warning("Could not load scheduled profiles on startup: %s", exc)

    yield

    scheduler.shutdown(wait=False)


# ── FastAPI app ───────────────────────────────────────────────────────────────

fastapi_app = FastAPI(
    title="AI Career Automation Assistant — API",
    description="Backend for the AI career assistant: job scraping, evaluation, and CV optimisation.",
    version="1.0.0",
    lifespan=lifespan,
)

fastapi_app.state.limiter = limiter
fastapi_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Only the app's own origin(s) may call the API from a browser. The Streamlit
# server talks to FastAPI server-to-server (no CORS), so this list can stay tight.
_allowed_origins = list(
    {
        settings.streamlit_base_url,
        settings.fastapi_base_url,
        "http://localhost:8501",
        "http://localhost:10000",
    }
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Response models ───────────────────────────────────────────────────────────

class RunResponse(BaseModel):
    user_id: str
    jobs_saved: int
    message: str


class OptimizeResponse(BaseModel):
    job_id: str
    signed_url: str
    message: str


class ScheduleRequest(BaseModel):
    run_hour: int  # 0–23


# ── Endpoints ─────────────────────────────────────────────────────────────────


@fastapi_app.post("/api/run/{user_id}", response_model=RunResponse, tags=["Pipeline"])
@limiter.limit("10/hour")
async def run_pipeline(
    request: Request,
    user_id: str,
    caller_id: str = Depends(get_current_user_id),
):
    """
    Manually trigger the Phase 1 evaluation pipeline for *user_id*.
    Scrapes LinkedIn jobs, evaluates each against the user's CV, and persists results.
    """
    if caller_id != user_id:
        raise HTTPException(status_code=403, detail="You can only run your own pipeline.")
    try:
        loop = asyncio.get_event_loop()
        count = await loop.run_in_executor(None, trigger_pipeline, user_id)
        return RunResponse(
            user_id=user_id,
            jobs_saved=count,
            message=f"Pipeline complete. {count} new job(s) evaluated and saved.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Pipeline error for user_id=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}")


@fastapi_app.post("/api/optimize/{job_id}", response_model=OptimizeResponse, tags=["CV"])
@limiter.limit("20/hour")
async def optimize_cv(
    request: Request,
    job_id: str,
    caller_id: str = Depends(get_current_user_id),
):
    """
    On-demand: generate an ATS-optimised PDF CV for the given job.
    Runs Phase 2 (optimize → pdf → upload) and returns a signed download URL.
    """
    from src.workflow.graph import optimize_graph

    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job["user_id"] != caller_id:
        raise HTTPException(status_code=403, detail="This job does not belong to you.")

    cv_text = get_cv_text(job["user_id"])
    cv_links = get_cv_links(job["user_id"])

    initial_state = {
        "cv_text": cv_text,
        "cv_links": cv_links,
        "job_description": job.get("job_description_md", ""),
        "job_id": job_id,
        "user_id": job["user_id"],
        "job_title": job.get("job_title", ""),
        "company": job.get("company", ""),
        "optimized_cv_html": "",
        "pdf_bytes": b"",
        "storage_url": "",
    }

    try:
        loop = asyncio.get_event_loop()
        final_state = await loop.run_in_executor(
            None, lambda: optimize_graph.invoke(initial_state)
        )
    except Exception as exc:
        logger.error("Optimize error for job_id=%s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail=f"Optimization failed: {exc}")

    signed_url = final_state.get("storage_url", "")
    return OptimizeResponse(
        job_id=job_id,
        signed_url=signed_url,
        message="Optimized CV generated successfully.",
    )


@fastapi_app.get("/api/jobs/{user_id}", tags=["Jobs"])
async def list_jobs(user_id: str, caller_id: str = Depends(get_current_user_id)):
    """Return all evaluated jobs for *user_id*, sorted by compatibility score."""
    if caller_id != user_id:
        raise HTTPException(status_code=403, detail="You can only view your own jobs.")
    try:
        jobs = get_processed_jobs(user_id)
        return {"user_id": user_id, "jobs": jobs}
    except Exception as exc:
        logger.error("list_jobs error for user_id=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@fastapi_app.post("/api/schedule/{user_id}", tags=["Scheduler"])
async def update_schedule(
    user_id: str,
    body: ScheduleRequest,
    caller_id: str = Depends(get_current_user_id),
):
    """
    (Re)schedule a daily pipeline run for *user_id* at the given hour.
    Called automatically after the user saves a 'scheduled' run mode in the sidebar.
    """
    if caller_id != user_id:
        raise HTTPException(status_code=403, detail="You can only schedule your own runs.")
    if not (0 <= body.run_hour <= 23):
        raise HTTPException(status_code=422, detail="run_hour must be 0–23")
    _schedule_user(user_id, body.run_hour)
    return {"message": f"User {user_id} scheduled at hour {body.run_hour}"}


@fastapi_app.delete("/api/schedule/{user_id}", tags=["Scheduler"])
async def remove_schedule(user_id: str, caller_id: str = Depends(get_current_user_id)):
    """Remove any existing scheduled pipeline job for *user_id*."""
    if caller_id != user_id:
        raise HTTPException(status_code=403, detail="You can only modify your own schedule.")
    job_id = f"eval_{user_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        return {"message": f"Schedule removed for user {user_id}"}
    return {"message": f"No active schedule for user {user_id}"}


@fastapi_app.get("/health", tags=["Meta"])
async def health():
    return {"status": "ok"}


@fastapi_app.get("/auth/confirm", response_class=HTMLResponse, tags=["Auth"])
async def auth_confirm():
    """
    Landing page after Supabase email verification.
    Supabase redirects here with tokens or errors in the URL hash.
    """
    from src.ui.auth_confirm_page import build_auth_confirm_html

    return HTMLResponse(
        build_auth_confirm_html(streamlit_url=settings.streamlit_base_url)
    )
