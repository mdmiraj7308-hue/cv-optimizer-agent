# AI Career Automation Assistant

A production-grade, multi-tenant AI career assistant that scrapes LinkedIn jobs via Apify, evaluates each posting against your CV using GPT-4o-mini, and on-demand generates an ATS-optimised PDF CV for any job — all inside a Streamlit + FastAPI app backed by Supabase.

---

## Quick Start

```bash
# 1. Clone and enter the repo
git clone <repo-url> && cd Job_Finder

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy env template and fill in your secrets
cp .env.example .env
# edit .env with your real keys

# 5. Run the Supabase SQL below in your project's SQL Editor

# 6. Start FastAPI backend (terminal 1)
uvicorn backend:fastapi_app --reload --port 8000

# 7. Start Streamlit frontend (terminal 2)
streamlit run app.py
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI secret key |
| `OPENAI_MODEL` | Model name (default `gpt-4o-mini`) |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon/public key (used by Streamlit) |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role key (used by FastAPI backend only) |
| `APIFY_API_TOKEN` | Apify API token |
| `APIFY_ACTOR_ID` | Apify actor ID (default `curious_coder/linkedin-jobs-scraper`) |
| `FASTAPI_BASE_URL` | Internal URL Streamlit uses to reach FastAPI (default `http://localhost:8000`) |
| `STREAMLIT_BASE_URL` | Streamlit app URL for the welcome page button (default `http://localhost:8501`) |
| `AUTH_CONFIRM_URL` | Email verification redirect URL (default `http://localhost:8000/auth/confirm`) |
| `SCHEDULER_TIMEZONE` | IANA timezone for APScheduler cron jobs (default `UTC`) |

---

## Supabase Auth — Email Verification

After sign-up, Supabase sends a confirmation email. Configure these in your Supabase dashboard under **Authentication → URL Configuration**:

| Setting | Value |
|---|---|
| **Site URL** | `http://localhost:8000/auth/confirm` |
| **Redirect URLs** | `http://localhost:8000/auth/confirm` |

Also add `http://localhost:8501` to Redirect URLs if you use Streamlit directly.

**Important:**
1. **FastAPI must be running** when you click the email link (`uvicorn backend:fastapi_app --reload --port 8000`).
2. Confirmation links **expire** (usually after 1 hour). If you see `otp_expired`, sign up again to get a fresh email.
3. After verifying, you'll see a **Welcome to Job Finder** page with a button to open the app.

Optional `.env` overrides:

```env
AUTH_CONFIRM_URL=http://localhost:8000/auth/confirm
STREAMLIT_BASE_URL=http://localhost:8501
```

---

## Supabase Setup

Run the following SQL in your Supabase project's **SQL Editor** (Database → SQL Editor → New query).

### 1. Enable UUID extension

```sql
create extension if not exists "uuid-ossp";
```

### 2. `profiles` table

```sql
create table public.profiles (
    user_id     uuid primary key references auth.users(id) on delete cascade,
    target_roles text[]          not null default '{}',
    location    text             not null default '',  -- preferred country
    job_type    text             not null default 'any'
                    check (job_type in ('any', 'remote', 'onsite')),
    salary_min  integer,
    salary_max  integer,
    salary_raw  text             not null default '',
    run_mode    text             not null default 'manual'
                    check (run_mode in ('scheduled', 'manual')),
    run_hour    integer          check (run_hour between 0 and 23),
    original_cv_url text,
    created_at  timestamptz      not null default now()
);

alter table public.profiles enable row level security;

create policy "Users manage own profile"
    on public.profiles
    for all
    using  (auth.uid() = user_id)
    with check (auth.uid() = user_id);
```

> **Existing projects:** if your `profiles` table was created before `job_type` was added, run:
> ```sql
> alter table public.profiles
>   add column if not exists job_type text not null default 'any'
>   check (job_type in ('any', 'remote', 'onsite'));
> ```

### 3. `processed_jobs` table

```sql
create table public.processed_jobs (
    id                      uuid primary key default uuid_generate_v4(),
    user_id                 uuid not null references public.profiles(user_id) on delete cascade,
    job_title               text not null,
    company                 text not null default '',
    location                text not null default '',
    job_url                 text not null default '',
    job_description_md      text not null default '',
    posted_at               timestamptz,
    compatibility_score     float not null default 0,
    evaluation_summary      text not null default '',
    optimized_cv_generated  boolean not null default false,
    optimized_cv_url        text,
    processed_at            timestamptz not null default now()
);

alter table public.processed_jobs enable row level security;

create policy "Users read own jobs"
    on public.processed_jobs
    for select
    using (auth.uid() = user_id);

create policy "Service role insert/update jobs"
    on public.processed_jobs
    for all
    using (true)
    with check (true);
```

> **Note**: The `service role insert/update` policy allows the FastAPI backend (which uses the service-role key) to write job records on behalf of any user. The `select` policy ensures users can only read their own jobs via the anon key in Streamlit.

### 4. `application_tracking` table

```sql
create table public.application_tracking (
    id                  uuid primary key default uuid_generate_v4(),
    user_id             uuid not null references public.profiles(user_id) on delete cascade,
    processed_job_id    uuid not null references public.processed_jobs(id) on delete cascade,
    marked_applied_at   timestamptz not null default now(),
    cv_downloaded       boolean not null default false,
    unique (user_id, processed_job_id)
);

alter table public.application_tracking enable row level security;

create policy "Users manage own applications"
    on public.application_tracking
    for all
    using  (auth.uid() = user_id)
    with check (auth.uid() = user_id);
```

### 5. Storage bucket `cvs`

```sql
-- Create the bucket (you can also do this in the Supabase dashboard: Storage → New bucket)
insert into storage.buckets (id, name, public)
values ('cvs', 'cvs', false);

-- Allow authenticated users to upload/read their own files
create policy "Users manage own CVs"
    on storage.objects
    for all
    using  (bucket_id = 'cvs' and auth.uid()::text = (storage.foldername(name))[2])
    with check (bucket_id = 'cvs' and auth.uid()::text = (storage.foldername(name))[2]);

-- Allow the service role unrestricted access (used by FastAPI to upload optimized CVs)
create policy "Service role manages all CVs"
    on storage.objects
    for all
    using (bucket_id = 'cvs')
    with check (bucket_id = 'cvs');
```

Storage path convention:
- `original/{user_id}/cv.pdf` — CV uploaded by user
- `optimized/{user_id}/{job_id}.pdf` — ATS-optimised CV generated on demand

---

## Architecture

```
Streamlit (sidebar.py + display.py)
        ↕ httpx
FastAPI (app.py) + APScheduler
        ↕
LangGraph Phase 1: eval_graph   → Apify → OpenAI → Supabase (processed_jobs)
LangGraph Phase 2: optimize_graph → OpenAI → xhtml2pdf → Supabase Storage
```

### Phase 1 — Job Evaluation (automatic)

Triggered either by the APScheduler cron job (scheduled mode) or by the user clicking **Run Now** (manual mode).

1. Scrapes LinkedIn jobs posted in the last 24 hours via the Apify actor.
2. For each job, calls GPT-4o-mini to produce a compatibility score (0–100) and a short evaluation summary.
3. Saves every job + score to `processed_jobs`.

### Phase 2 — CV Optimisation (on-demand)

Triggered when the user clicks **Generate Optimized CV** on a specific job card.

1. Calls GPT-4o-mini to rewrite the user's CV in ATS-friendly HTML, tailored to the job description.
2. Renders the HTML to PDF with xhtml2pdf.
3. Uploads the PDF to Supabase Storage and returns a signed download URL.

---

## Docker

```bash
docker build -t career-advisor .
docker run -p 8000:8000 --env-file .env career-advisor
```

To run Streamlit instead of FastAPI:

```bash
docker run -p 8501:8501 --env-file .env career-advisor \
    streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```
