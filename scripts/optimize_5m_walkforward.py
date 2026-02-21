
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

INPUT_CSV = "filtered_symbols_20260218_195101.csv"

def calculate_ema(prices, period):
    return prices.ewm(span=period, adjust=False).mean()

def get_max_consecutive(sequence, val_type):
    """
    Counts max consecutive occurances of val_type (True/False)
    """
    # Create change points
    if len(sequence) == 0: return 0
    
    # 1 for Match, 0 for Non-Match
    binary = (sequence == val_type).astype(int)
    
    # Pad with 0 at both ends
    d = np.diff(np.concatenate(([0], binary, [0])))
    
    # Starts are where diff is 1, ends are where diff is -1
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    
    if len(starts) == 0: return 0
    return np.max(ends - starts)

def run_backtest_detailed(df, fast_ema, slow_ema, spread_cost):
    if df.empty: return None
    
    # 1. Calculate Signals
    f = df[f'ema_{fast_ema}'].values
    s = df[f'ema_{slow_ema}'].values
    
    # Position: 1 (Long), -1 (Short)
    # Using 'valid' signals (f != s) usually, but simplicity: f > s
    pos = np.where(f > s, 1, -1)
    
    # 2. Per-Bar Returns
    # Returns at [i] = (Price[i+1] - Price[i]) * Pos[i]
    # We use diff on prices. 
    price_diffs = np.diff(df['close'].values) # len = N-1
    # positions held during those diffs are pos[:-1]
    positions = pos[:-1]
    
    # 3. Identify Trades
    # A new trade starts when position changes
    # Use 0 as initial comparison to force first segment to be a trade
    # Actually, simplistic view: 
    #   positions: 1 1 1 -1 -1
    #   trades:    A A A  B  B
    #   Changes at index 3
    
    # Compare i with i-1. 
    # Prepend a value different from first to ensure first is a "change" (start)
    # But for correct grouping, we just need unique IDs
    
    # change_mask: True where pos[i] != pos[i-1]
    change_mask = np.append([True], positions[1:] != positions[:-1])
    trade_ids = np.cumsum(change_mask) # 1-based IDs
    
    # 4. Aggregate Returns by Trade
    bar_returns = price_diffs * positions
    
    # Fast grouping using bincount
    # trade_ids are 1..M. bincount needs 0..M-1
    trade_pnls_gross = np.bincount(trade_ids - 1, weights=bar_returns)
    
    # 5. Apply Spread Cost
    # Each trade pays spread once (on entry or exit, effectively per transaction)
    # Since we reverse, we pay full spread
    trade_pnls_net = trade_pnls_gross - spread_cost
    
    # 6. Calculate Stats
    num_trades = len(trade_pnls_net)
    if num_trades == 0:
        return {'net_pnl': 0.0, 'count': 0, 'win_rate': 0.0, 'max_win_streak': 0, 'max_loss_streak': 0, 'max_dd': 0.0}

    total_pnl = np.sum(trade_pnls_net)
    
    # Win Rate
    wins = trade_pnls_net > 0
    win_count = np.sum(wins)
    win_rate = (win_count / num_trades) * 100
    
    # Consecutive
    max_win_streak = get_max_consecutive(wins, True)
    max_loss_streak = get_max_consecutive(wins, False)
    
    # Drawdown (based on Cumulative PnL)
    cum_pnl = np.cumsum(trade_pnls_net)
    running_max = np.maximum.accumulate(cum_pnl)
    drawdowns = running_max - cum_pnl
    max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0.0
    
    # Add initial drawdown if first trades are losses (running_max starts at first val)
    # Standard DD calc usually assumes starting at 0 equity.
    # Let's verify: 
    #   pnl: -10, -10, 20
    #   cum: -10, -20, 0
    #   max: -10, -10, 0
    #   dd:   0,  10,  0 -> Max DD 10. Correct? 
    #   Real equity: 0 -> -10 -> -20. DD is 20.
    # Fix: Prepend 0 to cum_pnl
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
        'max_dd': max_dd
    }

def optimize_symbol(mt5, symbol, fast_range, slow_range):
    # 1. Get Info & Data
    info = mt5.get_symbol_info(symbol)
    if not info:
        print(f"{symbol:<10} | SKIP (No Info)")
        return None

    spread = info.get('spread', 20)
    point = info.get('point', 0.0001)
    spread_cost = spread * point
    
    print(f"\nProcessing {symbol} (Spread: {spread})...")
    
    # Load Data
    tf = "M5"
    import os
    local_file = os.path.join("dataticks", f"{symbol}_M5.csv")
    df = pd.DataFrame()
    
    if os.path.exists(local_file):
        try:
            df = pd.read_csv(local_file)
            df['time'] = pd.to_datetime(df['time'])
            df['close'] = df['close'].astype(float)
        except: pass
            
    if df.empty:
        # Last resort fallback if local missing
        date_from = datetime(2025, 1, 1) # dummy
        date_to = datetime.now()
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 20000)
        if rates is None or len(rates) == 0:
             print(f"  {tf:<4}: No data")
             return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df['close'] = df['close'].astype(float)

    df['month'] = df['time'].dt.month
    
    # Pre-calc EMAs
    all_periods = set(fast_range) | set(slow_range)
    for p in all_periods:
        df[f'ema_{p}'] = calculate_ema(df['close'], p)
        
    train_df = df[df['month'] % 2 != 0].copy() # Odd Months = Train
    test_df = df[df['month'] % 2 == 0].copy()  # Even Months = Test (Inverted)
    
    if train_df.empty or test_df.empty:
        print(f"  {tf:<4}: Insufficient split")
        return None
        
    # 2. Optimize (Grid Search)
    best_train_pnl = -float('inf')
    best_params = (9, 21)
    
    for f in fast_range:
        for s in slow_range:
            if f >= s: continue
            
            # For optimization loop, we only need PnL to sort
            # Using run_backtest_detailed is slightly slower but safe
            stats = run_backtest_detailed(train_df, f, s, spread_cost)
            if not stats: continue
            
            pnl = stats['net_pnl']
            if pnl > best_train_pnl:
                best_train_pnl = pnl
                best_params = (f, s)
    
    # 3. Validate (Get Full Stats)
    final_stats = run_backtest_detailed(test_df, best_params[0], best_params[1], spread_cost)
    
    # Log Result
    print(f"  {tf:<4}: Best {best_params} | Train: {best_train_pnl:.2f} | Test: {final_stats['net_pnl']:.2f} (WR: {final_stats['win_rate']:.1f}%)")
    
    return {
        'symbol': symbol,
        'timeframe': tf,
        'fast_ema': best_params[0],
        'slow_ema': best_params[1],
        'test_stats': final_stats,
        'train_pnl': best_train_pnl
    }

# def update_config(results_map, output_symbols):
#     # DISABLED FOR SIMULATION
#     pass

def main():
    print("="*60)
    print(f"5M INVERTED OPTIMIZATION (Train: ODD, Test: EVEN)")
    print("="*60)
    print("NOTE: Configuration will NOT be updated.")
    
    mt5_conn = MT5Connector()
    if not mt5_conn.connect(): return

    if not os.path.exists(INPUT_CSV):
        print(f"{INPUT_CSV} not found!")
        return

    df = pd.read_csv(INPUT_CSV)
    all_candidates = df['Symbol'].unique().tolist()

    # Filter by Config Enabled List
    config_path = Path('config/trading_config.json')
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
        enabled_list = config.get('symbols', {}).get('enabled', [])
        candidates = [s for s in all_candidates if s in enabled_list]
        print(f"Loaded {len(candidates)} enabled candidates (filtered from {len(all_candidates)} total).")
    else:
        candidates = all_candidates
        print(f"Loaded {len(candidates)} candidates (Config not found).")

    # Ranges with Step 1
    fast_range = range(5, 30, 1)
    slow_range = range(20, 80, 1)

    results = {}
    count = 0
    total_test_pnl = 0.0
    wins = 0
    
    for symbol in candidates:
        count += 1
        print(f"[{count}/{len(candidates)}] ", end="")
        try:
            res = optimize_symbol(mt5_conn, symbol, fast_range, slow_range)
            if res: 
                results[symbol] = res
                pnl = res['test_stats']['net_pnl']
                total_test_pnl += pnl
                if pnl > 0: wins += 1
        except Exception as e:
            print(f"Error: {e}")
            
    # update_config(results, candidates) # DISABLED
    
    print("\n" + "="*60)
    print("INVERTED SIMULATION RESULTS (85 Symbols)")
    print("="*60)
    print(f"Total Test PnL: {total_test_pnl:.2f}")
    print(f"Profitable: {wins}/{len(results)} ({(wins/len(results))*100:.1f}%)" if results else "No results")
    print(f"Average PnL: {total_test_pnl/len(results):.2f}" if results else "N/A")
    
    mt5_conn.disconnect()
    print("Done.")

if __name__ == "__main__":
    main()
