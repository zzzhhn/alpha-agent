"""One-shot patch: adds risk management params to backtest endpoint.
Usage on AutoDL: python3 /root/alpha-agent/patch_backend.py
"""
import re, subprocess, time

FILE = "/root/alpha-agent/alpha_agent/api/routes/interactive.py"

with open(FILE, "r") as f:
    src = f.read()

# 1. Add new fields to BacktestRequest (after bollinger_period line)
src = src.replace(
    '    bollinger_period: int = Field(default=20, ge=5, le=100)\n    initial_capital',
    '    bollinger_period: int = Field(default=20, ge=5, le=100)\n'
    '    bollinger_std: float = Field(default=2.0, ge=0.5, le=4.0)\n'
    '    stop_loss_pct: float = Field(default=0.0, ge=0.0, le=50.0)\n'
    '    take_profit_pct: float = Field(default=0.0, ge=0.0, le=100.0)\n'
    '    position_size_pct: float = Field(default=100.0, ge=10.0, le=100.0)\n'
    '    initial_capital',
)

# 2. Update _compute_bollinger signature + body
src = src.replace(
    'def _compute_bollinger(close: pd.Series, period: int = 20)',
    'def _compute_bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0)',
)
src = src.replace('upper = sma + 2 * std', 'upper = sma + num_std * std')
src = src.replace('lower = sma - 2 * std', 'lower = sma - num_std * std')

# 3. Pass bollinger_std to function calls
src = src.replace(
    '_compute_bollinger(close, req.bollinger_period)',
    '_compute_bollinger(close, req.bollinger_period, req.bollinger_std)',
)

# 4. Add entry_price init
src = src.replace(
    '    position = 0.0  # shares held\n    cash = capital',
    '    position = 0.0  # shares held\n    entry_price = 0.0\n    cash = capital',
)

# 5. Update buy logic (position sizing + entry_price)
src = src.replace(
    '            shares = int(cash / price)\n'
    '            if shares > 0:\n'
    '                position = shares\n'
    '                cash -= shares * price\n'
    '                trades.append({"date": date_str, "side": "BUY"',
    '            alloc = cash * (req.position_size_pct / 100.0)\n'
    '            shares = int(alloc / price)\n'
    '            if shares > 0:\n'
    '                position = shares\n'
    '                entry_price = price\n'
    '                cash -= shares * price\n'
    '                trades.append({"date": date_str, "side": "BUY"',
)

# 6. Replace sell logic with stop-loss/take-profit
old_sell = (
    '        # Sell signal: RSI overbought OR MACD turning down\n'
    '        elif position > 0 and (r > req.rsi_overbought or mh < 0):\n'
    '            pnl = position * price - (trades[-1]["price"] * position) if trades else 0.0\n'
    '            trades.append({"date": date_str, "side": "SELL", "price": round(price, 2), "shares": int(position), "pnl": round(pnl, 2)})\n'
    '            cash += position * price\n'
    '            position = 0'
)
new_sell = (
    '        # Sell signal: stop-loss / take-profit / RSI overbought / MACD turning down\n'
    '        elif position > 0:\n'
    '            change_pct = (price - entry_price) / entry_price * 100.0\n'
    '            hit_stop = req.stop_loss_pct > 0 and change_pct <= -req.stop_loss_pct\n'
    '            hit_tp = req.take_profit_pct > 0 and change_pct >= req.take_profit_pct\n'
    '            hit_signal = r > req.rsi_overbought or mh < 0\n'
    '            if hit_stop or hit_tp or hit_signal:\n'
    '                side_label = "SELL (stop)" if hit_stop else "SELL (tp)" if hit_tp else "SELL"\n'
    '                pnl = position * price - (entry_price * position)\n'
    '                trades.append({"date": date_str, "side": side_label, "price": round(price, 2), "shares": int(position), "pnl": round(pnl, 2)})\n'
    '                cash += position * price\n'
    '                position = 0'
)
src = src.replace(old_sell, new_sell)

# 7. Fix end-of-period close to use entry_price
src = src.replace(
    'pnl = position * last_price - (trades[-1]["price"] * position) if trades else 0.0',
    'pnl = position * last_price - (entry_price * position)',
)

with open(FILE, "w") as f:
    f.write(src)

print("✓ File patched successfully")

# Restart uvicorn
subprocess.run(["pkill", "-f", "uvicorn"], capture_output=True)
time.sleep(1)
subprocess.Popen(
    ["python", "-m", "uvicorn", "alpha_agent.api.app:app",
     "--host", "0.0.0.0", "--port", "6008", "--reload"],
    stdout=open("/tmp/uvicorn.log", "w"),
    stderr=subprocess.STDOUT,
)
print("✓ Uvicorn restarting...")
time.sleep(3)

# Verify
import json, urllib.request
req_data = json.dumps({
    "ticker": "NVDA", "start_date": "2024-01-01", "end_date": "2025-01-01",
    "stop_loss_pct": 5, "take_profit_pct": 10, "position_size_pct": 50,
}).encode()
r = urllib.request.Request(
    "http://localhost:6008/api/v1/backtest/run",
    data=req_data, headers={"Content-Type": "application/json"},
)
resp = json.loads(urllib.request.urlopen(r).read())
m = resp["metrics"]
print(f"✓ Trades: {m['total_trades']}, Return: {m['total_return']*100:.2f}%, Sharpe: {m['sharpe_ratio']:.4f}")
