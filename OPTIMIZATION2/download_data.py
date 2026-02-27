"""
Script: download_data.py
Description:
    Downloads market data (OHLCV) from MetaTrader 5 for a list of symbols provided in a CSV file.
    Supports multiple timeframes: 1m, 5m, 15m, 1h, 4h.
    Saves data to 'dataticks/' directory with filenames format: {Symbol}_{Timeframe}.csv

Usage:
    python3 download_data.py

Inputs:
    - filtered_symbols_YYYYMMDD_HHMMSS.csv: CSV file containing a 'Symbol' column.
      The script looks for this file in the current directory or '../scripts/'.
      You may need to update the INPUT_CSV variable to match the specific filename.

Outputs:
    - dataticks/{Symbol}_{Timeframe}.csv: CSV files containing time, open, high, low, close, tick_volume, spread, real_volume.

Dependencies:
    - MetaTrader5
    - pandas
    - sys, os, csv, time, datetime

Installation:
    pip install MetaTrader5 pandas

Context:
    Part of the EMAX Trading System.
    Used to gather historical data for strategy optimization and backtesting.
    Ensure MT5 is running and initialized before running this script.

Notes:
    - The script attempts to download the last 180 days of data for M1 and M5.
    - For H1 and H4, it also downloads the last 180 days (configurable).
    - If range download fails, it falls back to downloading the last 40,000 bars.
    - Ensure 'Auto Trading' is enabled in MT5 if required (though not strictly for data download).
    - The 'dataticks' directory will be created if it doesn't exist.

"""

import sys
import os
import csv
import time
import pandas as pd
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import numpy as np

# Add project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.mt5_connector import MT5Connector

# Configuration
INPUT_CSV_FILENAME = "filtered_symbols_20260218_195101.csv"
OUTPUT_DIR = "dataticks"

# Timeframes to download
TIMEFRAMES = {
    '1m': mt5.TIMEFRAME_M1,
    '5m': mt5.TIMEFRAME_M5,
    '15m': mt5.TIMEFRAME_M15,
    '1h': mt5.TIMEFRAME_H1,
    '4h': mt5.TIMEFRAME_H4
}

# Approx bars for 6 months (180 days)
# M1: 180 * 24 * 60 = 259,200 -> 300,000
# M5: 259,200 / 5 = 51,840 -> 60,000
# M15: 259,200 / 15 = 17,280 -> 20,000
# H1: 259,200 / 60 = 4,320 -> 5,000
# H4: 259,200 / 240 = 1,080 -> 2,000
BAR_COUNTS = {
    '1m': 300000,
    '5m': 60000,
    '15m': 20000,
    '1h': 5000,
    '4h': 2000
}

def get_input_csv_path():
    """Finds the input CSV file in current or parent/scripts directory."""
    # Check current directory
    if os.path.exists(INPUT_CSV_FILENAME):
        return INPUT_CSV_FILENAME
    
    # Check parent scripts directory
    scripts_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', INPUT_CSV_FILENAME)
    if os.path.exists(scripts_path):
        return scripts_path

    # Check project root directory
    root_path = os.path.join(os.path.dirname(__file__), '..', INPUT_CSV_FILENAME)
    if os.path.exists(root_path):
        return root_path
        
    return None

def main():
    if not os.path.exists(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR)
        except OSError as e:
            if not os.path.isdir(OUTPUT_DIR):
                print(f"Error creating directory {OUTPUT_DIR}: {e}")
                return

    print("Initializing MT5 Connection...")
    connector = MT5Connector()
    if not connector.connect():
        print("Failed to connect to MT5")
        return

    # Locate Input CSV
    input_csv_path = get_input_csv_path()
    if not input_csv_path:
        print(f"Input file {INPUT_CSV_FILENAME} not found in current directory or ../scripts/")
        return
        
    print(f"Reading symbols from: {input_csv_path}")
    df = pd.read_csv(input_csv_path)
    symbols = df['Symbol'].unique().tolist()
    
    # Sort symbols for consistent processing
    symbols.sort()
    
    print(f"Loaded {len(symbols)} symbols.")
    
    # Date Range: Last 6 Months (approx 180 days)
    date_to = datetime.now()
    date_from = date_to - timedelta(days=180)
    
    total_operations = len(symbols) * len(TIMEFRAMES)
    current_op = 0
    success_count = 0
    
    print(f"Starting download for timeframes: {', '.join(TIMEFRAMES.keys())}")
    
    for symbol in symbols:
        print(f"\nProcessing {symbol}:")
        
        # Ensure symbol is selected (triggers data sync)
        if not mt5.symbol_select(symbol, True):
            print(f"  Failed to select {symbol}")
            current_op += len(TIMEFRAMES)
            continue
            
        for tf_name, tf_value in TIMEFRAMES.items():
            current_op += 1
            print(f"  [{current_op}/{total_operations}] {tf_name:<3} ... ", end="", flush=True)
            
            rates = None
            
            # 1. Try Copy Rates Range
            for attempt in range(3):
                rates = mt5.copy_rates_range(symbol, tf_value, date_from, date_to)
                if rates is not None and len(rates) > 0:
                    # Validate coverage: Check if oldest bar is close enough to date_from
                    # If we missed more than 20 days of data, consider it a failure
                    # (Allow some buffer for weekends/holidays/market closures)
                    oldest_time = datetime.fromtimestamp(rates[0]['time'].astype(int))
                    days_missed = (oldest_time - date_from).days
                    
                    if days_missed > 20:
                        print(f"Range incomplete (missed {days_missed} days), forcing iterative download... ", end="", flush=True)
                        rates = None # Force fallback
                        break
                    else:
                        break
                time.sleep(1) 
            
            # 2. Fallback to Iterative Download if range fails
            if rates is None or len(rates) == 0:
                target_bars = BAR_COUNTS.get(tf_name, 50000)
                print(f"Range failed, trying to download ~{target_bars} bars iteratively... ", end="", flush=True)
                
                all_chunks = []
                chunk_size = 50000
                offset = 0
                
                while offset < target_bars:
                    # Request current chunk
                    current_chunk_size = min(chunk_size, target_bars - offset)
                    chunk = mt5.copy_rates_from_pos(symbol, tf_value, offset, current_chunk_size)
                    
                    if chunk is None or len(chunk) == 0:
                        break
                        
                    all_chunks.append(chunk)
                    
                    if len(chunk) < current_chunk_size:
                        # Less data returned than requested, meaning end of history
                        break
                        
                    offset += len(chunk)
                    
                    # Small pause to be nice to the server
                    time.sleep(0.1)
                
                if all_chunks:
                    try:
                        rates = np.concatenate(all_chunks)
                    except Exception as e:
                        print(f"Error concatenating chunks: {e}")
                        rates = None
                else:
                    rates = None
                
            if rates is None or len(rates) == 0:
                print("No data found")
                continue
                
            # Convert to DataFrame
            df_rates = pd.DataFrame(rates)
            
            # Ensure 'time' column exists before accessing it
            if 'time' not in df_rates.columns:
                print(f"Error: 'time' column missing. Columns: {df_rates.columns}")
                continue

            df_rates['time'] = pd.to_datetime(df_rates['time'], unit='s')
            
            df_rates = df_rates.sort_values('time')
            df_rates = df_rates.drop_duplicates(subset=['time']) # Safety
            
            # Save to CSV
            # Filename format: Symbol_TF.csv (e.g. BTCUSD_1m.csv)
            filename = os.path.join(OUTPUT_DIR, f"{symbol}_{tf_name}.csv")
            df_rates.to_csv(filename, index=False)
            
            start_str = df_rates['time'].min().strftime('%Y-%m-%d')
            end_str = df_rates['time'].max().strftime('%Y-%m-%d')
            print(f"Saved {len(df_rates)} rows ({start_str} to {end_str})")
            success_count += 1
            
    print(f"\nDownload complete.")
    print(f"Successfully processed {success_count}/{total_operations} timeframe files.")
    print(f"Data saved to: {os.path.abspath(OUTPUT_DIR)}")
    
    connector.disconnect()

if __name__ == "__main__":
    main()
