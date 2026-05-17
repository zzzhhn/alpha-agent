"""Results page — detailed metrics and charts for the last pipeline run."""

from __future__ import annotations


import streamlit as st


def render() -> None:
    st.header("Results")

    result = st.session_state.get("last_result")
    if result is None:
        st.info("No results yet. Run a pipeline from the Research page first.")
        return

    st.subheader(f"Query: {result.query}")
    st.caption(f"{result.total_iterations} iteration(s)")

    all_results = []
    for state in result.all_states:
        all_results.extend(state.results)

    if not all_results:
        st.warning("No backtested factors in this run.")
        return

    # Summary table
    _render_summary_table(all_results)

    # Charts
    col1, col2 = st.columns(2)
    with col1:
        _render_ic_chart(all_results)
    with col2:
        _render_decay_chart(all_results)

    # Factor details
    st.subheader("Factor Details")
    for r in all_results:
        with st.expander(r.candidate.expression):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("IC Mean", f"{r.ic_mean:+.4f}")
            c2.metric("ICIR", f"{r.icir:+.4f}")
            c3.metric("Rank IC", f"{r.rank_ic_mean:+.4f}")
            c4.metric("Sharpe", f"{r.sharpe_ratio:+.4f}")

            c5, c6 = st.columns(2)
            c5.metric("Max Drawdown", f"{r.max_drawdown:+.2%}")
            c6.metric("Turnover", f"{r.turnover:.4f}")

            decay_str = ", ".join(f"{v:.4f}" for v in r.alpha_decay)
            st.caption(f"Alpha Decay: [{decay_str}]")

    # Export
    if st.button("Generate HTML Report"):
        _export_report(result)


def _render_summary_table(results) -> None:
    """Render a summary DataFrame of all factors."""
    import pandas as pd

    rows = [
        {
            "Expression": r.candidate.expression,
            "Hypothesis": r.candidate.hypothesis_name,
            "IC": r.ic_mean,
            "ICIR": r.icir,
            "Rank IC": r.rank_ic_mean,
            "Sharpe": r.sharpe_ratio,
            "Max DD": r.max_drawdown,
            "Turnover": r.turnover,
        }
        for r in results
    ]
    df = pd.DataFrame(rows)
    st.dataframe(
        df.style.format({
            "IC": "{:+.4f}",
            "ICIR": "{:+.4f}",
            "Rank IC": "{:+.4f}",
            "Sharpe": "{:+.4f}",
            "Max DD": "{:+.2%}",
            "Turnover": "{:.4f}",
        }),
        use_container_width=True,
    )


def _render_ic_chart(results) -> None:
    """Bar chart of IC mean for each factor."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    expressions = [r.candidate.expression[:30] + "..." if len(r.candidate.expression) > 30 else r.candidate.expression for r in results]
    ic_values = [r.ic_mean for r in results]
    colors = ["#2ecc71" if abs(v) > 0.03 else "#e74c3c" if abs(v) < 0.01 else "#f39c12" for v in ic_values]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(expressions, ic_values, color=colors)
    ax.set_xlabel("IC Mean")
    ax.set_title("Factor IC Comparison")
    ax.axvline(x=0, color="gray", linewidth=0.5)
    ax.axvline(x=0.03, color="green", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.axvline(x=-0.03, color="green", linewidth=0.5, linestyle="--", alpha=0.5)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def _render_decay_chart(results) -> None:
    """Line chart of alpha decay for top factors."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Show top 3 by abs(IC)
    sorted_results = sorted(results, key=lambda r: abs(r.ic_mean), reverse=True)[:3]

    fig, ax = plt.subplots(figsize=(8, 4))
    lags = [1, 2, 3, 5, 10, 20]

    for r in sorted_results:
        decay = list(r.alpha_decay)
        plot_lags = lags[: len(decay)]
        label = r.candidate.expression[:25] + "..." if len(r.candidate.expression) > 25 else r.candidate.expression
        ax.plot(plot_lags, decay[: len(plot_lags)], marker="o", label=label)

    ax.set_xlabel("Forward Lag (days)")
    ax.set_ylabel("IC")
    ax.set_title("Alpha Decay")
    ax.legend(fontsize=7)
    ax.axhline(y=0, color="gray", linewidth=0.5)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def _export_report(result) -> None:
    """Generate and offer download of HTML report."""
    try:
        from alpha_agent.report.generator import HTMLReportGenerator

        generator = HTMLReportGenerator()
        html = generator.generate(result)
        st.download_button(
            label="Download HTML Report",
            data=html,
            file_name="alpha_agent_report.html",
            mime="text/html",
        )
    except ImportError:
        st.error("Report generator not available yet.")
