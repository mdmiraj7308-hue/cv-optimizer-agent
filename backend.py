"""
backend.py — FastAPI backend entry point.

Run with:
    uvicorn backend:fastapi_app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.config.settings import settings
from src.core.tools import (
    get_all_scheduled_profiles,
    get_processed_jobs,
    get_job_by_id,
    get_cv_text,
    trigger_pipeline,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
async def run_pipeline(user_id: str):
    """
    Manually trigger the Phase 1 evaluation pipeline for *user_id*.
    Scrapes LinkedIn jobs, evaluates each against the user's CV, and persists results.
    """
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
async def optimize_cv(job_id: str):
    """
    On-demand: generate an ATS-optimised PDF CV for the given job.
    Runs Phase 2 (optimize → pdf → upload) and returns a signed download URL.
    """
    from src.workflow.graph import optimize_graph

    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    cv_text = get_cv_text(job["user_id"])

    initial_state = {
        "cv_text": cv_text,
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
async def list_jobs(user_id: str):
    """Return all evaluated jobs for *user_id*, sorted by compatibility score."""
    try:
        jobs = get_processed_jobs(user_id)
        return {"user_id": user_id, "jobs": jobs}
    except Exception as exc:
        logger.error("list_jobs error for user_id=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@fastapi_app.post("/api/schedule/{user_id}", tags=["Scheduler"])
async def update_schedule(user_id: str, body: ScheduleRequest):
    """
    (Re)schedule a daily pipeline run for *user_id* at the given hour.
    Called automatically after the user saves a 'scheduled' run mode in the sidebar.
    """
    if not (0 <= body.run_hour <= 23):
        raise HTTPException(status_code=422, detail="run_hour must be 0–23")
    _schedule_user(user_id, body.run_hour)
    return {"message": f"User {user_id} scheduled at hour {body.run_hour}"}


@fastapi_app.delete("/api/schedule/{user_id}", tags=["Scheduler"])
async def remove_schedule(user_id: str):
    """Remove any existing scheduled pipeline job for *user_id*."""
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
