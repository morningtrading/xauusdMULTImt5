
import sys
import os
import json
import time
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mt5_connector import MT5Connector

CONFIG_FILE = "config_optimization.json"

def calculate_ema(prices, period):
    return prices.ewm(span=period, adjust=False).mean()

def get_max_consecutive(sequence, val_type):
    """
    Counts max consecutive occurances of val_type (True/False)
    """
    if len(sequence) == 0: return 0
    binary = (sequence == val_type).astype(int)
    d = np.diff(np.concatenate(([0], binary, [0])))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    if len(starts) == 0: return 0
    return np.max(ends - starts)

def run_backtest_detailed(df, fast_ema, slow_ema, spread_cost):
    if df.empty: return None
    
    f = df[f'ema_{fast_ema}'].values
    s = df[f'ema_{slow_ema}'].values
    pos = np.where(f > s, 1, -1)
    
    price_diffs = np.diff(df['close'].values)
    positions = pos[:-1]
    
    change_mask = np.append([True], positions[1:] != positions[:-1])
    trade_ids = np.cumsum(change_mask)
    
    bar_returns = price_diffs * positions
    trade_pnls_gross = np.bincount(trade_ids - 1, weights=bar_returns)

    trade_pnls_net = trade_pnls_gross - spread_cost
    
    num_trades = len(trade_pnls_net)
    if num_trades == 0:
        return {
            'net_pnl': 0.0, 'count': 0, 'win_rate': 0.0, 
            'max_win_streak': 0, 'max_loss_streak': 0, 'max_dd': 0.0,
            'long_pnl': 0.0, 'short_pnl': 0.0, 'long_trades': 0, 'short_trades': 0
        }

    # Breakdown Long/Short
    # trade_ids starts at 1, positions aligned with trade_starts
    trade_starts = np.where(change_mask)[0]
    trade_dirs = positions[trade_starts]
    
    long_mask = (trade_dirs == 1)
    short_mask = (trade_dirs == -1)
    
    long_pnls = trade_pnls_net[long_mask]
    short_pnls = trade_pnls_net[short_mask]
    
    total_pnl = np.sum(trade_pnls_net)
    wins = trade_pnls_net > 0
    win_count = np.sum(wins)
    win_rate = (win_count / num_trades) * 100
    
    max_win_streak = get_max_consecutive(wins, True)
    max_loss_streak = get_max_consecutive(wins, False)
    
    cum_pnl = np.cumsum(trade_pnls_net)
    cum_pnl_padded = np.insert(cum_pnl, 0, 0)
    running_max_padded = np.maximum.accumulate(cum_pnl_padded)
    dd_padded = running_max_padded - cum_pnl_padded
    max_dd = np.max(dd_padded)

    return {
        'net_pnl': total_pnl,
        'count': num_trades,
        'win_rate': win_rate,
        'max_win_streak': int(max_win_streak),
        'max_loss_streak': int(max_loss_streak),
        'max_dd': max_dd,
        'long_pnl': np.sum(long_pnls),
        'short_pnl': np.sum(short_pnls),
        'long_trades': int(np.sum(long_mask)),
        'short_trades': int(np.sum(short_mask))
    }


def optimize_symbol_rolling(mt5, symbol, timeframe, fast_range, slow_range):
    # 1. Get Info & Data
    info = mt5.get_symbol_info(symbol)
    if not info:
        print(f"{symbol:<10} | SKIP (No Info)")
        return None

    spread = info.get('spread', 20)
    point = info.get('point', 0.0001)
    spread_cost = spread * point
    
    print(f"Processing {symbol} [{timeframe}] (Spread: {spread})...")
    
    # Load Data
    local_file = os.path.join("dataticks", f"{symbol}_{timeframe}.csv")
    df = pd.DataFrame()
    
    if os.path.exists(local_file):
        try:
            df = pd.read_csv(local_file)
            df['time'] = pd.to_datetime(df['time'])
            df['close'] = df['close'].astype(float)
        except Exception as e:
             print(f"  Error loading {local_file}: {e}")
            
    if df.empty:
         print(f"  {timeframe:<4}: No local data found at {local_file}")
         return None

    df['year'] = df['time'].dt.year
    df['month'] = df['time'].dt.month
    
    # Pre-calc EMAs
    all_periods = set(fast_range) | set(slow_range)
    for p in all_periods:
        df[f'ema_{p}'] = calculate_ema(df['close'], p)
    
    # Identify unique months (chronological)
    # create a sortable key: YYYYMM
    df['yyyymm'] = df['year'] * 100 + df['month']
    unique_months = sorted(df['yyyymm'].unique())
    
    if len(unique_months) < 2:
        print(f"  {timeframe:<4}: Insufficient history ({len(unique_months)} months) for rolling opt.")
        return None
        
    print(f"  Rolling over {len(unique_months)} months: {unique_months}")
    
    total_test_pnl = 0.0
    total_trades = 0
    total_long_pnl = 0.0
    total_short_pnl = 0.0
    total_long_trades = 0
    total_short_trades = 0
    wins = 0
    all_dates_pnl = [] # To calc MaxDD over full period
    
    # Rolling Loop: Train M, Test M+1
    for i in range(len(unique_months) - 1):
        train_month = unique_months[i]
        test_month = unique_months[i+1]
        
        train_df = df[df['yyyymm'] == train_month]
        test_df = df[df['yyyymm'] == test_month]
        
        if train_df.empty or test_df.empty: continue
        
        # 1. Optimize on Train Month
        best_train_pnl = -float('inf')
        best_params = (9, 21)
        
        for f in fast_range:
            for s in slow_range:
                if f >= s: continue
                
                stats = run_backtest_detailed(train_df, f, s, spread_cost)
                if not stats: continue
                
                if stats['net_pnl'] > best_train_pnl:
                    best_train_pnl = stats['net_pnl']
                    best_params = (f, s)
                    
        # 2. Test on Next Month
        test_stats = run_backtest_detailed(test_df, best_params[0], best_params[1], spread_cost)
        
        pnl = test_stats['net_pnl']
        total_test_pnl += pnl
        total_trades += test_stats['count']
        if pnl > 0: wins += 1 # This is per-month win, not per-trade, careful. 
        # Actually standard stats count trades. 
        # We need to aggregate trade-level data to get true Win Rate and MaxDD.
        # For simplicity in this summary, we sum PnL.
        # But 'wins' in results usually means profitable TRADES.
        # Let's just track PnL for now. To get true WR, we'd need to collect all trades.
        
        # Accumulate Breakdown
        total_long_pnl += test_stats.get('long_pnl', 0)
        total_short_pnl += test_stats.get('short_pnl', 0)
        total_long_trades += test_stats.get('long_trades', 0)
        total_short_trades += test_stats.get('short_trades', 0)
        
        print(f"    M:{test_month} | Params: {best_params} | PnL: {pnl:.2f}")

    # For full stats (MaxDD, WR), ideally we re-run backtest on concatenated periods with their respective params.
    # OR simpler: just report Total PnL and average monthly PnL.
    # The 'run_backtest_detailed' returns aggregate stats. Summing them (like trades) works, but WR needs weighting.
    
    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'fast_ema': "Rolling",
        'slow_ema': "Rolling",
        'test_stats': {
            'net_pnl': total_test_pnl,
            'count': total_trades,
            'win_rate': 0.0, # Placeholder
            'max_dd': 0.0,   # Placeholder
            'max_win_streak': 0,
            'max_loss_streak': 0,
            'long_pnl': total_long_pnl,
            'short_pnl': total_short_pnl,
            'long_trades': total_long_trades,
            'short_trades': total_short_trades
        },
        'train_pnl': 0.0 # N/A
    }

def optimize_symbol_static(mt5, symbol, timeframe, fast_range, slow_range):
    # 1. Get Info & Data
    info = mt5.get_symbol_info(symbol)
    if not info:
        print(f"{symbol:<10} | SKIP (No Info)")
        return None

    spread = info.get('spread', 20)
    point = info.get('point', 0.0001)
    spread_cost = spread * point
    
    print(f"Processing {symbol} [{timeframe}] (Spread: {spread})...")
    
    # Load Data
    # Filename format from download_data.py: Symbol_TF.csv
    # Config timeframes: "1m", "5m", "15m", "1h", "4h"
    # Files are likely: AAPL_1m.csv, AAPL_5m.csv...
    # NOTE: download_data.py uses strict suffix based on what we feed it.
    
    local_file = os.path.join("dataticks", f"{symbol}_{timeframe}.csv")
    df = pd.DataFrame()
    
    if os.path.exists(local_file):
        try:
            df = pd.read_csv(local_file)
            df['time'] = pd.to_datetime(df['time'])
            df['close'] = df['close'].astype(float)
        except Exception as e:
             print(f"  Error loading {local_file}: {e}")
            
    if df.empty:
         print(f"  {timeframe:<4}: No local data found at {local_file}")
         return None

    df['month'] = df['time'].dt.month
    
    # Pre-calc EMAs
    all_periods = set(fast_range) | set(slow_range)
    for p in all_periods:
        df[f'ema_{p}'] = calculate_ema(df['close'], p)
        
    train_df = df[df['month'] % 2 != 0].copy() # Odd Months = Train
    test_df = df[df['month'] % 2 == 0].copy()  # Even Months = Test (Inverted)
    
    if train_df.empty or test_df.empty:
        print(f"  {timeframe:<4}: Insufficient split (Train: {len(train_df)}, Test: {len(test_df)})")
        return None
        
    # 2. Optimize (Grid Search)
    best_train_pnl = -float('inf')
    best_params = (9, 21)
    
    for f in fast_range:
        for s in slow_range:
            if f >= s: continue
            
            stats = run_backtest_detailed(train_df, f, s, spread_cost)
            if not stats: continue
            
            pnl = stats['net_pnl']
            if pnl > best_train_pnl:
                best_train_pnl = pnl
                best_params = (f, s)
    
    # 3. Validate (Get Full Stats)
    final_stats = run_backtest_detailed(test_df, best_params[0], best_params[1], spread_cost)
    
    # Log Result
    print(f"  Best {best_params} | Train: {best_train_pnl:.2f} | Test: {final_stats['net_pnl']:.2f} (WR: {final_stats['win_rate']:.1f}%)")
    
    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'fast_ema': best_params[0],
        'slow_ema': best_params[1],
        'test_stats': final_stats,
        'train_pnl': best_train_pnl
    }

def main():
    print("="*60)
    print(f"CONFIGURABLE OPTIMIZATION SWEEP")
    print("="*60)

    # Load Configuration
    if not os.path.exists(CONFIG_FILE):
        print(f"Config file {CONFIG_FILE} not found!")
        return

    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    input_csv_name = config.get("input_csv", "filtered_symbols_20260218_195101.csv")
    mode = config.get("mode", "static") # static or rolling
    timeframes = config.get("timeframes", ["5m"])
    
    fast_conf = config.get("fast_ema", {"start": 7, "end": 38, "step": 1})
    slow_conf = config.get("slow_ema", {"start": 14, "end": 95, "step": 1})
    
    fast_range = range(fast_conf["start"], fast_conf["end"], fast_conf["step"])
    slow_range = range(slow_conf["start"], slow_conf["end"], slow_conf["step"])
    
    print(f"Config Loaded:")
    print(f"  Mode: {mode.upper()}")
    print(f"  Input: {input_csv_name}")
    print(f"  Timeframes: {timeframes}")
    print(f"  Fast EMA: {fast_conf['start']}-{fast_conf['end']} (step {fast_conf['step']})")
    print(f"  Slow EMA: {slow_conf['start']}-{slow_conf['end']} (step {slow_conf['step']})")
    print("-" * 60)
    
    mt5_conn = MT5Connector()
    if not mt5_conn.connect(): return

    # Load Symbols
    if os.path.exists(input_csv_name):
        input_file = input_csv_name
    elif os.path.exists(os.path.join("..", input_csv_name)):
        input_file = os.path.join("..", input_csv_name)
    else:
        print(f"Input CSV {input_csv_name} not found!")
        return

    df_symbols = pd.read_csv(input_file)
    candidates = df_symbols['Symbol'].unique().tolist()
    print(f"Loaded {len(candidates)} candidates.")

    results = []
    
    # Iterate Timeframes first or Symbols first?
    # Interactive grouping suggests iterating symbols then timeframes within?
    # Or Timeframes outer loop to keep cache hot? 
    # Actually loading CSV per file. Order doesn't matter much.
    # Let's do Symbol -> Timeframes to print progress per symbol.
    
    total_ops = len(candidates) * len(timeframes)
    current_op = 0
    wins = 0
    total_test_pnl = 0.0

    for symbol in candidates:
        print(f"\n--- {symbol} ---")
        for tf in timeframes:
            current_op += 1
            # print(f"[{current_op}/{total_ops}] ", end="")
            
            try:
                res = None
                if mode == "rolling":
                    res = optimize_symbol_rolling(mt5_conn, symbol, tf, fast_range, slow_range)
                else:
                    res = optimize_symbol_static(mt5_conn, symbol, tf, fast_range, slow_range)
                    
                if res: 
                    csv_record = {
                        'Symbol': res['symbol'],
                        'Timeframe': res['timeframe'],
                        'Fast_EMA': res['fast_ema'],
                        'Slow_EMA': res['slow_ema'],
                        'Train_PnL': round(res['train_pnl'], 2),
                        'Test_PnL': round(res['test_stats']['net_pnl'], 2),
                        'Trades': res['test_stats']['count'],
                        'Win_Rate': round(res['test_stats']['win_rate'], 1),
                        'Max_DD': round(res['test_stats']['max_dd'], 2),
                        'Streak_W': res['test_stats']['max_win_streak'],
                        'Streak_L': res['test_stats']['max_loss_streak'],
                        'Long_PnL': round(res['test_stats'].get('long_pnl', 0), 2),
                        'Short_PnL': round(res['test_stats'].get('short_pnl', 0), 2),
                        'Long_Trades': res['test_stats'].get('long_trades', 0),
                        'Short_Trades': res['test_stats'].get('short_trades', 0)
                    }
                    results.append(csv_record)
                    
                    pnl = res['test_stats']['net_pnl']
                    total_test_pnl += pnl
                    if pnl > 0: wins += 1
            except Exception as e:
                print(f"Error processing {symbol} {tf}: {e}")
                # traceback
                import traceback
                traceback.print_exc()
            
    # Save Results
    if results:
        df_results = pd.DataFrame(results)
        output_file = "optimization_rolling.csv" if mode == "rolling" else "optimization_results.csv"
        df_results.to_csv(output_file, index=False)
        print(f"\nResults saved to: {output_file}")
    
    print("\n" + "="*60)
    print(f"OPTIMIZATION RESULTS ({len(results)} Entries)")
    print("="*60)
    print(f"Total Test PnL: {total_test_pnl:.2f}")
    if results:
        print(f"Profitable: {wins}/{len(results)} ({(wins/len(results))*100:.1f}%)")
        print(f"Average PnL: {total_test_pnl/len(results):.2f}")
    else:
        print("No results found.")
    
    mt5_conn.disconnect()
    print("Done.")

if __name__ == "__main__":
    main()
