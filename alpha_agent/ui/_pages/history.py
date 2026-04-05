"""History page — past pipeline runs from the current session."""

from __future__ import annotations

import streamlit as st


def render() -> None:
    st.header("Run History")

    history = st.session_state.get("history", [])

    if not history:
        st.info("No pipeline runs yet in this session. Run a query from the Research page.")
        return

    st.metric("Total Runs", len(history))

    for i, result in enumerate(reversed(history)):
        run_num = len(history) - i
        accepted = len(result.accepted_factors)
        rejected = len(result.rejected_factors)
        status = "Accepted" if accepted > 0 else "No Results"

        with st.expander(
            f"Run #{run_num}: \"{result.query}\" — {status} ({result.total_iterations} iter)",
            expanded=(i == 0),
        ):
            c1, c2, c3 = st.columns(3)
            c1.metric("Iterations", result.total_iterations)
            c2.metric("Accepted", accepted)
            c3.metric("Rejected", rejected)

            if result.accepted_factors:
                st.markdown("**Accepted Factors:**")
                for f in result.accepted_factors:
                    st.code(f.candidate.expression, language="python")

            if result.all_states:
                st.markdown("**Iteration Log:**")
                for j, state in enumerate(result.all_states):
                    st.caption(
                        f"Iter {j + 1}: "
                        f"{len(state.factors)} factors generated, "
                        f"{len(state.results)} backtested"
                        + (f", decision: {state.evaluation.decision}" if state.evaluation else "")
                    )

    if st.button("Clear History"):
        st.session_state["history"] = []
        st.rerun()
