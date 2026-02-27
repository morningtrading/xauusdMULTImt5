
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

# Allow config file to be passed as argument
CONFIG_FILE = sys.argv[1] if len(sys.argv) > 1 else "config_optimization.json"

def calculate_ema(prices, period):
    return prices.ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    """Calculate Average True Range"""
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    
    tr1 = high - low
    tr2 = np.abs(high - np.roll(close, 1))
    tr3 = np.abs(low - np.roll(close, 1))
    
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    tr[0] = tr1[0]  # First value
    
    atr = pd.Series(tr).ewm(span=period, adjust=False).mean().values
    return atr

def detect_regime(df, window=20, high_vol_threshold=1.5):
    """Detect market regime based on volatility"""
    returns = df['close'].pct_change()
    rolling_vol = returns.rolling(window=window).std()
    avg_vol = rolling_vol.mean()
    
    regime = np.where(rolling_vol > avg_vol * high_vol_threshold, 'high_vol', 'low_vol')
    return regime

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

def calculate_fitness(stats, config):
    """
    Calculate fitness score with risk adjustment
    """
    thresholds = config.get('thresholds', {})
    
    pnl = stats['net_pnl']
    max_dd = stats['max_dd']
    trades = stats['count']
    win_rate = stats['win_rate']
    
    # Hard filters
    if trades < thresholds.get('min_trades', 30):
        return -float('inf')
    
    if win_rate < thresholds.get('min_win_rate', 35.0):
        return -float('inf')
    
    # Calculate profit factor
    gross_profit = stats.get('gross_profit', 0)
    gross_loss = abs(stats.get('gross_loss', 1))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    if profit_factor < thresholds.get('min_profit_factor', 1.2):
        return -float('inf')
    
    # Return/Drawdown ratio
    if max_dd == 0:
        fitness = pnl
    else:
        fitness = pnl / max_dd
        
        # Check max DD to PnL ratio
        if pnl > 0 and max_dd / pnl > thresholds.get('max_dd_to_pnl_ratio', 2.0):
            return -float('inf')
    
    # Bonus for high win rate
    if win_rate > 45:
        fitness *= 1.2
    
    return fitness

def run_backtest_detailed(df, fast_ema, slow_ema, spread_cost, config):
    """Enhanced backtest with additional features"""
    if df.empty: return None
    
    # Check if required EMA columns exist
    fast_col = f'ema_{fast_ema}'
    slow_col = f'ema_{slow_ema}'
    
    if fast_col not in df.columns or slow_col not in df.columns:
        print(f"  Warning: Missing EMA columns ({fast_col}, {slow_col}) - skipping")
        return None
    
    features = config.get('features', {})
    use_volume_filter = features.get('use_volume_filter', False)
    use_trend_filter = features.get('use_trend_filter', False)
    use_atr_stops = features.get('use_atr_stops', False)
    
    f = df[fast_col].values
    s = df[slow_col].values
    close_prices = df['close'].values
    
    # Basic signal
    raw_signal = np.where(f > s, 1, -1)
    
    # Apply volume filter
    if use_volume_filter and 'volume' in df.columns:
        avg_volume = df['volume'].rolling(20).mean().values
        volume_mask = df['volume'].values > avg_volume
        volume_mask = np.nan_to_num(volume_mask, nan=True)
    else:
        volume_mask = np.ones(len(df), dtype=bool)
    
    # Apply trend filter (only long when above slow EMA, only short when below)
    if use_trend_filter:
        long_allowed = close_prices > s
        short_allowed = close_prices < s
        trend_signal = np.where(long_allowed, 1, np.where(short_allowed, -1, 0))
        signal = np.where((raw_signal == trend_signal) & volume_mask, raw_signal, 0)
    else:
        signal = np.where(volume_mask, raw_signal, 0)
    
    # Forward fill signals (hold position)
    pos = signal.copy()
    for i in range(1, len(pos)):
        if pos[i] == 0:
            pos[i] = pos[i-1]
    
    # Calculate returns
    price_diffs = np.diff(close_prices)
    positions = pos[:-1]
    
    # ATR-based stops
    if use_atr_stops and 'high' in df.columns and 'low' in df.columns:
        atr = df['atr'].values if 'atr' in df.columns else calculate_atr(df, features.get('atr_period', 14))
        atr_mult = features.get('atr_multiplier', 2.0)
        
        # Apply stops (simplified - check if loss exceeds ATR threshold)
        stops = atr[:-1] * atr_mult
        abs_pnl = np.abs(price_diffs * positions)
        stop_triggered = abs_pnl > stops
        # If stop triggered and losing, exit position
        losing_trades = (price_diffs * positions) < 0
        exit_mask = stop_triggered & losing_trades
        # Zero out those returns
        price_diffs = np.where(exit_mask, price_diffs * 0.5, price_diffs)  # Partial loss
    
    # Identify trades
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
            'long_pnl': 0.0, 'short_pnl': 0.0, 'long_trades': 0, 'short_trades': 0,
            'gross_profit': 0.0, 'gross_loss': 0.0, 'profit_factor': 0.0
        }

    # Breakdown Long/Short
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
    
    # Calculate max drawdown
    cum_pnl = np.cumsum(trade_pnls_net)
    cum_pnl_padded = np.insert(cum_pnl, 0, 0)
    running_max_padded = np.maximum.accumulate(cum_pnl_padded)
    dd_padded = running_max_padded - cum_pnl_padded
    max_dd = np.max(dd_padded)
    
    # Profit factor
    gross_profit = np.sum(trade_pnls_net[wins])
    gross_loss = np.abs(np.sum(trade_pnls_net[~wins]))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

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
        'short_trades': int(np.sum(short_mask)),
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'profit_factor': profit_factor
    }


def optimize_symbol_with_validation(mt5, symbol, timeframe, fast_range, slow_range, config):
    """
    Rolling optimization with validation split: Train -> Validate -> Test
    
    Note: Assumes data is already downloaded to dataticks/
    Run download_data.py first if needed, but typically data already exists.
    """
    # Get Info & Data
    info = mt5.get_symbol_info(symbol)
    if not info:
        print(f"{symbol:<10} | SKIP (No Info)")
        return None

    spread = info.get('spread', 20)
    point = info.get('point', 0.0001)
    
    # Apply spread multiplier and slippage
    tx_costs = config.get('transaction_costs', {})
    spread_mult = tx_costs.get('spread_multiplier', 1.0)
    slippage_pips = tx_costs.get('slippage_pips', 0)
    
    spread_cost = (spread * spread_mult + slippage_pips) * point
    
    print(f"Processing {symbol} [{timeframe}] (Spread: {spread}, Cost: {spread_cost:.5f})...")
    
    # Load Data (assumes data already exists in dataticks/)
    local_file = os.path.join("dataticks", f"{symbol}_{timeframe}.csv")
    
    if not os.path.exists(local_file):
        print(f"  {timeframe:<4}: Data file not found: {local_file}")
        print(f"  Run download_data.py if needed, but data should already exist.")
        return None
    
    try:
        df = pd.read_csv(local_file)
        df['time'] = pd.to_datetime(df['time'])
        df['close'] = df['close'].astype(float)
        
        # Ensure required columns
        if 'high' not in df.columns:
            df['high'] = df['close']
        if 'low' not in df.columns:
            df['low'] = df['close']
        if 'volume' not in df.columns:
            df['volume'] = 0
            
    except Exception as e:
        print(f"  Error loading {local_file}: {e}")
        return None

    df['year'] = df['time'].dt.year
    df['month'] = df['time'].dt.month
    
    # Pre-calc EMAs and ATR
    all_periods = set(fast_range) | set(slow_range)
    for p in all_periods:
        df[f'ema_{p}'] = calculate_ema(df['close'], p)
    
    if config.get('features', {}).get('use_atr_stops', False):
        df['atr'] = calculate_atr(df, config['features'].get('atr_period', 14))
    
    # Regime detection
    if config.get('regime_detection', {}).get('enabled', False):
        regime_window = config['regime_detection'].get('volatility_window', 20)
        regime_threshold = config['regime_detection'].get('high_vol_threshold', 1.5)
        df['regime'] = detect_regime(df, regime_window, regime_threshold)
    
    # Identify unique months
    df['yyyymm'] = df['year'] * 100 + df['month']
    unique_months = sorted(df['yyyymm'].unique())
    
    if len(unique_months) < 3:
        print(f"  {timeframe:<4}: Insufficient history ({len(unique_months)} months) for validation split.")
        return None
        
    print(f"  Rolling over {len(unique_months)} months with validation split...")
    
    total_test_pnl = 0.0
    total_trades = 0
    total_long_pnl = 0.0
    total_short_pnl = 0.0
    total_long_trades = 0
    total_short_trades = 0
    total_profit_factor = []
    
    # Rolling Loop: Train M, Validate M+1, Test M+2
    for i in range(len(unique_months) - 2):
        train_month = unique_months[i]
        val_month = unique_months[i+1]
        test_month = unique_months[i+2]
        
        train_df = df[df['yyyymm'] == train_month]
        val_df = df[df['yyyymm'] == val_month]
        test_df = df[df['yyyymm'] == test_month]
        
        if train_df.empty or val_df.empty or test_df.empty: 
            continue
        
        # 1. Optimize on Train Month
        best_fitness = -float('inf')
        # Initialize with first valid params from ranges
        best_params = (min(fast_range), min(slow_range))
        
        for f in fast_range:
            for s in slow_range:
                if f >= s: continue
                
                stats = run_backtest_detailed(train_df, f, s, spread_cost, config)
                if not stats: continue
                
                fitness = calculate_fitness(stats, config)
                
                if fitness > best_fitness:
                    best_fitness = fitness
                    best_params = (f, s)
        
        # 2. Validate on Val Month (ensure it still works)
        val_stats = run_backtest_detailed(val_df, best_params[0], best_params[1], spread_cost, config)
        val_fitness = calculate_fitness(val_stats, config)
        
        # If validation fails, skip this month
        if val_fitness == -float('inf'):
            print(f"    M:{test_month} | Params: {best_params} | FAILED VALIDATION")
            continue
                    
        # 3. Test on Test Month
        test_stats = run_backtest_detailed(test_df, best_params[0], best_params[1], spread_cost, config)
        
        pnl = test_stats['net_pnl']
        total_test_pnl += pnl
        total_trades += test_stats['count']
        
        # Accumulate Breakdown
        total_long_pnl += test_stats.get('long_pnl', 0)
        total_short_pnl += test_stats.get('short_pnl', 0)
        total_long_trades += test_stats.get('long_trades', 0)
        total_short_trades += test_stats.get('short_trades', 0)
        total_profit_factor.append(test_stats.get('profit_factor', 0))
        
        print(f"    M:{test_month} | Params: {best_params} | PnL: {pnl:.2f} | PF: {test_stats.get('profit_factor', 0):.2f}")

    avg_profit_factor = np.mean(total_profit_factor) if total_profit_factor else 0
    
    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'fast_ema': "Rolling",
        'slow_ema': "Rolling",
        'test_stats': {
            'net_pnl': total_test_pnl,
            'count': total_trades,
            'win_rate': 0.0,  # Placeholder
            'max_dd': 0.0,    # Placeholder
            'max_win_streak': 0,
            'max_loss_streak': 0,
            'long_pnl': total_long_pnl,
            'short_pnl': total_short_pnl,
            'long_trades': total_long_trades,
            'short_trades': total_short_trades,
            'profit_factor': avg_profit_factor
        },
        'train_pnl': 0.0
    }


def main():
    print("="*60)
    print(f"ENHANCED OPTIMIZATION WITH VALIDATION SPLIT")
    print("="*60)

    # Load Configuration
    if not os.path.exists(CONFIG_FILE):
        print(f"Config file {CONFIG_FILE} not found!")
        return

    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    input_csv_name = config.get("input_csv", "filtered_symbols_for_opt.csv")
    mode = config.get("mode", "rolling_validation")
    timeframes = config.get("timeframes", ["15m", "1h", "4h"])
    
    fast_conf = config.get("fast_ema", {"start": 7, "end": 38, "step": 3})
    slow_conf = config.get("slow_ema", {"start": 14, "end": 95, "step": 5})
    
    fast_range = range(fast_conf["start"], fast_conf["end"], fast_conf["step"])
    slow_range = range(slow_conf["start"], slow_conf["end"], slow_conf["step"])
    
    print(f"Config Loaded:")
    print(f"  Mode: {mode.upper()}")
    print(f"  Input: {input_csv_name}")
    print(f"  Timeframes: {timeframes}")
    print(f"  Fast EMA: {fast_conf['start']}-{fast_conf['end']} (step {fast_conf['step']})")
    print(f"  Slow EMA: {slow_conf['start']}-{slow_conf['end']} (step {slow_conf['step']})")
    print(f"  Combinations: {len(fast_range) * len(slow_range)}")
    print(f"  Features: Volume={config.get('features', {}).get('use_volume_filter')}, Trend={config.get('features', {}).get('use_trend_filter')}, ATR={config.get('features', {}).get('use_atr_stops')}")
    print(f"  Thresholds: MinTrades={config.get('thresholds', {}).get('min_trades')}, MinWR={config.get('thresholds', {}).get('min_win_rate')}%")
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
    
    total_ops = len(candidates) * len(timeframes)
    current_op = 0
    wins = 0
    total_test_pnl = 0.0

    for symbol in candidates:
        print(f"\n--- {symbol} ---")
        for tf in timeframes:
            current_op += 1
            
            try:
                res = optimize_symbol_with_validation(mt5_conn, symbol, tf, fast_range, slow_range, config)
                    
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
                        'Short_Trades': res['test_stats'].get('short_trades', 0),
                        'Profit_Factor': round(res['test_stats'].get('profit_factor', 0), 2)
                    }
                    results.append(csv_record)
                    
                    pnl = res['test_stats']['net_pnl']
                    total_test_pnl += pnl
                    if pnl > 0: wins += 1
            except Exception as e:
                print(f"Error processing {symbol} {tf}: {e}")
                import traceback
                traceback.print_exc()
            
    # Save Results
    if results:
        df_results = pd.DataFrame(results)
        output_file = "optimization_results_enhanced.csv"
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
