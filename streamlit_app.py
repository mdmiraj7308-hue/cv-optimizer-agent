"""
streamlit_app.py — Alias for app.py (either command works).

    streamlit run app.py
    streamlit run streamlit_app.py
"""

from src.ui.sidebar import render_sidebar
from src.ui.display import render_display

render_sidebar()
render_display()
