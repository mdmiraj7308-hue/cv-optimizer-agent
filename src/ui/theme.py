"""
theme.py — VolkAI-inspired SaaS styling for the Streamlit UI.

Inject once at app startup via inject_global_css().
HTML helpers are safe for st.markdown(..., unsafe_allow_html=True).
"""

from __future__ import annotations

import html

import streamlit as st

# ── Palette ───────────────────────────────────────────────────────────────────

GRADIENT = "linear-gradient(135deg, #6366F1 0%, #3B82F6 50%, #06B6D4 100%)"
GRADIENT_SOFT = "linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(59,130,246,0.08) 100%)"
CARD_BG = "#1E293B"
CARD_BORDER = "rgba(99, 102, 241, 0.25)"
TEXT_MUTED = "#94A3B8"
TEXT_PRIMARY = "#F1F5F9"
ACCENT = "#818CF8"


def inject_global_css() -> None:
    """Inject global CSS.

    Must run on EVERY script execution: Streamlit re-runs the whole script on
    each rerun and re-renders the DOM from scratch, so a one-time guard would
    drop the styles after the first interaction and the layout would collapse.
    """
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        }}

        /* Hide Streamlit chrome */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        header[data-testid="stHeader"] {{
            background: transparent;
        }}

        /* Main area */
        .block-container {{
            padding-top: 1.5rem;
            max-width: 1200px;
        }}

        /* Gradient page title */
        .saas-hero-title {{
            font-size: 1.85rem;
            font-weight: 700;
            background: {GRADIENT};
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 0.25rem;
        }}
        .saas-hero-sub {{
            color: {TEXT_MUTED};
            font-size: 0.95rem;
            margin-bottom: 1.5rem;
        }}

        /* KPI cards */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1rem;
            margin-bottom: 1.75rem;
        }}
        @media (max-width: 768px) {{
            .kpi-grid {{ grid-template-columns: 1fr; }}
        }}
        .kpi-card {{
            background: {GRADIENT_SOFT};
            border: 1px solid {CARD_BORDER};
            border-radius: 12px;
            padding: 1.1rem 1.25rem;
            position: relative;
            overflow: hidden;
        }}
        .kpi-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: {GRADIENT};
        }}
        .kpi-label {{
            color: {TEXT_MUTED};
            font-size: 0.78rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.35rem;
        }}
        .kpi-value {{
            color: {TEXT_PRIMARY};
            font-size: 1.75rem;
            font-weight: 700;
            line-height: 1.2;
        }}
        .kpi-sub {{
            color: {ACCENT};
            font-size: 0.82rem;
            margin-top: 0.25rem;
        }}

        /* Section headers */
        .section-header {{
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: {ACCENT};
            margin: 1.25rem 0 0.75rem 0;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .section-header::after {{
            content: '';
            flex: 1;
            height: 1px;
            background: linear-gradient(90deg, {CARD_BORDER}, transparent);
        }}

        /* Sidebar cards */
        .sidebar-card {{
            background: {GRADIENT_SOFT};
            border: 1px solid {CARD_BORDER};
            border-radius: 10px;
            padding: 0.85rem 1rem;
            margin-bottom: 0.75rem;
        }}
        .sidebar-card-title {{
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: {ACCENT};
            margin-bottom: 0.6rem;
        }}
        .sidebar-kv {{
            display: flex;
            justify-content: space-between;
            padding: 0.3rem 0;
            font-size: 0.85rem;
            border-bottom: 1px solid rgba(148,163,184,0.12);
        }}
        .sidebar-kv:last-child {{ border-bottom: none; }}
        .sidebar-kv-key {{ color: {TEXT_MUTED}; }}
        .sidebar-kv-val {{ color: {TEXT_PRIMARY}; font-weight: 500; text-align: right; max-width: 60%; }}

        .user-badge {{
            background: {GRADIENT_SOFT};
            border: 1px solid {CARD_BORDER};
            border-radius: 10px;
            padding: 0.75rem 1rem;
            margin-bottom: 0.75rem;
            font-size: 0.85rem;
        }}
        .user-badge-email {{
            color: {ACCENT};
            font-weight: 600;
            word-break: break-all;
        }}

        /* Job card expander styling */
        [data-testid="stExpander"] {{
            background: {CARD_BG};
            border: 1px solid {CARD_BORDER};
            border-radius: 12px;
            margin-bottom: 0.65rem;
            overflow: hidden;
        }}
        [data-testid="stExpander"] summary {{
            font-weight: 600;
            font-size: 0.95rem;
        }}
        [data-testid="stExpander"] > div {{
            border-top: 1px solid rgba(99,102,241,0.15);
        }}

        /* Score bar */
        .score-bar-wrap {{
            margin: 0.5rem 0 1rem 0;
        }}
        .score-bar-label {{
            display: flex;
            justify-content: space-between;
            font-size: 0.8rem;
            color: {TEXT_MUTED};
            margin-bottom: 0.35rem;
        }}
        .score-bar-track {{
            height: 8px;
            background: rgba(148,163,184,0.15);
            border-radius: 99px;
            overflow: hidden;
        }}
        .score-bar-fill {{
            height: 100%;
            border-radius: 99px;
            background: {GRADIENT};
            transition: width 0.3s ease;
        }}

        /* Detail column panels inside job cards */
        .detail-panel {{
            background: rgba(15,23,42,0.5);
            border: 1px solid rgba(99,102,241,0.12);
            border-radius: 8px;
            padding: 0.85rem;
            height: 100%;
            min-height: 120px;
        }}
        .detail-panel-title {{
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: {ACCENT};
            margin-bottom: 0.5rem;
        }}
        .detail-panel-body {{
            font-size: 0.88rem;
            color: {TEXT_PRIMARY};
            line-height: 1.55;
        }}

        /* About the job block */
        .about-job {{
            background: rgba(15,23,42,0.4);
            border: 1px solid rgba(99,102,241,0.1);
            border-radius: 8px;
            padding: 1rem;
            line-height: 1.55;
            font-size: 0.88rem;
            max-height: 420px;
            overflow-y: auto;
        }}
        .about-job ul {{ padding-left: 1.2rem; }}
        .about-job p {{ margin: 0.4rem 0; }}

        /* Welcome card (logged out) */
        .welcome-card {{
            background: {GRADIENT_SOFT};
            border: 1px solid {CARD_BORDER};
            border-radius: 16px;
            padding: 2rem 2.5rem;
            margin-top: 1rem;
        }}
        .welcome-card h3 {{
            background: {GRADIENT};
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-size: 1.4rem;
            margin-bottom: 1rem;
        }}
        .welcome-card ol {{
            color: {TEXT_MUTED};
            line-height: 1.8;
        }}

        /* Tabs */
        [data-testid="stTabs"] button {{
            font-weight: 600;
            font-size: 0.9rem;
        }}
        [data-testid="stTabs"] button[aria-selected="true"] {{
            color: {ACCENT} !important;
        }}

        /* Primary buttons — gradient feel via border glow */
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, #6366F1, #3B82F6) !important;
            border: none !important;
            font-weight: 600 !important;
            transition: opacity 0.2s;
        }}
        .stButton > button[kind="primary"]:hover {{
            opacity: 0.9;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero_title(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div style="font-size:1.85rem;font-weight:700;'
        f'background:{GRADIENT};-webkit-background-clip:text;'
        f'-webkit-text-fill-color:transparent;background-clip:text;'
        f'margin-bottom:0.25rem;">{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(
            f'<div style="color:{TEXT_MUTED};font-size:0.95rem;'
            f'margin-bottom:1.25rem;">{html.escape(subtitle)}</div>',
            unsafe_allow_html=True,
        )


def section_header(label: str, icon: str = "") -> None:
    prefix = f"{icon} " if icon else ""
    st.markdown(
        f'<div style="font-size:0.8rem;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.06em;color:{ACCENT};margin:1rem 0 0.6rem 0;">'
        f'{prefix}{html.escape(label)}</div>',
        unsafe_allow_html=True,
    )


def kpi_row(
    *,
    total_jobs: int,
    top_score: float,
    top_company: str,
    cvs_tailored: int,
    period_label: str = "All time",
) -> None:
    """Render three KPI cards side-by-side with icons and borders."""
    company_display = html.escape(top_company or "—")
    period_display = html.escape(period_label)

    cards = [
        ("📊", "linear-gradient(135deg,#6366F1,#818CF8)", "Total Jobs Scraped", str(total_jobs), period_display),
        ("🎯", "linear-gradient(135deg,#F59E0B,#FBBF24)", "Top Compatibility", f"{top_score:.0f}%", company_display),
        ("📄", "linear-gradient(135deg,#06B6D4,#3B82F6)", "ATS CVs Tailored", str(cvs_tailored), "Saved in Supabase"),
    ]

    card_html = ""
    for icon, grad, label, value, sub in cards:
        card_html += (
            '<div style="flex:1;display:flex;align-items:center;gap:12px;'
            'background:linear-gradient(135deg,rgba(99,102,241,0.14),rgba(59,130,246,0.07));'
            'border:1px solid rgba(99,102,241,0.35);border-radius:12px;padding:14px 16px;'
            'min-height:88px;box-shadow:0 2px 10px rgba(0,0,0,0.2);">'
            f'<div style="width:44px;height:44px;border-radius:10px;display:flex;'
            f'align-items:center;justify-content:center;font-size:1.3rem;flex-shrink:0;'
            f'background:{grad};box-shadow:0 2px 8px rgba(99,102,241,0.3);">{icon}</div>'
            '<div style="min-width:0;">'
            f'<div style="color:#94A3B8;font-size:0.68rem;font-weight:600;'
            f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:3px;">{label}</div>'
            f'<div style="color:#F1F5F9;font-size:1.6rem;font-weight:700;line-height:1.1;">{value}</div>'
            f'<div style="color:#818CF8;font-size:0.75rem;margin-top:3px;white-space:nowrap;'
            f'overflow:hidden;text-overflow:ellipsis;">{sub}</div>'
            '</div></div>'
        )

    st.markdown(
        f'<div style="display:flex;gap:14px;width:100%;margin-bottom:18px;">{card_html}</div>',
        unsafe_allow_html=True,
    )


def score_progress_bar(score: float) -> str:
    """Return HTML for a gradient compatibility progress bar (fully inline)."""
    pct = max(0, min(100, score))
    return (
        '<div style="margin:0.4rem 0 1rem 0;">'
        '<div style="display:flex;justify-content:space-between;font-size:0.8rem;'
        f'color:{TEXT_MUTED};margin-bottom:0.35rem;">'
        f'<span>Compatibility</span><span><strong>{pct:.0f}%</strong></span></div>'
        '<div style="height:8px;background:rgba(148,163,184,0.15);border-radius:99px;overflow:hidden;">'
        f'<div style="height:100%;border-radius:99px;background:{GRADIENT};width:{pct}%;"></div>'
        '</div></div>'
    )


def score_badge_html(score: float) -> str:
    if score >= 70:
        bg, fg = "rgba(16,185,129,0.2)", "#34D399"
    elif score >= 50:
        bg, fg = "rgba(245,158,11,0.2)", "#FBBF24"
    else:
        bg, fg = "rgba(239,68,68,0.2)", "#F87171"
    return (
        f'<span style="background:{bg};color:{fg};padding:3px 12px;'
        f'border-radius:20px;font-weight:700;font-size:0.85rem;">'
        f'{score:.0f}%</span>'
    )


def detail_panel(title: str, body_html: str) -> str:
    return (
        '<div style="background:rgba(15,23,42,0.5);border:1px solid rgba(99,102,241,0.12);'
        'border-radius:8px;padding:0.85rem;min-height:120px;">'
        f'<div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.05em;color:{ACCENT};margin-bottom:0.5rem;">{html.escape(title)}</div>'
        f'<div style="font-size:0.88rem;color:{TEXT_PRIMARY};line-height:1.55;">{body_html}</div>'
        '</div>'
    )


def sidebar_card(title: str, body_html: str) -> None:
    st.sidebar.markdown(
        '<div style="background:linear-gradient(135deg,rgba(99,102,241,0.15),rgba(59,130,246,0.08));'
        'border:1px solid rgba(99,102,241,0.25);border-radius:10px;padding:0.85rem 1rem;'
        'margin-bottom:0.75rem;">'
        f'<div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:0.05em;color:{ACCENT};margin-bottom:0.6rem;">{html.escape(title)}</div>'
        f'{body_html}</div>',
        unsafe_allow_html=True,
    )


def sidebar_kv_rows(rows: list[tuple[str, str]]) -> str:
    parts = []
    for key, val in rows:
        parts.append(
            '<div style="display:flex;justify-content:space-between;gap:0.5rem;padding:0.3rem 0;'
            'font-size:0.85rem;border-bottom:1px solid rgba(148,163,184,0.12);">'
            f'<span style="color:{TEXT_MUTED};">{html.escape(key)}</span>'
            f'<span style="color:{TEXT_PRIMARY};font-weight:500;text-align:right;'
            f'max-width:60%;">{html.escape(val)}</span>'
            '</div>'
        )
    return "".join(parts)


def user_badge(email: str) -> None:
    st.sidebar.markdown(
        '<div style="background:linear-gradient(135deg,rgba(99,102,241,0.15),rgba(59,130,246,0.08));'
        'border:1px solid rgba(99,102,241,0.25);border-radius:10px;padding:0.75rem 1rem;'
        'margin-bottom:0.75rem;font-size:0.85rem;">'
        'Signed in as<br>'
        f'<span style="color:{ACCENT};font-weight:600;word-break:break-all;">{html.escape(email)}</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def welcome_card() -> None:
    st.markdown(
        '<div style="background:linear-gradient(135deg,rgba(99,102,241,0.15),rgba(59,130,246,0.08));'
        'border:1px solid rgba(99,102,241,0.25);border-radius:16px;padding:2rem 2.5rem;margin-top:1rem;">'
        f'<h3 style="background:{GRADIENT};-webkit-background-clip:text;'
        '-webkit-text-fill-color:transparent;background-clip:text;font-size:1.4rem;'
        'margin-bottom:1rem;">Welcome to AI Career Assistant</h3>'
        '<p style="color:#94A3B8;margin-bottom:1rem;">Sign in using the sidebar to get started.</p>'
        '<ol style="color:#94A3B8;line-height:1.8;">'
        '<li>Scrapes LinkedIn jobs matching your target roles every day (or on demand).</li>'
        '<li>Uses GPT-4o-mini to score each job\'s compatibility with your CV (0–100).</li>'
        '<li>On request, generates an ATS-optimised PDF CV tailored to any specific job.</li>'
        '</ol></div>',
        unsafe_allow_html=True,
    )
