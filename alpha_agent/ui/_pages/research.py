"""Research page — run the alpha research pipeline from natural language."""

from __future__ import annotations

import asyncio
import logging
import time

import streamlit as st

logger = logging.getLogger(__name__)


def render() -> None:
    st.header("Factor Research")
    st.markdown("Enter a research query to generate and evaluate alpha factors.")

    # Prerequisites check
    with st.expander("System Status", expanded=False):
        _show_status()

    query = st.text_input(
        "Research Query",
        placeholder="e.g., short-term reversal factors for CSI300",
        key="research_query",
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        max_iter = st.number_input("Max Iterations", min_value=1, max_value=5, value=3)
    with col2:
        st.markdown("")  # spacer

    if st.button("Run Pipeline", type="primary", disabled=not query):
        _run_pipeline(query, max_iter)


def _show_status() -> None:
    """Show system prerequisites status."""
    from alpha_agent.config import Settings
    import httpx
    from pathlib import Path

    settings = Settings()

    # LLM check
    try:
        url = settings.ollama_base_url.rstrip("/") + "/api/version"
        resp = httpx.get(url, timeout=3.0)
        resp.raise_for_status()
        ver = resp.json().get("version", "?")
        st.markdown(f"LLM: **Connected** (Ollama {ver} at `{settings.ollama_base_url}`)")
    except Exception:
        st.markdown(f"LLM: **Not connected** — start SSH tunnel to `{settings.ollama_base_url}`")

    # Data check
    cache_dir = Path("data")
    parquet_files = list(cache_dir.glob("*.parquet")) if cache_dir.exists() else []
    if parquet_files:
        st.markdown(f"Data: **{len(parquet_files)} cached files** in `data/`")
    else:
        try:
            import akshare  # noqa: F401
            st.markdown("Data: No cache — will fetch from AKShare on first run (may take 1-2 min)")
        except ImportError:
            st.markdown("Data: **akshare not installed** — run `pip install akshare`")

    # Registry check
    try:
        from alpha_agent.pipeline.registry import FactorRegistry
        count = FactorRegistry().count()
        st.markdown(f"Registry: **{count} factors** stored")
    except Exception:
        st.markdown("Registry: Empty (will be created on first run)")


def _run_pipeline(query: str, max_iterations: int) -> None:
    """Execute the pipeline with live status updates."""
    from alpha_agent.config import Settings
    from alpha_agent.pipeline.orchestrator import AlphaResearchPipeline

    settings = Settings()
    progress = st.progress(0, text="Initializing...")
    status_container = st.container()

    try:
        # Check LLM availability
        progress.progress(5, text="Checking LLM connection...")
        _check_llm(settings)

        # Load data
        progress.progress(10, text="Loading market data...")
        data = _load_data(settings)

        if data is None or data.empty:
            st.error(
                "Failed to load market data. Possible causes:\n"
                "- `akshare` not installed (`pip install akshare`)\n"
                "- No cached Parquet files in `data/` directory\n"
                "- Network issue connecting to AKShare API"
            )
            return

        # Create pipeline
        progress.progress(20, text="Creating pipeline...")
        from alpha_agent.pipeline.registry import FactorRegistry
        registry = FactorRegistry()
        pipeline = AlphaResearchPipeline(
            settings=settings,
            data=data,
            registry=registry,
            max_iterations=max_iterations,
        )

        # Run
        progress.progress(30, text="Generating hypotheses...")
        start_time = time.time()
        result = asyncio.run(pipeline.run(query))
        elapsed = time.time() - start_time

        progress.progress(100, text=f"Complete ({elapsed:.1f}s)")

        # Store result in session state
        st.session_state["last_result"] = result
        if "history" not in st.session_state:
            st.session_state["history"] = []
        st.session_state["history"].append(result)

        # Display summary
        _display_summary(result, elapsed, status_container)

    except Exception as e:
        st.error(f"Pipeline failed: {e}")
        logger.error("Pipeline error", exc_info=True)


def _check_llm(settings) -> None:
    """Quick LLM health check."""
    import httpx

    url = settings.ollama_base_url.rstrip("/") + "/api/version"
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        st.warning(f"LLM not reachable at {settings.ollama_base_url}. Ensure SSH tunnel is active.")
        raise RuntimeError(f"LLM unavailable: {e}") from e


def _load_data(settings):
    """Load cached market data or fetch fresh."""
    import pandas as pd
    from pathlib import Path

    cache_dir = Path("data")
    parquet_files = list(cache_dir.glob("*.parquet")) if cache_dir.exists() else []

    if parquet_files:
        frames = [pd.read_parquet(f) for f in parquet_files]
        data = pd.concat(frames)
        if not isinstance(data.index, pd.MultiIndex):
            if "date" in data.columns and "stock_code" in data.columns:
                data = data.set_index(["date", "stock_code"])
        return data

    # Try fetching fresh data
    try:
        from alpha_agent.data.provider import AKShareProvider
        from alpha_agent.data.universe import CSI300Universe
        from alpha_agent.data.cache import ParquetCache

        cache = ParquetCache()
        provider = AKShareProvider(cache=cache)
        universe = CSI300Universe()
        codes = universe.stock_codes[:10]  # Start with 10 stocks for speed
        st.info(f"Fetching data for {len(codes)} stocks via AKShare (first run may be slow)...")
        data = provider.fetch(codes, "20240101", "20250401")
        return data
    except ImportError as e:
        st.error(f"Missing dependency: {e}. Run `pip install akshare` first.")
        return None
    except Exception as e:
        st.error(f"Data fetch failed: {e}")
        logger.warning("Failed to fetch data: %s", e)
        return None


def _display_summary(result, elapsed: float, container) -> None:
    """Show pipeline results summary."""
    with container:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Iterations", result.total_iterations)
        col2.metric("Accepted", len(result.accepted_factors))
        col3.metric("Rejected", len(result.rejected_factors))
        col4.metric("Time", f"{elapsed:.1f}s")

        if result.accepted_factors:
            st.success(f"Found {len(result.accepted_factors)} alpha factor(s)!")
            for f in result.accepted_factors:
                st.code(f.candidate.expression, language="python")
                c1, c2, c3 = st.columns(3)
                c1.metric("IC", f"{f.ic_mean:+.4f}")
                c2.metric("ICIR", f"{f.icir:+.4f}")
                c3.metric("Sharpe", f"{f.sharpe_ratio:+.4f}")
        else:
            st.warning("No factors accepted in this run.")

        # Show iteration details in expanders
        for i, state in enumerate(result.all_states):
            with st.expander(f"Iteration {i + 1} Details", expanded=False):
                if state.hypotheses:
                    st.markdown("**Hypotheses:**")
                    for h in state.hypotheses:
                        st.markdown(f"- **{h.name}**: {h.rationale}")

                if state.factors:
                    st.markdown("**Generated Factors:**")
                    for f in state.factors:
                        st.code(f.expression, language="python")

                if state.results:
                    st.markdown("**Backtest Results:**")
                    import pandas as pd
                    rows = [
                        {
                            "Expression": r.candidate.expression[:50],
                            "IC": f"{r.ic_mean:+.4f}",
                            "ICIR": f"{r.icir:+.4f}",
                            "Rank IC": f"{r.rank_ic_mean:+.4f}",
                            "Sharpe": f"{r.sharpe_ratio:+.4f}",
                            "Turnover": f"{r.turnover:.4f}",
                        }
                        for r in state.results
                    ]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

                if state.evaluation:
                    st.markdown(f"**Decision:** `{state.evaluation.decision}`")
                    if state.evaluation.feedback:
                        st.info(state.evaluation.feedback)
