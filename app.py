"""
app.py — Streamlit frontend entry point.

Run with:
    streamlit run app.py

The FastAPI backend must be running separately:
    uvicorn backend:fastapi_app --reload --port 8000
"""

from src.ui.sidebar import render_sidebar
from src.ui.display import render_display

render_sidebar()
render_display()
