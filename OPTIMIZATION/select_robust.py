
import sys
import os
import json
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

def run_backtest_simple(df, fast_ema, slow_ema, spread_cost):
    if df.empty: return 0.0
    f = df[f'ema_{fast_ema}'].values
    s = df[f'ema_{slow_ema}'].values
    pos = np.where(f > s, 1, -1)
    trades = np.diff(pos)
    num_trades = np.count_nonzero(trades)
    if num_trades == 0: return 0.0
    
    price_changes = np.diff(df['close'].values)
    strategy_returns = price_changes * pos[:-1]
    gross_pnl = np.sum(strategy_returns)
    net_pnl = gross_pnl - (num_trades * spread_cost)
    return net_pnl

def check_robustness(mt5, symbol, fast_range, slow_range):
    # 1. Get Info
    info = mt5.get_symbol_info(symbol)
    if not info: return None

    spread = info.get('spread', 20)
    point = info.get('point', 0.0001)
    spread_cost = spread * point
    
    # 2. Load Data
    import os
    local_file = os.path.join("dataticks", f"{symbol}_M5.csv")
    df = pd.DataFrame()
    
    if os.path.exists(local_file):
        try:
            df = pd.read_csv(local_file)
            df['time'] = pd.to_datetime(df['time'])
            df['close'] = df['close'].astype(float)
        except: pass
            
    if df.empty: return None

    df['month'] = df['time'].dt.month
    
    # Pre-calc EMAs
    all_periods = set(fast_range) | set(slow_range)
    for p in all_periods:
        df[f'ema_{p}'] = calculate_ema(df['close'], p)
        
    # --- PHASE 1: NORMAL OPTIMIZATION (Train ODD, Test EVEN) ---
    # This mimics what is currently in config. We re-calc to confirm.
    train_norm = df[df['month'] % 2 != 0].copy()
    test_norm = df[df['month'] % 2 == 0].copy()
    
    # Optimize Normal
    best_norm_pnl = -float('inf')
    best_norm_params = (9, 21)
    
    for f in fast_range:
        for s in slow_range:
            if f >= s: continue
            pnl = run_backtest_simple(train_norm, f, s, spread_cost)
            if pnl > best_norm_pnl:
                best_norm_pnl = pnl
                best_norm_params = (f, s)
                
    # Validate Normal (Test EVEN)
    norm_test_pnl = run_backtest_simple(test_norm, best_norm_params[0], best_norm_params[1], spread_cost)
    
    # --- PHASE 2: INVERTED OPTIMIZATION (Train EVEN, Test ODD) ---
    train_inv = df[df['month'] % 2 == 0].copy()
    test_inv = df[df['month'] % 2 != 0].copy()
    
    # Optimize Inverted
    best_inv_pnl = -float('inf')
    best_inv_params = (9, 21)
    
    for f in fast_range:
        for s in slow_range:
            if f >= s: continue
            pnl = run_backtest_simple(train_inv, f, s, spread_cost)
            if pnl > best_inv_pnl:
                best_inv_pnl = pnl
                best_inv_params = (f, s)
                
    # Validate Inverted (Test ODD)
    inv_test_pnl = run_backtest_simple(test_inv, best_inv_params[0], best_inv_params[1], spread_cost)
    
    return {
        'symbol': symbol,
        'norm_test_pnl': norm_test_pnl,
        'inv_test_pnl': inv_test_pnl,
        'robust': (norm_test_pnl > 0 and inv_test_pnl > 0)
    }

def update_config_robust(robust_symbols):
    config_path = Path('config/trading_config.json')
    if not config_path.exists(): return
        
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    enabled = config.get('symbols', {}).get('enabled', [])
    settings = config.get('symbols', {}).get('settings', {})
    
    # Filter enabled list
    new_enabled = [s for s in robust_symbols if s in enabled]
    
    # Update settings
    for s in settings:
        if s not in new_enabled:
            settings[s]['enabled'] = False
        else:
            settings[s]['enabled'] = True
            
    config['symbols']['enabled'] = new_enabled
    config['symbols']['settings'] = settings
    
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
        
    print(f"\nUpdated Config. Kept {len(new_enabled)} Robust Symbols.")

def main():
    print("="*60)
    print("SELECTING ROBUST CORE (Profitable in Both Splits)")
    print("="*60)
    
    mt5_conn = MT5Connector()
    if not mt5_conn.connect(): return

    # Load currently enabled
    config_path = Path('config/trading_config.json')
    if not config_path.exists(): return
    with open(config_path, 'r') as f:
        config = json.load(f)
    candidates = config.get('symbols', {}).get('enabled', [])
    
    print(f"Checking {len(candidates)} enabled candidates...")

    # Ranges (Step 2 is enough for robustness check speed)
    fast_range = range(5, 30, 2)
    slow_range = range(20, 80, 5)

    robust_list = []
    
    count = 0
    for symbol in candidates:
        count += 1
        print(f"[{count}/{len(candidates)}] {symbol:<10} ... ", end="", flush=True)
        try:
            res = check_robustness(mt5_conn, symbol, fast_range, slow_range)
            if res:
                if res['robust']:
                    print(f"ROBUST (Norm: {res['norm_test_pnl']:.0f}, Inv: {res['inv_test_pnl']:.0f})")
                    robust_list.append(symbol)
                else:
                    print(f"Weak   (Norm: {res['norm_test_pnl']:.0f}, Inv: {res['inv_test_pnl']:.0f})")
            else:
                print("Error")
        except Exception as e:
            print(f"Error: {e}")
            
    print("\nRobust Symbols Identified:")
    print(", ".join(robust_list))
    
    if len(robust_list) > 0:
        update_config_robust(robust_list)
    else:
        print("No robust symbols found! No changes made.")
    
    mt5_conn.disconnect()
    print("Done.")

if __name__ == "__main__":
    main()
