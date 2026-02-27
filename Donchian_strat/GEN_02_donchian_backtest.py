#!/usr/bin/env python3
"""
================================================================================
DONCHIAN CHANNEL BACKTEST
================================================================================
Backtests the Donchian Channel Breakout strategy using the exact same logic
and config as the live engine (trading_config.json).

Reads historical data from dataticks/ directory.
No MT5 connection needed.

Output: Console report + GEN_02_backtest_results.csv
================================================================================
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# ─── Load Config ──────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config" / "trading_config.json"
DATA_DIR = SCRIPT_DIR / "dataticks"
OUTPUT_CSV = SCRIPT_DIR / "GEN_02_backtest_results.csv"

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

# Timeframe string -> file suffix mapping
TF_FILE_MAP = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
}


def load_fx_rates() -> dict:
    """
    Load average FX rates from dataticks for currency conversion to USD.
    Returns dict like {'JPY': 0.00653, 'EUR': 1.17, 'USD': 1.0, ...}
    """
    rates = {'USD': 1.0}

    # USDJPY -> JPY per USD, we need USD per JPY
    usdjpy_path = DATA_DIR / "USDJPY_1h.csv"
    if usdjpy_path.exists():
        df = pd.read_csv(usdjpy_path)
        avg_rate = df['close'].astype(float).mean()
        rates['JPY'] = 1.0 / avg_rate
    else:
        rates['JPY'] = 1.0 / 153.0  # fallback

    # EURUSD -> USD per EUR
    eurusd_path = DATA_DIR / "EURUSD_1h.csv"
    if eurusd_path.exists():
        df = pd.read_csv(eurusd_path)
        rates['EUR'] = df['close'].astype(float).mean()
    else:
        rates['EUR'] = 1.10  # fallback

    # GBPUSD -> USD per GBP
    gbpusd_path = DATA_DIR / "GBPUSD_1h.csv"
    if gbpusd_path.exists():
        df = pd.read_csv(gbpusd_path)
        rates['GBP'] = df['close'].astype(float).mean()
    else:
        rates['GBP'] = 1.27  # fallback

    # AUDUSD -> USD per AUD
    audusd_path = DATA_DIR / "AUDUSD_1h.csv"
    if audusd_path.exists():
        df = pd.read_csv(audusd_path)
        rates['AUD'] = df['close'].astype(float).mean()
    else:
        rates['AUD'] = 0.65  # fallback

    return rates


FX_RATES = load_fx_rates()


def load_data(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Load OHLCV data from dataticks/"""
    suffix = TF_FILE_MAP.get(timeframe, timeframe.lower())
    filepath = DATA_DIR / f"{symbol}_{suffix}.csv"
    if not filepath.exists():
        print(f"  ⚠ Data not found: {filepath.name}")
        return None
    try:
        df = pd.read_csv(filepath)
        df["time"] = pd.to_datetime(df["time"])
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)
        if "spread" in df.columns:
            df["spread"] = df["spread"].astype(float)
        else:
            df["spread"] = 0.0
        return df.sort_values("time").reset_index(drop=True)
    except Exception as e:
        print(f"  ⚠ Error loading {filepath.name}: {e}")
        return None


def calculate_adx(high, low, close, period=14):
    """Calculate ADX for each bar. Returns array of ADX values."""
    n = len(high)
    adx_out = np.zeros(n)
    if n < period * 3:
        return adx_out

    tr = np.zeros(n)
    pdm = np.zeros(n)
    ndm = np.zeros(n)

    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        up = high[i] - high[i - 1]
        dn = low[i - 1] - low[i]
        pdm[i] = up if up > dn and up > 0 else 0.0
        ndm[i] = dn if dn > up and dn > 0 else 0.0

    atr = np.zeros(n)
    spdm = np.zeros(n)
    sndm = np.zeros(n)

    atr[period] = np.sum(tr[1:period + 1]) / period
    spdm[period] = np.sum(pdm[1:period + 1]) / period
    sndm[period] = np.sum(ndm[1:period + 1]) / period

    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        spdm[i] = (spdm[i - 1] * (period - 1) + pdm[i]) / period
        sndm[i] = (sndm[i - 1] * (period - 1) + ndm[i]) / period

    dx = np.zeros(n)
    for i in range(period, n):
        if atr[i] > 0:
            pdi = 100 * spdm[i] / atr[i]
            ndi = 100 * sndm[i] / atr[i]
            if (pdi + ndi) > 0:
                dx[i] = 100 * abs(pdi - ndi) / (pdi + ndi)

    start = period * 2
    if start >= n:
        return adx_out

    adx_out[start] = np.mean(dx[period + 1:start + 1])
    for i in range(start + 1, n):
        adx_out[i] = (adx_out[i - 1] * (period - 1) + dx[i]) / period

    return adx_out


def run_backtest(df: pd.DataFrame, period: int, symbol_config: dict,
                 exit_on_mid: bool, exit_on_opposite: bool,
                 direction: str = "both",
                 adx_min: float = 0, adx_period: int = 14,
                 close_confirm: bool = False,
                 cooldown_bars: int = 0) -> dict | None:
    """
    Run Donchian Channel Breakout backtest on a DataFrame.

    Logic matches core/donchian_strategy.py:
    - BUY when close > upper (close_confirm) or high >= upper
    - SELL when close < lower (close_confirm) or low <= lower
    - ADX filter: skip entry if ADX < adx_min
    - Cooldown: skip entry for N bars after exit
    - EXIT LONG when price < mid (if exit_on_mid) OR bearish breakout (if exit_on_opposite)
    - EXIT SHORT when price > mid (if exit_on_mid) OR bullish breakout (if exit_on_opposite)

    Uses per-bar spread from data as transaction cost (applied on entry + exit).
    """
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    spread_pts = df["spread"].values if "spread" in df.columns else np.zeros(len(df))

    # Get symbol point for spread cost conversion
    # Estimate point from price precision
    sample_price = close[len(close) // 2]
    if sample_price > 1000:
        point = 0.01  # indices, gold-like
    elif sample_price > 10:
        point = 0.01
    else:
        point = 0.00001  # forex

    n = len(df)
    if n < period + 5:
        return None

    # Pre-compute Donchian channels
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    mid = np.full(n, np.nan)

    for i in range(period, n):
        upper[i] = np.max(high[i - period:i])
        lower[i] = np.min(low[i - period:i])
        mid[i] = (upper[i] + lower[i]) / 2.0

    # Pre-compute ADX if filter is active
    adx_values = np.zeros(n)
    if adx_min > 0:
        adx_values = calculate_adx(high, low, close, adx_period)

    # Simulate trades
    trades = []
    position = None  # None, "LONG", "SHORT"
    entry_price = 0.0
    entry_bar = 0
    entry_spread_cost = 0.0
    last_exit_bar = -999  # for cooldown tracking

    for i in range(period + 1, n):
        if np.isnan(upper[i]) or np.isnan(upper[i - 1]):
            continue

        current_spread_cost = spread_pts[i] * point

        # --- Exit logic (check first) ---
        if position == "LONG":
            exit_reasons = []
            if exit_on_mid and close[i] < mid[i]:
                exit_reasons.append("mid_cross")
            if exit_on_opposite and low[i] <= lower[i]:
                exit_reasons.append("opposite_breakout")

            if exit_reasons:
                exit_price = close[i]
                pnl = (exit_price - entry_price) - entry_spread_cost - current_spread_cost
                trades.append({
                    "entry_bar": entry_bar,
                    "exit_bar": i,
                    "direction": "LONG",
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "bars_held": i - entry_bar,
                    "exit_reason": "+".join(exit_reasons),
                    "entry_time": str(df["time"].iloc[entry_bar]),
                    "exit_time": str(df["time"].iloc[i]),
                })
                position = None
                last_exit_bar = i
                continue

        elif position == "SHORT":
            exit_reasons = []
            if exit_on_mid and close[i] > mid[i]:
                exit_reasons.append("mid_cross")
            if exit_on_opposite and high[i] >= upper[i]:
                exit_reasons.append("opposite_breakout")

            if exit_reasons:
                exit_price = close[i]
                pnl = (entry_price - exit_price) - entry_spread_cost - current_spread_cost
                trades.append({
                    "entry_bar": entry_bar,
                    "exit_bar": i,
                    "direction": "SHORT",
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "bars_held": i - entry_bar,
                    "exit_reason": "+".join(exit_reasons),
                    "entry_time": str(df["time"].iloc[entry_bar]),
                    "exit_time": str(df["time"].iloc[i]),
                })
                position = None
                last_exit_bar = i
                continue

        # --- Entry logic (only if flat) ---
        if position is None:
            # ADX filter
            if adx_min > 0 and adx_values[i] < adx_min:
                continue

            # Cooldown filter
            if cooldown_bars > 0 and (i - last_exit_bar) < cooldown_bars:
                continue

            # Breakout conditions
            if close_confirm:
                buy_cond = close[i] > upper[i]
                sell_cond = close[i] < lower[i]
            else:
                buy_cond = high[i] >= upper[i]
                sell_cond = low[i] <= lower[i]

            # Bullish breakout
            if buy_cond and direction in ("both", "long"):
                position = "LONG"
                entry_price = close[i]
                entry_bar = i
                entry_spread_cost = current_spread_cost

            # Bearish breakout
            elif sell_cond and direction in ("both", "short"):
                position = "SHORT"
                entry_price = close[i]
                entry_bar = i
                entry_spread_cost = current_spread_cost

    # Close any remaining open position at last bar
    if position is not None:
        exit_price = close[-1]
        current_spread_cost = spread_pts[-1] * point
        if position == "LONG":
            pnl = (exit_price - entry_price) - entry_spread_cost - current_spread_cost
        else:
            pnl = (entry_price - exit_price) - entry_spread_cost - current_spread_cost
        trades.append({
            "entry_bar": entry_bar,
            "exit_bar": n - 1,
            "direction": position,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "bars_held": (n - 1) - entry_bar,
            "exit_reason": "end_of_data",
            "entry_time": str(df["time"].iloc[entry_bar]),
            "exit_time": str(df["time"].iloc[-1]),
        })

    if not trades:
        return None

    # Compute statistics
    pnls = np.array([t["pnl"] for t in trades])
    n_trades = len(pnls)
    wins = pnls > 0
    losses = pnls <= 0
    n_wins = int(wins.sum())
    n_losses = int(losses.sum())

    total_pnl = float(pnls.sum())
    win_rate = (n_wins / n_trades) * 100 if n_trades > 0 else 0

    gross_profit = float(pnls[wins].sum()) if n_wins > 0 else 0
    gross_loss = float(np.abs(pnls[losses].sum())) if n_losses > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0

    avg_win = float(pnls[wins].mean()) if n_wins > 0 else 0
    avg_loss = float(pnls[losses].mean()) if n_losses > 0 else 0

    # Drawdown
    cum_pnl = np.cumsum(pnls)
    running_max = np.maximum.accumulate(np.insert(cum_pnl, 0, 0))
    drawdowns = running_max[1:] - cum_pnl
    max_dd = float(drawdowns.max()) if len(drawdowns) > 0 else 0

    # Sharpe (annualized from trade PnLs)
    if len(pnls) > 1 and pnls.std() > 0:
        sharpe = float(pnls.mean() / pnls.std() * np.sqrt(min(n_trades, 252)))
    else:
        sharpe = 0.0

    # Average bars held
    avg_bars = float(np.mean([t["bars_held"] for t in trades]))

    # Long/short breakdown
    long_trades = [t for t in trades if t["direction"] == "LONG"]
    short_trades = [t for t in trades if t["direction"] == "SHORT"]
    long_pnl = sum(t["pnl"] for t in long_trades)
    short_pnl = sum(t["pnl"] for t in short_trades)

    return {
        "total_pnl": round(total_pnl, 2),
        "n_trades": n_trades,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_bars_held": round(avg_bars, 1),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "long_trades": len(long_trades),
        "long_pnl": round(long_pnl, 2),
        "short_trades": len(short_trades),
        "short_pnl": round(short_pnl, 2),
        "trades": trades,
        "date_range": f"{df['time'].iloc[0].date()} to {df['time'].iloc[-1].date()}",
        "bars": n,
    }


def main():
    print("=" * 70)
    print("DONCHIAN CHANNEL BREAKOUT - BACKTEST")
    print("=" * 70)
    print(f"Config: {CONFIG_PATH}")
    print(f"Data:   {DATA_DIR}")
    print()

    # Global strategy config
    strategy_cfg = CONFIG["strategy"]
    exit_cfg = CONFIG["exit_rules"]
    global_period = strategy_cfg["channel_period"]
    direction = strategy_cfg["direction"]
    exit_on_mid = exit_cfg["exit_on_mid_cross"]
    exit_on_opposite = exit_cfg["exit_on_opposite_breakout"]
    adx_min = strategy_cfg.get("adx_min_threshold", 0)
    adx_period = strategy_cfg.get("adx_period", 14)
    close_confirm = strategy_cfg.get("close_confirm", False)
    cooldown_bars = strategy_cfg.get("cooldown_bars", 0)

    print(f"Strategy: Donchian Channel Breakout")
    print(f"  Global Period: {global_period}")
    print(f"  Direction:     {direction}")
    print(f"  ADX Min:       {adx_min} (period={adx_period})")
    print(f"  Close Confirm: {close_confirm}")
    print(f"  Cooldown Bars: {cooldown_bars}")
    print(f"  Exit Mid Cross:       {exit_on_mid}")
    print(f"  Exit Opposite Break:  {exit_on_opposite}")
    print("-" * 70)

    enabled_symbols = CONFIG["symbols"]["enabled"]
    symbol_settings = CONFIG["symbols"]["settings"]

    results = []
    all_trades = []
    total_portfolio_pnl = 0.0
    total_portfolio_trades = 0

    for symbol in enabled_symbols:
        sym_cfg = symbol_settings.get(symbol, {})
        timeframe = sym_cfg.get("timeframe", "H1")
        period = sym_cfg.get("channel_period", global_period)
        volume = sym_cfg.get("volume", 0.01)

        print(f"\n{'─'*70}")
        print(f"  {symbol}  |  TF={timeframe}  |  Period={period}  |  Vol={volume}")
        print(f"{'─'*70}")

        df = load_data(symbol, timeframe)
        if df is None:
            print(f"  ⏭  Skipping {symbol} - no data")
            continue

        print(f"  Data: {len(df)} bars  |  {df['time'].iloc[0].date()} → {df['time'].iloc[-1].date()}")

        stats = run_backtest(df, period, sym_cfg, exit_on_mid, exit_on_opposite, direction,
                             adx_min=adx_min, adx_period=adx_period,
                             close_confirm=close_confirm, cooldown_bars=cooldown_bars)
        if stats is None:
            print(f"  ⏭  No trades generated")
            continue

        # Real dollar PnL = raw_price_pnl * volume * contract_size * fx_to_usd
        contract_size = sym_cfg.get("contract_size", 1)
        profit_currency = sym_cfg.get("profit_currency", "USD")
        fx_rate = FX_RATES.get(profit_currency, 1.0)
        dollar_per_point = volume * contract_size * fx_rate

        raw_pnl = stats["total_pnl"]
        scaled_pnl = raw_pnl * dollar_per_point

        # Print results
        pnl_color = "\033[92m" if scaled_pnl > 0 else "\033[91m"
        reset = "\033[0m"

        # Scale per-trade stats to real dollars
        avg_win_usd = stats['avg_win'] * dollar_per_point
        avg_loss_usd = stats['avg_loss'] * dollar_per_point
        max_dd_usd = stats['max_drawdown'] * dollar_per_point
        long_pnl_usd = stats['long_pnl'] * dollar_per_point
        short_pnl_usd = stats['short_pnl'] * dollar_per_point

        print(f"  Trades:  {stats['n_trades']}  ({stats['long_trades']}L / {stats['short_trades']}S)")
        print(f"  PnL:     {pnl_color}${scaled_pnl:+.2f}{reset}  (raw={raw_pnl:+.2f}pts × {volume}vol × {contract_size}cs × {fx_rate:.4f}fx)")
        print(f"  WinRate: {stats['win_rate']:.1f}%  ({stats['n_wins']}W / {stats['n_losses']}L)")
        print(f"  PF:      {stats['profit_factor']:.2f}  |  Sharpe: {stats['sharpe']:.2f}")
        print(f"  MaxDD:   ${max_dd_usd:+.2f}")
        print(f"  AvgWin:  ${avg_win_usd:+.2f}  |  AvgLoss: ${avg_loss_usd:+.2f}  |  AvgBars: {stats['avg_bars_held']:.0f}")
        print(f"  Long PnL: ${long_pnl_usd:+.2f}  |  Short PnL: ${short_pnl_usd:+.2f}")

        total_portfolio_pnl += scaled_pnl
        total_portfolio_trades += stats["n_trades"]

        # Collect for CSV
        results.append({
            "Symbol": symbol,
            "Timeframe": timeframe,
            "Period": period,
            "Volume": volume,
            "Contract_Size": contract_size,
            "Profit_Currency": profit_currency,
            "FX_Rate": round(fx_rate, 5),
            "Bars": stats["bars"],
            "Date_Range": stats["date_range"],
            "Trades": stats["n_trades"],
            "Wins": stats["n_wins"],
            "Losses": stats["n_losses"],
            "Win_Rate": stats["win_rate"],
            "PnL_Points": raw_pnl,
            "PnL_USD": round(scaled_pnl, 2),
            "Profit_Factor": stats["profit_factor"],
            "Sharpe": stats["sharpe"],
            "Max_DD_USD": round(max_dd_usd, 2),
            "Avg_Win_USD": round(avg_win_usd, 2),
            "Avg_Loss_USD": round(avg_loss_usd, 2),
            "Avg_Bars_Held": stats["avg_bars_held"],
            "Long_Trades": stats["long_trades"],
            "Long_PnL_USD": round(long_pnl_usd, 2),
            "Short_Trades": stats["short_trades"],
            "Short_PnL_USD": round(short_pnl_usd, 2),
        })

        # Collect individual trades
        for t in stats["trades"]:
            t["symbol"] = symbol
            t["timeframe"] = timeframe
            t["volume"] = volume
            all_trades.append(t)

    # ─── Portfolio Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PORTFOLIO SUMMARY")
    print("=" * 70)

    if results:
        pnl_color = "\033[92m" if total_portfolio_pnl > 0 else "\033[91m"
        reset = "\033[0m"

        print(f"  Symbols Traded: {len(results)}/{len(enabled_symbols)}")
        print(f"  Total Trades:   {total_portfolio_trades}")
        print(f"  Portfolio PnL:  {pnl_color}{total_portfolio_pnl:+.2f}{reset} (volume-scaled)")

        # Per-symbol summary table
        print(f"\n  {'Symbol':<12} {'TF':<5} {'Trades':>7} {'WR%':>6} {'PF':>6} {'PnL($)':>10} {'MaxDD($)':>10} {'AvgWin($)':>10} {'Sharpe':>7}")
        print(f"  {'─'*12} {'─'*5} {'─'*7} {'─'*6} {'─'*6} {'─'*10} {'─'*10} {'─'*10} {'─'*7}")
        for r in sorted(results, key=lambda x: x["PnL_USD"], reverse=True):
            c = "\033[92m" if r["PnL_USD"] > 0 else "\033[91m"
            print(f"  {r['Symbol']:<12} {r['Timeframe']:<5} {r['Trades']:>7} {r['Win_Rate']:>5.1f}% {r['Profit_Factor']:>6.2f} "
                  f"{c}{r['PnL_USD']:>+10.2f}{reset} {r['Max_DD_USD']:>10.2f} {r['Avg_Win_USD']:>10.2f} {r['Sharpe']:>7.2f}")

        # Save CSV
        df_results = pd.DataFrame(results)
        df_results.to_csv(OUTPUT_CSV, index=False)
        print(f"\n  Results saved to: {OUTPUT_CSV.name}")

        # Save trade log
        trade_log_path = SCRIPT_DIR / "GEN_02_backtest_trades.csv"
        df_trades = pd.DataFrame(all_trades)
        cols = ["symbol", "timeframe", "volume", "direction", "entry_time", "exit_time",
                "entry_price", "exit_price", "pnl", "bars_held", "exit_reason"]
        df_trades[[c for c in cols if c in df_trades.columns]].to_csv(trade_log_path, index=False)
        print(f"  Trade log saved to: {trade_log_path.name}")
    else:
        print("  No results to report.")

    print("=" * 70)


if __name__ == "__main__":
    main()
