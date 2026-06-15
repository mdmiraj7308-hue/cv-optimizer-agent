"""
sidebar.py — Streamlit sidebar:
  - Auth (sign-in / sign-up / sign-out)
  - CV upload
  - Profile form (shown first; Run Mode / Delete shown after first save)
  - Run Now / Scheduled scanner
"""

from __future__ import annotations

import streamlit as st
import httpx
from supabase import create_client

from src.config.settings import settings
from src.core.tools import parse_salary, delete_user_account, MAX_INPUT_CHARS, validate_char_limits
from src.ui.theme import sidebar_card, sidebar_kv_rows, user_badge

# ── Constants ─────────────────────────────────────────────────────────────────

HOUR_LABELS = [f"{h:02d}:00 {'AM' if h < 12 else 'PM'}" for h in range(24)]

JOB_TYPE_OPTIONS    = ["Any", "Remote", "Onsite"]
EXPERIENCE_OPTIONS  = ["Any", "Internship", "Entry level", "Associate",
                       "Mid-Senior level", "Director", "Executive"]
DATE_POSTED_OPTIONS = ["Any time", "Past 24 hours", "Past week", "Past month"]

# Map display labels → stored values
_EXP_TO_KEY = {
    "Any": "any", "Internship": "internship", "Entry level": "entry",
    "Associate": "associate", "Mid-Senior level": "mid_senior",
    "Director": "director", "Executive": "executive",
}
_KEY_TO_EXP = {v: k for k, v in _EXP_TO_KEY.items()}

_DATE_TO_KEY = {
    "Any time": "any_time", "Past 24 hours": "past_24h",
    "Past week": "past_week", "Past month": "past_month",
}
_KEY_TO_DATE = {v: k for k, v in _DATE_TO_KEY.items()}

# Countries for autocomplete
_COUNTRIES = [
    "Afghanistan", "Albania", "Algeria", "Argentina", "Australia", "Austria",
    "Azerbaijan", "Bangladesh", "Belgium", "Bolivia", "Brazil", "Bulgaria",
    "Cambodia", "Canada", "Chile", "China", "Colombia", "Croatia", "Czech Republic",
    "Denmark", "Dominican Republic", "Ecuador", "Egypt", "Estonia", "Ethiopia",
    "Finland", "France", "Georgia", "Germany", "Ghana", "Greece", "Guatemala",
    "Honduras", "Hong Kong", "Hungary", "India", "Indonesia", "Iran", "Iraq",
    "Ireland", "Israel", "Italy", "Japan", "Jordan", "Kazakhstan", "Kenya",
    "Kuwait", "Latvia", "Lebanon", "Lithuania", "Malaysia", "Mexico", "Morocco",
    "Myanmar", "Nepal", "Netherlands", "New Zealand", "Nigeria", "Norway",
    "Pakistan", "Panama", "Paraguay", "Peru", "Philippines", "Poland", "Portugal",
    "Qatar", "Romania", "Russia", "Saudi Arabia", "Serbia", "Singapore",
    "Slovakia", "South Africa", "South Korea", "Spain", "Sri Lanka", "Sweden",
    "Switzerland", "Taiwan", "Tanzania", "Thailand", "Turkey", "Uganda",
    "Ukraine", "United Arab Emirates", "United Kingdom", "United States",
    "Uruguay", "Uzbekistan", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe",
    "Remote",
]


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _get_supabase():
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    if st.session_state.get("access_token"):
        client.auth.set_session(
            st.session_state["access_token"],
            st.session_state.get("refresh_token", ""),
        )
    return client


def _auth_headers() -> dict:
    """Bearer header so the FastAPI backend can authenticate the current user."""
    token = st.session_state.get("access_token", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _load_profile(user_id: str):
    try:
        sb = _get_supabase()
        resp = sb.table("profiles").select("*").eq("user_id", user_id).maybe_single().execute()
        st.session_state["profile"] = resp.data or {}
    except Exception:
        st.session_state["profile"] = {}


# ── Session persistence (survives browser refresh) ─────────────────────────────

def _persist_session(refresh_token: str) -> None:
    """Store the refresh token in the URL so a page refresh keeps the user signed in."""
    if refresh_token:
        st.query_params["rt"] = refresh_token


def _clear_persisted_session() -> None:
    try:
        del st.query_params["rt"]
    except KeyError:
        pass


def _restore_session() -> None:
    """Re-establish a Supabase session from the refresh token stored in the URL."""
    if st.session_state.get("user_id"):
        return

    refresh_token = st.query_params.get("rt")
    if not refresh_token:
        return

    try:
        sb = create_client(settings.supabase_url, settings.supabase_anon_key)
        resp = sb.auth.refresh_session(refresh_token)
        if resp and resp.session and resp.user:
            st.session_state["user_id"]       = resp.user.id
            st.session_state["user_email"]    = resp.user.email
            st.session_state["access_token"]  = resp.session.access_token
            st.session_state["refresh_token"] = resp.session.refresh_token
            # Supabase rotates the refresh token on each use — store the new one.
            _persist_session(resp.session.refresh_token)
            _load_profile(resp.user.id)
        else:
            _clear_persisted_session()
    except Exception:
        # Token expired or invalid — drop it so the user can sign in cleanly.
        _clear_persisted_session()


def _save_profile(user_id: str, data: dict) -> bool:
    try:
        sb = _get_supabase()
        sb.table("profiles").upsert({"user_id": user_id, **data}).execute()
        return True
    except Exception as exc:
        st.sidebar.error(f"Failed to save profile: {exc}")
        return False


def _upload_cv(user_id: str, pdf_bytes: bytes) -> str | None:
    try:
        sb = _get_supabase()
        path = f"original/{user_id}/cv.pdf"
        sb.storage.from_("cvs").upload(
            path, pdf_bytes, {"content-type": "application/pdf", "upsert": "true"},
        )
        return path
    except Exception as exc:
        st.sidebar.error(f"CV upload failed: {exc}")
        return None


# ── Input helpers ─────────────────────────────────────────────────────────────

def _char_counter(label: str, text: str, limit: int = MAX_INPUT_CHARS) -> None:
    n = len(text)
    if n > limit:
        st.caption(f"⚠️ {label}: {n}/{limit} chars — too long.")
    else:
        st.caption(f"{label}: {n}/{limit} chars")


def _field_errors(roles_raw: str, salary_raw: str) -> list[str]:
    return validate_char_limits({"Target roles": roles_raw, "Salary range": salary_raw})


def _profile_is_complete(profile: dict) -> bool:
    """True once the user has a fully saved profile (all required fields)."""
    return bool(
        profile.get("original_cv_url")
        and profile.get("target_roles")
        and profile.get("location")
        and profile.get("salary_raw")
    )


def _validate_required_fields(
    *,
    roles_raw: str,
    country: str,
    salary_raw: str,
    has_cv: bool,
) -> dict[str, str]:
    """Return {field_key: error_message} for every empty required field."""
    errors: dict[str, str] = {}
    if not has_cv:
        errors["cv"] = "Upload your CV (PDF) before saving."
    if not roles_raw.strip():
        errors["roles"] = "Target roles are required."
    if not country.strip():
        errors["country"] = "Preferred country is required."
    if not salary_raw.strip():
        errors["salary"] = "Salary range is required."
    return errors


def _country_selectbox(saved_country: str) -> str:
    """Searchable country dropdown that feels like LinkedIn autocomplete."""
    options = [""] + _COUNTRIES
    saved_idx = 0
    if saved_country:
        try:
            saved_idx = options.index(saved_country)
        except ValueError:
            options = [saved_country] + _COUNTRIES
            saved_idx = 0

    country = st.selectbox(
        "Preferred country",
        options=options,
        index=saved_idx,
        key="preferred_country_select",
        help="Start typing to filter. Matches LinkedIn's location filter.",
        format_func=lambda x: x if x else "— Select a country —",
        label_visibility="collapsed",
    )
    return country or ""


# ── Auth section ──────────────────────────────────────────────────────────────

def _render_auth():
    sidebar_card("Account", "<p style='color:#94A3B8;font-size:0.85rem;margin:0;'>Sign in or create an account to get started.</p>")
    tab_in, tab_up = st.sidebar.tabs(["Sign In", "Sign Up"])

    with tab_in:
        email_in = st.text_input("Email", key="login_email")
        pw_in    = st.text_input("Password", type="password", key="login_pw")
        if st.button("Sign In", key="btn_signin"):
            try:
                sb   = create_client(settings.supabase_url, settings.supabase_anon_key)
                resp = sb.auth.sign_in_with_password({"email": email_in, "password": pw_in})
                st.session_state["user_id"]       = resp.user.id
                st.session_state["user_email"]    = resp.user.email
                st.session_state["access_token"]  = resp.session.access_token
                st.session_state["refresh_token"] = resp.session.refresh_token
                _persist_session(resp.session.refresh_token)
                _load_profile(resp.user.id)
                st.rerun()
            except Exception as exc:
                st.error(f"Sign-in failed: {exc}")

    with tab_up:
        email_up = st.text_input("Email", key="signup_email")
        pw_up    = st.text_input("Password (min 6 chars)", type="password", key="signup_pw")
        if st.button("Create Account", key="btn_signup"):
            try:
                sb   = create_client(settings.supabase_url, settings.supabase_anon_key)
                resp = sb.auth.sign_up({
                    "email": email_up, "password": pw_up,
                    "options": {"email_redirect_to": settings.auth_confirm_url},
                })
                if resp.user and not resp.session:
                    st.success(
                        "Account created! Check your email and click the confirmation "
                        "link, then **Sign In**."
                    )
                else:
                    st.success("Account created! You can sign in now.")
            except Exception as exc:
                st.error(f"Sign-up failed: {exc}")


# ── Profile form ──────────────────────────────────────────────────────────────

def _render_profile(user_id: str):
    profile  = st.session_state.get("profile", {})
    has_saved = _profile_is_complete(profile)

    st.sidebar.divider()

    # ── Job Preferences ───────────────────────────────────────────────────────
    editing = st.session_state.get("editing_profile", not has_saved)

    if not editing:
        roles_str = ", ".join(profile.get("target_roles") or []) or "—"
        country   = profile.get("location") or "—"
        jtype     = (profile.get("job_type") or "any").capitalize()
        exp_key   = profile.get("experience_level") or "any"
        exp_str   = _KEY_TO_EXP.get(exp_key, exp_key.replace("_", " ").title())
        date_key  = profile.get("date_posted") or "any_time"
        date_str  = _KEY_TO_DATE.get(date_key, date_key.replace("_", " ").title())
        salary    = profile.get("salary_raw") or "—"

        sidebar_card(
            "🎯 Job Preferences",
            sidebar_kv_rows([
                ("Roles", roles_str),
                ("Country", country),
                ("Job type", jtype),
                ("Experience", exp_str),
                ("Date posted", date_str),
                ("Salary", salary),
            ]),
        )
        if profile.get("original_cv_url"):
            st.sidebar.caption(
                f"✅ CV on file: `{profile['original_cv_url'].split('/')[-1]}`"
            )

        if st.sidebar.button("📄 Edit / Update Profile", key="btn_edit_profile",
                             use_container_width=True, type="primary"):
            st.session_state["editing_profile"] = True
            st.rerun()

    else:
        sidebar_card(
            "🎯 Job Preferences",
            "<p style='color:#94A3B8;font-size:0.82rem;margin:0;'>Fill every field, then click <strong>Save Profile</strong>.</p>",
        )

        with st.sidebar.form("profile_form", clear_on_submit=False, border=False):
            st.markdown("📄 CV (PDF)")
            cv_file = st.file_uploader(
                "Upload your CV",
                type=["pdf"],
                key="cv_uploader",
                label_visibility="collapsed",
            )
            if profile.get("original_cv_url") and not cv_file:
                st.caption(
                    f"Current file: `{profile['original_cv_url'].split('/')[-1]}` "
                    "(upload a new PDF to replace)"
                )

            st.markdown("Target roles (max 3, comma-separated)")
            roles_raw = st.text_input(
                "Target roles",
                value=", ".join(profile.get("target_roles") or []),
                key="target_roles_input",
                placeholder="e.g. Python Engineer, Data Analyst",
                max_chars=MAX_INPUT_CHARS,
                label_visibility="collapsed",
            )
            _char_counter("Roles", roles_raw)
            st.caption("Up to 3 roles · 10 jobs each · max 30 per scan")

            st.markdown("Preferred country")
            country = _country_selectbox(profile.get("location") or "")

            saved_jtype = (profile.get("job_type") or "any").lower()
            jtype_idx   = {"any": 0, "remote": 1, "onsite": 2}.get(saved_jtype, 0)
            job_type = st.selectbox(
                "Job type", JOB_TYPE_OPTIONS, index=jtype_idx, key="job_type_select",
            )

            saved_exp  = _KEY_TO_EXP.get(profile.get("experience_level") or "any", "Any")
            exp_idx    = EXPERIENCE_OPTIONS.index(saved_exp) if saved_exp in EXPERIENCE_OPTIONS else 0
            experience = st.selectbox(
                "Experience level", EXPERIENCE_OPTIONS, index=exp_idx,
                key="experience_select",
            )

            saved_date = _KEY_TO_DATE.get(profile.get("date_posted") or "any_time", "Any time")
            date_idx   = DATE_POSTED_OPTIONS.index(saved_date) if saved_date in DATE_POSTED_OPTIONS else 0
            date_posted = st.selectbox(
                "Date posted", DATE_POSTED_OPTIONS, index=date_idx, key="date_posted_select",
            )

            st.markdown("Salary range")
            salary_raw = st.text_input(
                "Salary range",
                value=profile.get("salary_raw") or "",
                key="salary_raw_input",
                placeholder="e.g. 60k-90k  |  80k+  |  any",
                max_chars=MAX_INPUT_CHARS,
                label_visibility="collapsed",
            )
            _char_counter("Salary", salary_raw)

            st.divider()
            submitted = st.form_submit_button(
                "💾 Save Profile", use_container_width=True, type="primary",
            )

        if submitted:
            has_cv = bool(cv_file) or bool(profile.get("original_cv_url"))
            required = _validate_required_fields(
                roles_raw=roles_raw,
                country=country,
                salary_raw=salary_raw,
                has_cv=has_cv,
            )
            char_errs = _field_errors(roles_raw, salary_raw)

            if required or char_errs:
                for msg in required.values():
                    st.sidebar.error(msg)
                for e in char_errs:
                    st.sidebar.error(e)
            else:
                cv_path = profile.get("original_cv_url")
                if cv_file:
                    with st.sidebar.spinner("Uploading CV…"):
                        cv_path = _upload_cv(user_id, cv_file.read())
                    if not cv_path:
                        st.rerun()

                salary_min, salary_max = parse_salary(salary_raw)
                target_roles = [r.strip() for r in roles_raw.split(",") if r.strip()][:3]
                if len(target_roles) < len([r for r in roles_raw.split(",") if r.strip()]):
                    st.sidebar.warning("Only the first 3 roles will be used.")

                payload = {
                    "target_roles":     target_roles,
                    "location":         country,
                    "job_type":         job_type.lower(),
                    "experience_level": _EXP_TO_KEY.get(experience, "any"),
                    "date_posted":      _DATE_TO_KEY.get(date_posted, "any_time"),
                    "salary_raw":       salary_raw,
                    "salary_min":       salary_min,
                    "salary_max":       salary_max,
                    "original_cv_url":  cv_path,
                }

                if _save_profile(user_id, payload):
                    st.session_state["profile"] = {**profile, **payload}
                    st.session_state["editing_profile"] = False
                    st.sidebar.success("Profile saved!")
                    st.rerun()

        if has_saved:
            if st.sidebar.button("✕ Cancel", key="btn_cancel_edit",
                                 use_container_width=True):
                st.session_state["editing_profile"] = False
                st.rerun()

    # ── Run Mode & actions (only after first save) ────────────────────────────
    if has_saved and not editing:
        _render_run_mode(user_id, profile)
        _render_danger_zone(user_id)


# ── Run mode ──────────────────────────────────────────────────────────────────

def _render_run_mode(user_id: str, profile: dict):
    st.sidebar.markdown(
        '<div class="sidebar-card-title" style="margin-top:0.5rem;">⚙️ Run Mode</div>',
        unsafe_allow_html=True,
    )

    with st.sidebar.container(border=True):
        run_mode = st.radio(
            "How should jobs be scanned?",
            options=["Manual", "Scheduled"],
            index=0 if profile.get("run_mode", "manual") == "manual" else 1,
            key="run_mode_radio",
            horizontal=True,
        )

        run_hour: int | None = None

        if run_mode == "Scheduled":
            saved_hour = profile.get("run_hour") or 9
            run_hour = st.selectbox(
                "Daily run hour", list(range(24)), index=saved_hour,
                format_func=lambda h: HOUR_LABELS[h], key="run_hour_select",
            )
            st.caption(
                f"Scans every day at **{HOUR_LABELS[run_hour]}** ({settings.scheduler_timezone})."
            )
        else:
            st.caption("Each **Run Now** click runs one LinkedIn scan (~20 s).")
            if st.button("▶ Run Now", key="btn_run_now", use_container_width=True, type="primary"):
                with st.spinner("Scanning jobs…"):
                    try:
                        resp = httpx.post(
                            f"{settings.fastapi_base_url}/api/run/{user_id}",
                            headers=_auth_headers(), timeout=360,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        st.success(f"Found {data.get('jobs_saved', 0)} new job(s)!")
                        st.session_state["jobs_refreshed"] = True
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Pipeline failed: {exc}")

        if run_mode == "Scheduled" and run_hour is not None:
            if st.button("💾 Save Schedule", key="btn_save_schedule", use_container_width=True):
                _save_profile(user_id, {"run_mode": "scheduled", "run_hour": run_hour})
                st.session_state["profile"] = {
                    **st.session_state.get("profile", {}),
                    "run_mode": "scheduled", "run_hour": run_hour,
                }
                try:
                    httpx.post(
                        f"{settings.fastapi_base_url}/api/schedule/{user_id}",
                        json={"run_hour": run_hour}, headers=_auth_headers(), timeout=10,
                    )
                except Exception:
                    pass
                st.success("Schedule saved!")
        elif run_mode == "Manual":
            if profile.get("run_mode") == "scheduled":
                if st.button("💾 Switch to Manual", key="btn_save_manual", use_container_width=True):
                    _save_profile(user_id, {"run_mode": "manual"})
                    st.session_state["profile"] = {
                        **st.session_state.get("profile", {}), "run_mode": "manual",
                    }
                    try:
                        httpx.delete(
                            f"{settings.fastapi_base_url}/api/schedule/{user_id}",
                            headers=_auth_headers(), timeout=5,
                        )
                    except Exception:
                        pass
                    st.success("Switched to manual mode.")


# ── Danger zone ───────────────────────────────────────────────────────────────

def _render_danger_zone(user_id: str):
    st.sidebar.divider()
    if st.session_state.get("confirm_delete_account"):
        st.sidebar.warning(
            "⚠️ **Delete account?**\n\n"
            "Permanently removes your profile, CV, all job history, optimized CVs, "
            "and application tracking. **This cannot be undone.**"
        )
        col_yes, col_no = st.sidebar.columns(2)
        with col_yes:
            if st.sidebar.button("Yes, delete", key="btn_confirm_delete", type="primary"):
                try:
                    try:
                        httpx.delete(
                            f"{settings.fastapi_base_url}/api/schedule/{user_id}",
                            headers=_auth_headers(), timeout=5,
                        )
                    except Exception:
                        pass
                    delete_user_account(user_id)
                    for key in list(st.session_state.keys()):
                        st.session_state.pop(key, None)
                    st.rerun()
                except Exception as exc:
                    st.sidebar.error(f"Delete failed: {exc}")
        with col_no:
            if st.sidebar.button("Cancel", key="btn_cancel_delete"):
                st.session_state["confirm_delete_account"] = False
                st.rerun()
    else:
        if st.sidebar.button("🗑 Delete Account", key="btn_delete_account",
                             use_container_width=True):
            st.session_state["confirm_delete_account"] = True
            st.rerun()


# ── Main render ───────────────────────────────────────────────────────────────

def render_sidebar():
    """Entry point called from app.py."""
    # Restore login from the URL refresh token before anything else, so a
    # browser refresh keeps the user on the app instead of the sign-in screen.
    _restore_session()

    if st.session_state.get("user_id"):
        user_id = st.session_state["user_id"]
        email   = st.session_state.get("user_email", "")

        user_badge(email)
        if st.sidebar.button("Sign Out", key="btn_signout", use_container_width=True):
            _clear_persisted_session()
            for key in ["user_id", "user_email", "access_token", "refresh_token",
                        "profile", "editing_profile", "cached_jobs",
                        "cached_applied_ids", "cached_history", "_sb_client",
                        "_sb_token"]:
                st.session_state.pop(key, None)
            st.rerun()

        if "profile" not in st.session_state:
            _load_profile(user_id)

        _render_profile(user_id)
    else:
        _render_auth()
