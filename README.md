# AI Career Automation Assistant

A full-stack AI career assistant that scrapes LinkedIn jobs, scores each posting against your CV, and generates ATS-optimised PDFs on demand — built with Streamlit, FastAPI, LangGraph, and Supabase.

**Live Demo:** [https://your-app.onrender.com](https://your-app.onrender.com)  
*Hosted on Render free tier — first load after idle may take ~30 seconds. Sign-up required for full features.*

<!-- Optional: uncomment when you have a pre-seeded demo account
**Demo account**
- Email: `demo@example.com`
- Password: `YourDemoPassword`
-->

---

## What it does

1. **Sign up & upload your CV** — secure auth via Supabase; PDF stored in private storage.
2. **Set job preferences** — target roles, location, salary, remote/onsite, experience level.
3. **Run the pipeline** — scrapes recent LinkedIn jobs (Apify), evaluates each with GPT-4o-mini, saves compatibility scores.
4. **Review job cards** — sorted by score with summaries and apply links.
5. **Generate optimised CV** — on-demand, job-tailored ATS PDF uploaded to Supabase Storage.

---

## Screenshots

<!-- Replace with your own images, e.g. docs/screenshots/dashboard.png -->

| Dashboard | Job cards | Sidebar |
|---|---|---|
| *Add screenshot* | *Add screenshot* | *Add screenshot* |

---

## Tech stack

| Layer | Technologies |
|---|---|
| **Frontend** | Streamlit |
| **Backend** | FastAPI, APScheduler |
| **AI / orchestration** | LangGraph, LangChain, OpenAI GPT-4o-mini |
| **Data** | Supabase (Auth, Postgres, Storage) |
| **Scraping** | Apify (LinkedIn Jobs actor) |
| **PDF** | xhtml2pdf |
| **Deploy** | Docker, nginx, Render |

---

## Architecture

```
Browser
   ↓
nginx (single public URL on Render)
   ├── /              → Streamlit (app.py)
   ├── /api/*         → FastAPI (backend.py)
   └── /auth/confirm  → Email verification landing page

FastAPI + APScheduler
   ↓
LangGraph Phase 1 (eval)    → Apify → OpenAI → Supabase (processed_jobs)
LangGraph Phase 2 (optimize) → OpenAI → xhtml2pdf → Supabase Storage
```

### Phase 1 — Job evaluation

Triggered by **Run Now** (manual) or a daily cron job (scheduled mode).

1. Scrapes LinkedIn jobs posted in the last 24 hours.
2. Scores each job against the user's CV (0–100) with a short summary.
3. Persists results to `processed_jobs`.

### Phase 2 — CV optimisation (on demand)

Triggered when the user clicks **Generate Optimized CV** on a job card.

1. Rewrites the CV in ATS-friendly HTML tailored to the job description.
2. Renders HTML to PDF.
3. Uploads to Supabase Storage and returns a signed download URL.

---

## Run locally

### Prerequisites

- Python 3.12+
- Supabase project (see [Supabase setup](#supabase-setup) below)
- OpenAI API key
- Apify API token

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/Job_Finder.git
cd Job_Finder

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Environment variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

APIFY_API_TOKEN=apify_api_...
APIFY_ACTOR_ID=curious_coder/linkedin-jobs-scraper

# Local defaults (no change needed)
FASTAPI_BASE_URL=http://localhost:8000
STREAMLIT_BASE_URL=http://localhost:8501
AUTH_CONFIRM_URL=http://localhost:8000/auth/confirm
SCHEDULER_TIMEZONE=Asia/Dhaka
```

### 3. Supabase Auth (local)

In **Supabase → Authentication → URL Configuration**:

| Setting | Value |
|---|---|
| Site URL | `http://localhost:8000/auth/confirm` |
| Redirect URLs | `http://localhost:8000/auth/confirm` |
| | `http://localhost:8501` |

> **FastAPI must be running** when you click the email verification link.

### 4. Start the app (two terminals)

```bash
# Terminal 1 — backend
uvicorn backend:fastapi_app --reload --port 8000

# Terminal 2 — frontend
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

---

## Deploy to Render (one URL)

The repo ships with a **single-container** setup: nginx routes traffic to Streamlit and FastAPI on one public URL.

### Steps

1. Push this repo to GitHub.
2. On [Render](https://render.com): **New → Web Service** → connect the repo.
3. Set **Runtime** to **Docker**, **Plan** to **Free**, **Health Check Path** to `/health`.
4. Add environment variables:

| Variable | Required |
|---|---|
| `OPENAI_API_KEY` | Yes |
| `SUPABASE_URL` | Yes |
| `SUPABASE_ANON_KEY` | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes |
| `APIFY_API_TOKEN` | Yes |
| `OPENAI_MODEL` | No (default `gpt-4o-mini`) |
| `SCHEDULER_TIMEZONE` | No (default `Asia/Dhaka`) |

Public URLs are set automatically from Render's `RENDER_EXTERNAL_URL` — no manual URL config needed.

5. After deploy, update **Supabase Auth** redirect URLs with your Render URL:

| Setting | Value |
|---|---|
| Site URL | `https://your-app.onrender.com/auth/confirm` |
| Redirect URLs | `https://your-app.onrender.com/auth/confirm` |
| | `https://your-app.onrender.com` |

6. Replace `https://your-app.onrender.com` at the top of this README with your real URL.

### Docker (local single-container test)

```bash
docker build -t job-finder .
docker run --rm -p 10000:10000 --env-file .env -e PUBLIC_BASE_URL=http://localhost:10000 job-finder
```

Open [http://localhost:10000](http://localhost:10000).

---

## Environment variables reference

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI secret key | — |
| `OPENAI_MODEL` | Model for both agents | `gpt-4o-mini` |
| `SUPABASE_URL` | Supabase project URL | — |
| `SUPABASE_ANON_KEY` | Anon key (Streamlit / client) | — |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (backend) | — |
| `APIFY_API_TOKEN` | Apify API token | — |
| `APIFY_ACTOR_ID` | LinkedIn scraper actor | `curious_coder/linkedin-jobs-scraper` |
| `FASTAPI_BASE_URL` | URL Streamlit uses for API calls | `http://localhost:8000` |
| `STREAMLIT_BASE_URL` | App URL on the welcome page | `http://localhost:8501` |
| `AUTH_CONFIRM_URL` | Supabase email redirect URL | `http://localhost:8000/auth/confirm` |
| `PUBLIC_BASE_URL` | Override for single-URL Docker deploy | — |
| `SCHEDULER_TIMEZONE` | APScheduler timezone | `Asia/Dhaka` |

On Render, `RENDER_EXTERNAL_URL` is injected automatically and configures the public URLs for you.

---

## Supabase setup

Run the following in your Supabase **SQL Editor**.

### 1. Enable UUID extension

```sql
create extension if not exists "uuid-ossp";
```

### 2. `profiles` table

```sql
create table public.profiles (
    user_id     uuid primary key references auth.users(id) on delete cascade,
    target_roles text[]          not null default '{}',
    location    text             not null default '',
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
insert into storage.buckets (id, name, public)
values ('cvs', 'cvs', false)
on conflict (id) do nothing;

create policy "Users manage own CVs"
    on storage.objects
    for all
    using  (bucket_id = 'cvs' and auth.uid()::text = (storage.foldername(name))[2])
    with check (bucket_id = 'cvs' and auth.uid()::text = (storage.foldername(name))[2]);

create policy "Service role manages all CVs"
    on storage.objects
    for all
    using (bucket_id = 'cvs')
    with check (bucket_id = 'cvs');
```

Storage paths:
- `original/{user_id}/cv.pdf` — user-uploaded CV
- `optimized/{user_id}/{job_id}.pdf` — generated ATS CV

---

## Project structure

```
Job_Finder/
├── app.py                  # Streamlit entry point
├── backend.py              # FastAPI + APScheduler
├── deploy/
│   ├── nginx.conf.template # Reverse proxy routes
│   └── start.sh            # Single-container startup
├── src/
│   ├── config/settings.py
│   ├── core/               # LLMs, tools, state
│   ├── ui/                 # Streamlit UI (sidebar, display, theme)
│   └── workflow/           # LangGraph agents & graph
├── Dockerfile
├── render.yaml
└── requirements.txt
```

---

## License

MIT — feel free to use this as a reference for your own projects.

---

## Author

**Your Name** — [GitHub](https://github.com/YOUR_USERNAME) · [LinkedIn](https://linkedin.com/in/YOUR_PROFILE)
