"""
streamlit_app.py — Alias for app.py (either command works).

    streamlit run app.py
    streamlit run streamlit_app.py
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
