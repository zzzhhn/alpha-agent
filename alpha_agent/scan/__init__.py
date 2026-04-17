"""scan layer: numpy+numba vectorized fast-scan engine.

Exists alongside backtest/engine.py (event-driven, accurate, slow).
Target: <800ms single-ticker scan for slider-live-recompute UX (Pillar 4).

Planned contents (W2+):
    vectorized.py    - @njit rolling zscore, rank, ts_corr
    warm_cache.py    - pre-load common universes to numpy memory at boot
"""
