#!/usr/bin/env python3
"""
================================================================================
MULTI-STRATEGY BACKTESTER - Compare 6 strategies against EMA Cross baseline
================================================================================

Strategies tested:
  1. EMA Cross (baseline)     - Fast/Slow EMA crossover
  2. RSI Mean Reversion       - Buy oversold, sell overbought
  3. MACD Crossover           - MACD line vs signal line
  4. Bollinger Band Reversion - Buy at lower band, sell at upper band
  5. Donchian Channel Breakout- Buy new highs, sell new lows
  6. RSI + EMA Combo          - RSI signals filtered by EMA trend

Uses same rolling Train/Validate/Test split as optimize.py.
Reads data directly from dataticks/ - no MT5 connection needed.
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────────────────

CONFIG = {
    "symbol_file": "GEN_01_liquid_symbols.csv",
    "data_dir": "dataticks",
    "output_file": "GEN_05_strategy_comparison.csv",
    "output_summary": "GEN_05_strategy_summary.csv",
    "timeframes": ["15m", "1h"],

    # Transaction costs
    "spread_multiplier": 1.0,
    "slippage_pips": 0,

    # Strategy parameter ranges for optimization
    "strategies": {
        "ema_cross": {
            "enabled": True,
            "params": [
                {"fast": 7, "slow": 21},
                {"fast": 9, "slow": 41},
                {"fast": 13, "slow": 55},
                {"fast": 21, "slow": 89},
            ]
        },
        "rsi_reversion": {
            "enabled": True,
            "params": [
                {"period": 14, "oversold": 30, "overbought": 70},
                {"period": 14, "oversold": 25, "overbought": 75},
                {"period": 7,  "oversold": 20, "overbought": 80},
                {"period": 21, "oversold": 35, "overbought": 65},
            ]
        },
        "macd": {
            "enabled": True,
            "params": [
                {"fast": 12, "slow": 26, "signal": 9},
                {"fast": 8,  "slow": 21, "signal": 5},
                {"fast": 5,  "slow": 35, "signal": 5},
            ]
        },
        "bollinger": {
            "enabled": True,
            "params": [
                {"period": 20, "std_dev": 2.0},
                {"period": 20, "std_dev": 2.5},
                {"period": 30, "std_dev": 2.0},
                {"period": 14, "std_dev": 1.5},
            ]
        },
        "donchian": {
            "enabled": True,
            "params": [
                {"period": 20},
                {"period": 14},
                {"period": 30},
                {"period": 55},
            ]
        },
        "rsi_ema_combo": {
            "enabled": True,
            "params": [
                {"rsi_period": 14, "ema_period": 50, "oversold": 40, "overbought": 60},
                {"rsi_period": 14, "ema_period": 100, "oversold": 35, "overbought": 65},
                {"rsi_period": 7,  "ema_period": 50, "oversold": 30, "overbought": 70},
            ]
        },
    },

    # Minimum thresholds
    "min_trades": 5,
}

# Allow config override from command line
if len(sys.argv) > 1:
    with open(sys.argv[1], 'r') as f:
        user_config = json.load(f)
    CONFIG.update(user_config)


# ─── Indicator Calculations ───────────────────────────────────────────────────

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bollinger(series, period=20, std_dev=2.0):
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


def calc_donchian(df, period=20):
    upper = df['high'].rolling(period).max()
    lower = df['low'].rolling(period).min()
    mid = (upper + lower) / 2
    return upper, mid, lower


# ─── Signal Generators ────────────────────────────────────────────────────────

def signals_ema_cross(df, params):
    """EMA Crossover: +1 when fast > slow, -1 when fast < slow"""
    fast_ema = calc_ema(df['close'], params['fast'])
    slow_ema = calc_ema(df['close'], params['slow'])
    signal = np.where(fast_ema > slow_ema, 1, -1)
    return signal


def signals_rsi_reversion(df, params):
    """RSI Mean Reversion: buy oversold, sell overbought, flat in between"""
    rsi = calc_rsi(df['close'], params['period'])
    signal = np.zeros(len(df))
    position = 0
    for i in range(1, len(df)):
        if rsi.iloc[i] < params['oversold']:
            position = 1  # Buy
        elif rsi.iloc[i] > params['overbought']:
            position = -1  # Sell
        # else hold current position
        signal[i] = position
    return signal


def signals_macd(df, params):
    """MACD Crossover: +1 when MACD > signal, -1 when MACD < signal"""
    macd_line, signal_line, _ = calc_macd(df['close'], params['fast'], params['slow'], params['signal'])
    signal = np.where(macd_line > signal_line, 1, -1)
    return signal


def signals_bollinger(df, params):
    """Bollinger Band Mean Reversion: buy at lower band, sell at upper band"""
    upper, mid, lower = calc_bollinger(df['close'], params['period'], params['std_dev'])
    signal = np.zeros(len(df))
    position = 0
    close = df['close'].values
    upper_v = upper.values
    lower_v = lower.values
    mid_v = mid.values
    for i in range(1, len(df)):
        if np.isnan(lower_v[i]):
            signal[i] = 0
            continue
        if close[i] <= lower_v[i]:
            position = 1   # Buy at lower band
        elif close[i] >= upper_v[i]:
            position = -1  # Sell at upper band
        elif position == 1 and close[i] >= mid_v[i]:
            position = 0   # Exit long at mid
        elif position == -1 and close[i] <= mid_v[i]:
            position = 0   # Exit short at mid
        signal[i] = position
    return signal


def signals_donchian(df, params):
    """Donchian Breakout: buy on new high, sell on new low"""
    upper, mid, lower = calc_donchian(df, params['period'])
    signal = np.zeros(len(df))
    position = 0
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    upper_v = upper.values
    lower_v = lower.values
    for i in range(1, len(df)):
        if np.isnan(upper_v[i]):
            signal[i] = 0
            continue
        if high[i] >= upper_v[i]:
            position = 1   # Breakout long
        elif low[i] <= lower_v[i]:
            position = -1  # Breakout short
        signal[i] = position
    return signal


def signals_rsi_ema_combo(df, params):
    """RSI filtered by EMA trend: only buy when above EMA + RSI oversold"""
    rsi = calc_rsi(df['close'], params['rsi_period'])
    ema = calc_ema(df['close'], params['ema_period'])
    signal = np.zeros(len(df))
    position = 0
    close = df['close'].values
    ema_v = ema.values
    for i in range(1, len(df)):
        if np.isnan(ema_v[i]):
            signal[i] = 0
            continue
        # Only long when price above EMA (uptrend) AND RSI oversold
        if close[i] > ema_v[i] and rsi.iloc[i] < params['oversold']:
            position = 1
        # Only short when price below EMA (downtrend) AND RSI overbought
        elif close[i] < ema_v[i] and rsi.iloc[i] > params['overbought']:
            position = -1
        # Exit long if price drops below EMA
        elif position == 1 and close[i] < ema_v[i]:
            position = 0
        # Exit short if price rises above EMA
        elif position == -1 and close[i] > ema_v[i]:
            position = 0
        signal[i] = position
    return signal


STRATEGY_MAP = {
    "ema_cross": signals_ema_cross,
    "rsi_reversion": signals_rsi_reversion,
    "macd": signals_macd,
    "bollinger": signals_bollinger,
    "donchian": signals_donchian,
    "rsi_ema_combo": signals_rsi_ema_combo,
}


# ─── Backtesting Engine ──────────────────────────────────────────────────────

def backtest(df, signal_array, spread_cost):
    """
    Run backtest given a signal array (+1 long, -1 short, 0 flat).
    Returns performance stats dict.
    """
    close = df['close'].values
    pos = signal_array.copy()

    # Calculate bar-by-bar PnL
    price_diffs = np.diff(close)
    positions = pos[:-1]

    # Identify trades (groups of consecutive same-direction positions)
    nonzero_mask = positions != 0
    if nonzero_mask.sum() == 0:
        return None

    # Trade segmentation
    change_mask = np.append([True], positions[1:] != positions[:-1])
    trade_ids = np.cumsum(change_mask)

    bar_returns = price_diffs * positions
    trade_pnls_gross = np.bincount(trade_ids - 1, weights=bar_returns)

    # Count actual position changes (entries) for spread cost
    entries = np.sum(change_mask & nonzero_mask)
    trade_pnls_net = trade_pnls_gross.copy()

    # Apply spread cost only to actual trades (not flat periods)
    trade_starts = np.where(change_mask)[0]
    trade_dirs = positions[trade_starts]
    active_trades = trade_dirs != 0

    for idx in np.where(active_trades)[0]:
        if idx < len(trade_pnls_net):
            trade_pnls_net[idx] -= spread_cost

    # Filter to actual trades only
    trade_pnls_net = trade_pnls_net[active_trades[:len(trade_pnls_net)]]

    num_trades = len(trade_pnls_net)
    if num_trades == 0:
        return None

    total_pnl = np.sum(trade_pnls_net)
    wins = trade_pnls_net > 0
    win_count = np.sum(wins)
    win_rate = (win_count / num_trades) * 100

    # Max drawdown
    cum_pnl = np.cumsum(trade_pnls_net)
    cum_pnl_padded = np.insert(cum_pnl, 0, 0)
    running_max = np.maximum.accumulate(cum_pnl_padded)
    dd = running_max - cum_pnl_padded
    max_dd = np.max(dd)

    # Profit factor
    gross_profit = np.sum(trade_pnls_net[wins]) if win_count > 0 else 0
    gross_loss = np.abs(np.sum(trade_pnls_net[~wins]))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    # Breakdown
    active_dirs = trade_dirs[active_trades[:len(trade_pnls_gross)]]
    long_mask = active_dirs == 1
    short_mask = active_dirs == -1

    return {
        'net_pnl': total_pnl,
        'count': num_trades,
        'win_rate': win_rate,
        'max_dd': max_dd,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'profit_factor': profit_factor,
        'long_pnl': np.sum(trade_pnls_net[long_mask[:len(trade_pnls_net)]]) if long_mask.any() else 0,
        'short_pnl': np.sum(trade_pnls_net[short_mask[:len(trade_pnls_net)]]) if short_mask.any() else 0,
        'long_trades': int(np.sum(long_mask)),
        'short_trades': int(np.sum(short_mask)),
    }


def calculate_fitness(stats):
    """Score a backtest result for parameter selection"""
    if stats is None or stats['count'] < CONFIG['min_trades']:
        return -float('inf')
    pnl = stats['net_pnl']
    max_dd = stats['max_dd']
    pf = stats['profit_factor']
    if pf < 1.0:
        return -float('inf')
    if max_dd == 0:
        return pnl
    return pnl / max_dd


# ─── Rolling Optimization ────────────────────────────────────────────────────

def rolling_optimize_strategy(df, strategy_name, param_list, spread_cost):
    """
    Rolling train/validate/test for a single strategy with multiple param sets.
    Returns aggregated test performance.
    """
    signal_fn = STRATEGY_MAP[strategy_name]

    df['year'] = df['time'].dt.year
    df['month'] = df['time'].dt.month
    df['yyyymm'] = df['year'] * 100 + df['month']
    unique_months = sorted(df['yyyymm'].unique())

    if len(unique_months) < 3:
        return None

    total_pnl = 0.0
    total_trades = 0
    total_wins = 0
    total_long_pnl = 0.0
    total_short_pnl = 0.0
    profit_factors = []
    monthly_pnls = []

    for i in range(len(unique_months) - 2):
        train_df = df[df['yyyymm'] == unique_months[i]].copy()
        val_df = df[df['yyyymm'] == unique_months[i + 1]].copy()
        test_df = df[df['yyyymm'] == unique_months[i + 2]].copy()

        if train_df.empty or val_df.empty or test_df.empty:
            continue

        # 1. Find best params on training month
        best_fitness = -float('inf')
        best_params = param_list[0]

        for params in param_list:
            try:
                sig = signal_fn(train_df, params)
                stats = backtest(train_df, sig, spread_cost)
                fitness = calculate_fitness(stats)
                if fitness > best_fitness:
                    best_fitness = fitness
                    best_params = params
            except Exception:
                continue

        # 2. Validate on validation month
        try:
            val_sig = signal_fn(val_df, best_params)
            val_stats = backtest(val_df, val_sig, spread_cost)
            val_fitness = calculate_fitness(val_stats)
            if val_fitness == -float('inf'):
                continue
        except Exception:
            continue

        # 3. Test on test month
        try:
            test_sig = signal_fn(test_df, best_params)
            test_stats = backtest(test_df, test_sig, spread_cost)
            if test_stats is None:
                continue

            total_pnl += test_stats['net_pnl']
            total_trades += test_stats['count']
            if test_stats['win_rate'] > 0:
                total_wins += int(test_stats['count'] * test_stats['win_rate'] / 100)
            total_long_pnl += test_stats.get('long_pnl', 0)
            total_short_pnl += test_stats.get('short_pnl', 0)
            profit_factors.append(test_stats['profit_factor'])
            monthly_pnls.append(test_stats['net_pnl'])
        except Exception:
            continue

    if total_trades == 0:
        return None

    avg_pf = np.mean(profit_factors) if profit_factors else 0
    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
    monthly_std = np.std(monthly_pnls) if len(monthly_pnls) > 1 else 0
    sharpe = (np.mean(monthly_pnls) / monthly_std) if monthly_std > 0 else 0

    return {
        'net_pnl': total_pnl,
        'count': total_trades,
        'win_rate': round(win_rate, 1),
        'profit_factor': round(avg_pf, 2),
        'long_pnl': total_long_pnl,
        'short_pnl': total_short_pnl,
        'monthly_sharpe': round(sharpe, 2),
        'months_tested': len(monthly_pnls),
        'months_profitable': sum(1 for p in monthly_pnls if p > 0),
    }


# ─── Main ────────────────────────────────────────────────────────────────────

def load_data(symbol, timeframe, data_dir):
    """Load OHLCV data from CSV"""
    filepath = os.path.join(data_dir, f"{symbol}_{timeframe}.csv")
    if not os.path.exists(filepath):
        return None
    try:
        df = pd.read_csv(filepath)
        df['time'] = pd.to_datetime(df['time'])
        df['close'] = df['close'].astype(float)
        for col in ['high', 'low', 'open']:
            if col not in df.columns:
                df[col] = df['close']
        if 'volume' not in df.columns:
            if 'tick_volume' in df.columns:
                df['volume'] = df['tick_volume']
            else:
                df['volume'] = 0
        return df
    except Exception as e:
        print(f"  Error loading {filepath}: {e}")
        return None


def estimate_spread_cost(symbol_row):
    """Estimate spread cost from symbol info"""
    try:
        spread_pct = float(symbol_row.get('Spread%', 0.05))
        price = float(symbol_row.get('Price', 1.0))
        return price * spread_pct / 100.0
    except (ValueError, TypeError):
        return 0.0001


def main():
    print("=" * 70)
    print("MULTI-STRATEGY COMPARISON BACKTESTER")
    print("=" * 70)
    print(f"  Strategies: {', '.join(s for s, cfg in CONFIG['strategies'].items() if cfg['enabled'])}")
    print(f"  Timeframes: {CONFIG['timeframes']}")
    print()

    # Load symbol list
    symbol_file = CONFIG['symbol_file']
    if not os.path.exists(symbol_file):
        print(f"Symbol file not found: {symbol_file}")
        return

    df_symbols = pd.read_csv(symbol_file)
    symbols = df_symbols['Symbol'].unique().tolist()
    print(f"Loaded {len(symbols)} symbols from {symbol_file}")
    print("-" * 70)

    # Create symbol info lookup
    symbol_info = {}
    for _, row in df_symbols.iterrows():
        symbol_info[row['Symbol']] = row

    all_results = []
    enabled_strategies = {k: v for k, v in CONFIG['strategies'].items() if v['enabled']}

    total_ops = len(symbols) * len(CONFIG['timeframes']) * len(enabled_strategies)
    current_op = 0

    for symbol in symbols:
        spread_cost = estimate_spread_cost(symbol_info.get(symbol, {}))

        for tf in CONFIG['timeframes']:
            df = load_data(symbol, tf, CONFIG['data_dir'])
            if df is None or len(df) < 100:
                current_op += len(enabled_strategies)
                continue

            for strat_name, strat_cfg in enabled_strategies.items():
                current_op += 1
                if current_op % 50 == 0:
                    print(f"  Progress: {current_op}/{total_ops} ({current_op/total_ops*100:.0f}%)")

                try:
                    result = rolling_optimize_strategy(
                        df, strat_name, strat_cfg['params'], spread_cost
                    )

                    if result:
                        record = {
                            'Symbol': symbol,
                            'Timeframe': tf,
                            'Strategy': strat_name,
                            'Test_PnL': round(result['net_pnl'], 2),
                            'Trades': result['count'],
                            'Win_Rate': result['win_rate'],
                            'Profit_Factor': result['profit_factor'],
                            'Long_PnL': round(result['long_pnl'], 2),
                            'Short_PnL': round(result['short_pnl'], 2),
                            'Monthly_Sharpe': result['monthly_sharpe'],
                            'Months_Tested': result['months_tested'],
                            'Months_Profitable': result['months_profitable'],
                        }
                        all_results.append(record)
                except Exception as e:
                    print(f"  Error: {symbol} {tf} {strat_name}: {e}")

    # ─── Save detailed results ────────────────────────────────────────────────
    if not all_results:
        print("\nNo results generated!")
        return

    df_results = pd.DataFrame(all_results)
    df_results.to_csv(CONFIG['output_file'], index=False)
    print(f"\nDetailed results saved to: {CONFIG['output_file']}")

    # ─── Generate strategy comparison summary ─────────────────────────────────
    print("\n" + "=" * 70)
    print("STRATEGY COMPARISON SUMMARY")
    print("=" * 70)

    summary_rows = []
    for strat_name in enabled_strategies:
        strat_data = df_results[df_results['Strategy'] == strat_name]
        if strat_data.empty:
            continue

        profitable = strat_data[strat_data['Test_PnL'] > 0]
        losing = strat_data[strat_data['Test_PnL'] <= 0]

        total_pnl = strat_data['Test_PnL'].sum()
        avg_pnl = strat_data['Test_PnL'].mean()
        median_pnl = strat_data['Test_PnL'].median()
        avg_pf = strat_data['Profit_Factor'].mean()
        avg_wr = strat_data['Win_Rate'].mean()
        avg_sharpe = strat_data['Monthly_Sharpe'].mean()
        pct_profitable = len(profitable) / len(strat_data) * 100 if len(strat_data) > 0 else 0

        row = {
            'Strategy': strat_name,
            'Total_Configs': len(strat_data),
            'Profitable_Configs': len(profitable),
            'Pct_Profitable': round(pct_profitable, 1),
            'Total_PnL': round(total_pnl, 2),
            'Avg_PnL': round(avg_pnl, 2),
            'Median_PnL': round(median_pnl, 2),
            'Avg_Profit_Factor': round(avg_pf, 2),
            'Avg_Win_Rate': round(avg_wr, 1),
            'Avg_Monthly_Sharpe': round(avg_sharpe, 2),
        }
        summary_rows.append(row)

        print(f"\n  {strat_name.upper()}")
        print(f"    Configs tested:  {len(strat_data)}")
        print(f"    Profitable:      {len(profitable)}/{len(strat_data)} ({pct_profitable:.0f}%)")
        print(f"    Total PnL:       {total_pnl:>12.2f}")
        print(f"    Avg PnL:         {avg_pnl:>12.2f}")
        print(f"    Median PnL:      {median_pnl:>12.2f}")
        print(f"    Avg PF:          {avg_pf:>12.2f}")
        print(f"    Avg Win Rate:    {avg_wr:>11.1f}%")
        print(f"    Avg Sharpe:      {avg_sharpe:>12.2f}")

    df_summary = pd.DataFrame(summary_rows)
    df_summary = df_summary.sort_values('Avg_PnL', ascending=False)
    df_summary.to_csv(CONFIG['output_summary'], index=False)
    print(f"\nSummary saved to: {CONFIG['output_summary']}")

    # ─── Top 10 best individual configs ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("TOP 15 BEST INDIVIDUAL SYMBOL/STRATEGY CONFIGS")
    print("=" * 70)

    top = df_results.sort_values('Test_PnL', ascending=False).head(15)
    for _, row in top.iterrows():
        print(f"  {row['Symbol']:<12} {row['Timeframe']:<5} {row['Strategy']:<18} "
              f"PnL={row['Test_PnL']:>10.2f}  PF={row['Profit_Factor']:.2f}  "
              f"WR={row['Win_Rate']:.0f}%  Sharpe={row['Monthly_Sharpe']:.2f}")

    # ─── Worst 10 ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("BOTTOM 10 WORST CONFIGS (avoid these)")
    print("=" * 70)

    bottom = df_results.sort_values('Test_PnL', ascending=True).head(10)
    for _, row in bottom.iterrows():
        print(f"  {row['Symbol']:<12} {row['Timeframe']:<5} {row['Strategy']:<18} "
              f"PnL={row['Test_PnL']:>10.2f}  PF={row['Profit_Factor']:.2f}")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()
