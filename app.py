"""
app.py — Streamlit frontend entry point.

Run with:
    streamlit run app.py

The FastAPI backend must be running separately:
    uvicorn backend:fastapi_app --reload --port 8000
"""

import streamlit as st

from src.ui.theme import inject_global_css
from src.ui.sidebar import render_sidebar
from src.ui.display import render_display

st.set_page_config(
    page_title="AI Career Assistant",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_global_css()
render_sidebar()
render_display()
