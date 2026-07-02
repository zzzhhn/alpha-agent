"""Phase E: real WorldQuant BRAIN platform integration.

The local miner (Phases A-D) breeds/validates factors on this platform's own
data. This package instead drives the ACTUAL WorldQuant BRAIN platform via its
API: simulate alphas, read real Sharpe/Fitness/Turnover, run the SELF_CORRELATION
check, and surface passing alphas for the user to submit. See client.py."""
