#!/usr/bin/env python3
"""
================================================================================
DONCHIAN CHANNEL OPTIMIZER
================================================================================
Optimizes Donchian channel_period for each symbol/timeframe using rolling
Train/Validate/Test split. No MT5 connection needed - reads from dataticks/.

Output: GEN_01_donchian_results.csv
================================================================================
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(os.path.dirname(__file__))
SYMBOL_FILE = os.path.join(SCRIPT_DIR, "..", "OPTIMIZATION2", "GEN_01_liquid_symbols.csv")
DATA_DIR = os.path.join(SCRIPT_DIR, "dataticks")
OUTPUT_FILE = "GEN_01_donchian_results.csv"
TIMEFRAMES = ["15m", "1h"]
PERIOD_RANGE = range(10, 56, 5)  # 10, 15, 20, 25, 30, 35, 40, 45, 50, 55
MIN_TRADES = 5


def load_fx_rates() -> dict:
    """Load average FX rates from dataticks for currency conversion to USD."""
    data_path = SCRIPT_DIR / "dataticks"
    rates = {'USD': 1.0}

    usdjpy_path = data_path / "USDJPY_1h.csv"
    if usdjpy_path.exists():
        df = pd.read_csv(usdjpy_path)
        rates['JPY'] = 1.0 / df['close'].astype(float).mean()
    else:
        rates['JPY'] = 1.0 / 153.0

    eurusd_path = data_path / "EURUSD_1h.csv"
    if eurusd_path.exists():
        df = pd.read_csv(eurusd_path)
        rates['EUR'] = df['close'].astype(float).mean()
    else:
        rates['EUR'] = 1.10

    gbpusd_path = data_path / "GBPUSD_1h.csv"
    if gbpusd_path.exists():
        df = pd.read_csv(gbpusd_path)
        rates['GBP'] = df['close'].astype(float).mean()
    else:
        rates['GBP'] = 1.27

    audusd_path = data_path / "AUDUSD_1h.csv"
    if audusd_path.exists():
        df = pd.read_csv(audusd_path)
        rates['AUD'] = df['close'].astype(float).mean()
    else:
        rates['AUD'] = 0.65

    return rates


def get_profit_currency(symbol: str) -> str:
    """Infer the profit currency from symbol name."""
    s = symbol.upper()
    # Forex pairs: profit currency is the quote (last 3 chars)
    if len(symbol) == 6 and symbol.isalpha():
        quote = s[3:6]
        return quote
    # JPY indices
    if any(x in s for x in ['NIKKEI', 'JPN225', 'TOPIX']):
        return 'JPY'
    # EUR indices
    if any(x in s for x in ['GER40', 'FRA40', 'ES35', 'NETH25', 'SWI20']):
        return 'EUR'
    # GBP indices
    if 'UK100' in s:
        return 'GBP'
    # AUD indices
    if 'ASX' in s or 'AUS200' in s:
        return 'AUD'
    # Metals/crypto with explicit USD
    if s.endswith('USD') or s.endswith('USD.CRP'):
        return 'USD'
    if s.endswith('JPY'):
        return 'JPY'
    if s.endswith('EUR'):
        return 'EUR'
    if s.endswith('AUD'):
        return 'AUD'
    if s.endswith('GBP'):
        return 'GBP'
    # Oil (USD-denominated)
    if any(x in s for x in ['OIL', 'CL-', 'USO', 'UKO']):
        return 'USD'
    # Default: USD
    return 'USD'


FX_RATES = load_fx_rates()


def load_data(symbol, timeframe):
    filepath = os.path.join(DATA_DIR, f"{symbol}_{timeframe}.csv")
    if not os.path.exists(filepath):
        return None
    try:
        df = pd.read_csv(filepath)
        df['time'] = pd.to_datetime(df['time'])
        df['close'] = df['close'].astype(float)
        for col in ['high', 'low', 'open']:
            if col not in df.columns:
                df[col] = df['close']
        return df
    except Exception:
        return None


def calculate_adx_array(high, low, close, period=14):
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


def donchian_signals(df, period, adx_min=20, adx_period=14,
                     close_confirm=True, cooldown_bars=3):
    """Generate Donchian breakout signals with ADX, close confirm, cooldown filters"""
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    n = len(df)
    signal = np.zeros(n)
    position = 0

    # Pre-compute ADX
    adx_values = np.zeros(n)
    if adx_min > 0:
        adx_values = calculate_adx_array(high, low, close, adx_period)

    last_exit_bar = -999

    for i in range(period, n):
        upper = np.max(high[i - period:i])
        lower = np.min(low[i - period:i])
        mid_ch = (upper + lower) / 2.0

        # Exit logic (simplified: mid cross)
        if position == 1 and close[i] < mid_ch:
            position = 0
            last_exit_bar = i
        elif position == -1 and close[i] > mid_ch:
            position = 0
            last_exit_bar = i

        # Entry logic
        if position == 0:
            # ADX filter
            if adx_min > 0 and adx_values[i] < adx_min:
                signal[i] = 0
                continue

            # Cooldown filter
            if cooldown_bars > 0 and (i - last_exit_bar) < cooldown_bars:
                signal[i] = 0
                continue

            # Breakout conditions
            if close_confirm:
                buy_cond = close[i] > upper
                sell_cond = close[i] < lower
            else:
                buy_cond = high[i] >= upper
                sell_cond = low[i] <= lower

            if buy_cond:
                position = 1
            elif sell_cond:
                position = -1

        signal[i] = position
    return signal


def backtest(df, signal_array, spread_cost):
    close = df['close'].values
    pos = signal_array.copy()
    price_diffs = np.diff(close)
    positions = pos[:-1]

    nonzero = positions != 0
    if nonzero.sum() == 0:
        return None

    change_mask = np.append([True], positions[1:] != positions[:-1])
    trade_ids = np.cumsum(change_mask)
    bar_returns = price_diffs * positions
    trade_pnls = np.bincount(trade_ids - 1, weights=bar_returns)

    trade_starts = np.where(change_mask)[0]
    trade_dirs = positions[trade_starts]
    active = trade_dirs != 0

    trade_pnls_net = trade_pnls.copy()
    for idx in np.where(active)[0]:
        if idx < len(trade_pnls_net):
            trade_pnls_net[idx] -= spread_cost

    trade_pnls_net = trade_pnls_net[active[:len(trade_pnls_net)]]
    n = len(trade_pnls_net)
    if n == 0:
        return None

    total_pnl = np.sum(trade_pnls_net)
    wins = trade_pnls_net > 0
    wc = np.sum(wins)
    wr = (wc / n) * 100

    gp = np.sum(trade_pnls_net[wins]) if wc > 0 else 0
    gl = np.abs(np.sum(trade_pnls_net[~wins]))
    pf = gp / gl if gl > 0 else 0

    cum = np.cumsum(trade_pnls_net)
    cum_p = np.insert(cum, 0, 0)
    rm = np.maximum.accumulate(cum_p)
    dd = np.max(rm - cum_p)

    return {'pnl': total_pnl, 'trades': n, 'wr': wr, 'pf': pf, 'dd': dd}


def fitness(stats):
    if stats is None or stats['trades'] < MIN_TRADES:
        return -float('inf')
    if stats['pf'] < 1.0:
        return -float('inf')
    if stats['dd'] == 0:
        return stats['pnl']
    return stats['pnl'] / stats['dd']


def estimate_spread(symbol_row):
    try:
        sp = float(symbol_row.get('Spread%', 0.05))
        pr = float(symbol_row.get('Price', 1.0))
        return pr * sp / 100.0
    except (ValueError, TypeError):
        return 0.0001


def main():
    print("=" * 60)
    print("DONCHIAN CHANNEL OPTIMIZER")
    print("=" * 60)
    print(f"  Periods: {list(PERIOD_RANGE)}")
    print(f"  Timeframes: {TIMEFRAMES}")

    print(f"  FX Rates: JPY={FX_RATES.get('JPY',0):.5f} EUR={FX_RATES.get('EUR',0):.4f} "
          f"GBP={FX_RATES.get('GBP',0):.4f} AUD={FX_RATES.get('AUD',0):.4f}")

    if not os.path.exists(SYMBOL_FILE):
        # Fallback: use config symbols
        config_path = os.path.join(os.path.dirname(__file__), "config", "trading_config.json")
        with open(config_path) as f:
            cfg = json.load(f)
        symbols = cfg['symbols']['enabled']
        symbol_info = {}
        print(f"  Using config symbols: {symbols}")
    else:
        df_sym = pd.read_csv(SYMBOL_FILE)
        symbols = df_sym['Symbol'].unique().tolist()
        symbol_info = {}
        for _, row in df_sym.iterrows():
            symbol_info[row['Symbol']] = row
        print(f"  Loaded {len(symbols)} symbols")

    print("-" * 60)

    results = []
    total = len(symbols) * len(TIMEFRAMES)
    current = 0

    for symbol in symbols:
        spread_cost = estimate_spread(symbol_info.get(symbol, {}))

        for tf in TIMEFRAMES:
            current += 1
            df = load_data(symbol, tf)
            if df is None or len(df) < 100:
                continue

            if current % 20 == 0:
                print(f"  Progress: {current}/{total}")

            df['year'] = df['time'].dt.year
            df['month'] = df['time'].dt.month
            df['yyyymm'] = df['year'] * 100 + df['month']
            months = sorted(df['yyyymm'].unique())

            if len(months) < 3:
                continue

            # Rolling optimization
            total_pnl = 0.0
            total_trades = 0
            monthly_pnls = []
            best_periods_used = []
            pfs = []

            for i in range(len(months) - 2):
                train = df[df['yyyymm'] == months[i]].copy()
                val = df[df['yyyymm'] == months[i + 1]].copy()
                test = df[df['yyyymm'] == months[i + 2]].copy()

                if train.empty or val.empty or test.empty:
                    continue

                # Find best period on train
                best_fit = -float('inf')
                best_p = 20

                for p in PERIOD_RANGE:
                    try:
                        sig = donchian_signals(train, p)
                        st = backtest(train, sig, spread_cost)
                        f = fitness(st)
                        if f > best_fit:
                            best_fit = f
                            best_p = p
                    except Exception:
                        continue

                # Validate
                try:
                    val_sig = donchian_signals(val, best_p)
                    val_st = backtest(val, val_sig, spread_cost)
                    if fitness(val_st) == -float('inf'):
                        continue
                except Exception:
                    continue

                # Test
                try:
                    test_sig = donchian_signals(test, best_p)
                    test_st = backtest(test, test_sig, spread_cost)
                    if test_st is None:
                        continue

                    total_pnl += test_st['pnl']
                    total_trades += test_st['trades']
                    monthly_pnls.append(test_st['pnl'])
                    best_periods_used.append(best_p)
                    pfs.append(test_st['pf'])
                except Exception:
                    continue

            if total_trades == 0:
                continue

            avg_pf = np.mean(pfs) if pfs else 0
            monthly_std = np.std(monthly_pnls) if len(monthly_pnls) > 1 else 0
            sharpe = (np.mean(monthly_pnls) / monthly_std) if monthly_std > 0 else 0
            most_used = max(set(best_periods_used), key=best_periods_used.count) if best_periods_used else 20

            # Convert raw PnL to USD using contract_size and FX rate
            sym_row = symbol_info.get(symbol, {})
            contract_size = float(sym_row.get('Contract', 1)) if hasattr(sym_row, 'get') else 1.0
            profit_ccy = get_profit_currency(symbol)
            fx_rate = FX_RATES.get(profit_ccy, 1.0)
            usd_pnl = total_pnl * contract_size * fx_rate

            record = {
                'Symbol': symbol,
                'Timeframe': tf,
                'Best_Period': most_used,
                'Test_PnL_Raw': round(total_pnl, 2),
                'Contract_Size': contract_size,
                'Profit_Currency': profit_ccy,
                'FX_Rate': round(fx_rate, 5),
                'Test_PnL_USD': round(usd_pnl, 2),
                'Trades': total_trades,
                'Avg_PF': round(avg_pf, 2),
                'Monthly_Sharpe': round(sharpe, 2),
                'Months_Tested': len(monthly_pnls),
                'Months_Profitable': sum(1 for p in monthly_pnls if p > 0),
            }
            results.append(record)

            if usd_pnl > 0:
                print(f"  ✅ {symbol:<12} {tf:<5} P={most_used:<3} PnL_USD={usd_pnl:>10.2f} PF={avg_pf:.2f} Sharpe={sharpe:.2f}")

    # Save
    if results:
        df_res = pd.DataFrame(results)
        df_res = df_res.sort_values('Test_PnL_USD', ascending=False)
        df_res.to_csv(OUTPUT_FILE, index=False)
        print(f"\nResults saved to: {OUTPUT_FILE}")

        # Summary
        profitable = df_res[df_res['Test_PnL_USD'] > 0]
        print(f"\n{'='*60}")
        print(f"SUMMARY: {len(profitable)}/{len(df_res)} configs profitable (USD)")
        print(f"Total PnL (USD): ${df_res['Test_PnL_USD'].sum():.2f}")
        print(f"\nTOP 10 (by USD PnL):")
        for _, r in df_res.head(10).iterrows():
            print(f"  {r['Symbol']:<12} {r['Timeframe']:<5} P={r['Best_Period']:<3} "
                  f"${r['Test_PnL_USD']:>+10.2f} ({r['Profit_Currency']}) "
                  f"PF={r['Avg_PF']:.2f} Sharpe={r['Monthly_Sharpe']:.2f}")
    else:
        print("No results!")


if __name__ == "__main__":
    main()
