"""Streamlit main app — Alpha Agent interactive dashboard."""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Alpha Agent",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("Alpha Agent")
st.sidebar.caption("LLM-Powered Factor Research")

page = st.sidebar.radio(
    "Navigation",
    ["Research", "Results", "Registry", "History"],
    label_visibility="collapsed",
)

if page == "Research":
    from alpha_agent.ui._pages.research import render
    render()
elif page == "Results":
    from alpha_agent.ui._pages.results import render
    render()
elif page == "Registry":
    from alpha_agent.ui._pages.registry import render
    render()
elif page == "History":
    from alpha_agent.ui._pages.history import render
    render()
