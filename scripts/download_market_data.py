
import sys
import os
import csv
import time
import pandas as pd
from datetime import datetime
import MetaTrader5 as mt5

# Add project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.mt5_connector import MT5Connector

INPUT_CSV = "filtered_symbols_20260218_195101.csv"
OUTPUT_DIR = "dataticks"

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    print("Initializing MT5 Connection...")
    connector = MT5Connector()
    if not connector.connect():
        print("Failed to connect to MT5")
        return

    # Read symbols
    if not os.path.exists(INPUT_CSV):
        print(f"Input file {INPUT_CSV} not found.")
        return
        
    df = pd.read_csv(INPUT_CSV)
    symbols = df['Symbol'].unique().tolist()
    
    print(f"Loaded {len(symbols)} symbols. Starting download (M5, Last 6 Months)...")
    
    # Date Range: Last 6 Months
    from datetime import timedelta
    date_to = datetime.now()
    date_from = date_to - timedelta(days=180)
    
    count = 0
    success = 0
    
    for symbol in symbols:
        count += 1
        print(f"[{count}/{len(symbols)}] {symbol:<10} ... ", end="", flush=True)
        
        # Ensure symbol is selected (triggers data sync)
        if not mt5.symbol_select(symbol, True):
            print("Failed to select")
            continue
            
        # Try Data Range First (Last 6 Months)
        rates = None
        for attempt in range(3):
            rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, date_from, date_to)
            if rates is not None and len(rates) > 0:
                break
            time.sleep(1) # Wait for data download
            
        # Fallback: exact bars if range fails (e.g. server time issues)
        if rates is None or len(rates) == 0:
            print("Range failed, trying last 40k bars... ", end="", flush=True)
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 40000)
            
        if rates is None or len(rates) == 0:
            print("No data found")
            continue
            
        # Convert to DataFrame
        df_rates = pd.DataFrame(rates)
        df_rates['time'] = pd.to_datetime(df_rates['time'], unit='s')
        
        # Save to CSV
        # Filename format: Symbol_M5.csv
        filename = os.path.join(OUTPUT_DIR, f"{symbol}_M5.csv")
        df_rates.to_csv(filename, index=False)
        
        print(f"Saved {len(df_rates)} rows")
        success += 1
        
    print(f"\nDownload complete. Successfully downloaded {success}/{len(symbols)} symbols to '{OUTPUT_DIR}/'.")
    connector.disconnect()

if __name__ == "__main__":
    main()
