"""Registry page — browse all accepted factors stored in SQLite."""

from __future__ import annotations

import streamlit as st


def render() -> None:
    st.header("Factor Registry")
    st.markdown("All accepted factors, deduplicated by structural hash.")

    try:
        from alpha_agent.pipeline.registry import FactorRegistry

        registry = FactorRegistry()
        records = registry.list_all()
    except Exception as e:
        st.error(f"Failed to load registry: {e}")
        return

    if not records:
        st.info("No factors registered yet. Run a pipeline to discover factors.")
        return

    st.metric("Total Factors", len(records))

    import pandas as pd

    rows = [
        {
            "ID": r.id,
            "Expression": r.expression,
            "Hypothesis": r.hypothesis_name,
            "IC Mean": r.metrics.get("ic_mean", "N/A"),
            "ICIR": r.metrics.get("icir", "N/A"),
            "Sharpe": r.metrics.get("sharpe_ratio", "N/A"),
            "Turnover": r.metrics.get("turnover", "N/A"),
            "Created": r.created_at[:19],
        }
        for r in records
    ]

    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    # Detail view
    st.subheader("Factor Details")
    factor_ids = [r.id for r in records]
    selected_id = st.selectbox("Select Factor", factor_ids, format_func=lambda x: f"#{x}: {next(r.expression for r in records if r.id == x)[:50]}")

    if selected_id:
        record = registry.get_by_id(selected_id)
        if record:
            st.code(record.expression, language="python")
            st.json(record.metrics)
            st.caption(f"Hypothesis: {record.hypothesis_name}")
            st.caption(f"Rationale: {record.rationale}")
            st.caption(f"Tree Hash: {record.tree_hash[:16]}...")
            st.caption(f"Created: {record.created_at}")
