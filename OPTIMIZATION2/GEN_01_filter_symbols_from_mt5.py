#!/usr/bin/env -S wine python
"""
GEN_01_filter_symbols_from_mt5.py

Fetch ALL symbols from MT5, calculate spread and volume stats, 
then filter to keep only liquid, reasonable-spread assets.

Output: GEN_01_liquid_symbols.csv

Note: Must run with Wine Python for MT5 access: wine python GEN_01_filter_symbols_from_mt5.py
"""

import sys
import os
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, timedelta

# Add project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.mt5_connector import MT5Connector

# Filter Configuration
MAX_SPREAD_PCT = 0.30  # 0.30% max spread (filters out crazy spreads)
MIN_AVG_VOLUME = 1000   # Minimum average volume per bar (filters illiquid)
MIN_BARS_REQUIRED = 400  # Need enough history for backtesting (~20 days H1)

def get_symbol_type(symbol_name):
    """Classify symbol type based on naming conventions."""
    symbol_upper = symbol_name.upper()
    
    # Forex majors and crosses
    if any(pair in symbol_upper for pair in ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF']):
        if any(x in symbol_upper for x in ['CNH', 'PLN', 'NOK', 'SEK', 'TRY', 'MXN', 'ZAR', 'BRL']):
            return 'Forex'
        if len(symbol_name) == 6 and not any(x in symbol_upper for x in ['USD.', 'EUR.', 'GBP.']):
            return 'Forex Major'
    
    # Crypto
    if any(x in symbol_upper for x in ['BTC', 'ETH', 'LTC', 'USDT']):
        return 'Crypto Currency'
    
    # Metals
    if any(x in symbol_upper for x in ['XAU', 'XAG', 'GOLD', 'SILVER', 'COPPER']):
        return 'Metal'
    
    # Oil
    if any(x in symbol_upper for x in ['OIL', 'USOIL', 'UKOIL', 'CL-']):
        return 'Oil'
    
    # Gas
    if 'GAS' in symbol_upper:
        return 'Commodities'
    
    # Indices
    if any(x in symbol_upper for x in ['DJ30', 'NAS100', 'SP500', 'GER40', 'UK100', 'HK50', 
                                         'NIKKEI', 'JPN225', 'ES35', 'FRA40', 'SWI20',
                                         'BVSPX', 'CHINAH', 'HKTECH', 'IND50', 'NETH25',
                                         'SA40', 'TWINDEX', 'US2000']):
        return 'CFDs'
    
    # ETFs
    if any(x in symbol_upper for x in ['SPY', 'QQQ', 'IWM', 'XLK', 'GLD', 'GDX', 
                                         'ARKK', 'VGT', 'FAZ', 'FDN', 'GBTC', 'BTCO']):
        return 'ETF'
    
    # Individual stocks
    if any(x in symbol_upper for x in ['AAPL', 'TSLA', 'NVIDIA', 'AMAZON', 'GOOG', 
                                         'MSFT', 'AMD', 'PLTR', 'MU', 'EXXON']):
        return 'Stocks'
    
    return 'Other'

def calculate_spread_stats(symbol, connector):
    """
    Calculate spread statistics for a symbol using recent H1 data.
    Returns: (current_price, spread_points, spread_pct, avg_volume, contract_size, bar_count)
    """
    # Get symbol info
    info = mt5.symbol_info(symbol)
    if info is None:
        return None, None, None, None, None, 0
    
    # Ensure symbol is selected
    if not mt5.symbol_select(symbol, True):
        return None, None, None, None, None, 0
    
    # Get recent H1 bars (last 30 days = ~720 bars)
    date_to = datetime.now()
    date_from = date_to - timedelta(days=30)
    
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, date_from, date_to)
    
    if rates is None or len(rates) < 100:  # Need at least 100 bars
        return None, None, None, None, None, len(rates) if rates is not None else 0
    
    df = pd.DataFrame(rates)
    
    # Calculate average spread
    avg_spread_points = (info.ask - info.bid)  # Current spread
    
    # Calculate average volume
    avg_volume = df['tick_volume'].mean()
    
    # Current price (midpoint)
    current_price = (info.ask + info.bid) / 2
    
    # Spread percentage
    spread_pct = (avg_spread_points / current_price) * 100 if current_price > 0 else 0
    
    # Contract size
    contract_size = info.trade_contract_size
    
    return current_price, avg_spread_points, spread_pct, avg_volume, contract_size, len(rates)

def main():
    print("=" * 70)
    print("MT5 Symbol Liquidity Filter")
    print("=" * 70)
    print(f"\nFilter Criteria:")
    print(f"  - Max Spread: {MAX_SPREAD_PCT}%")
    print(f"  - Min Volume: {MIN_AVG_VOLUME} per bar")
    print(f"  - Min History: {MIN_BARS_REQUIRED} bars (H1)")
    print()
    
    # Connect to MT5
    print("Connecting to MT5...")
    connector = MT5Connector()
    if not connector.connect():
        print("ERROR Failed to connect to MT5")
        return
    
    print("OK Connected to MT5\n")
    
    # Get all symbols
    all_symbols = mt5.symbols_get()
    if all_symbols is None:
        print("ERROR Failed to get symbols from MT5")
        return
    
    print(f"Found {len(all_symbols)} total symbols in MT5\n")
    print("Analyzing symbols (this may take a few minutes)...\n")
    
    results = []
    processed = 0
    
    for sym_info in all_symbols:
        symbol = sym_info.name
        processed += 1
        
        if processed % 50 == 0:
            print(f"  Processed {processed}/{len(all_symbols)} symbols...")
        
        # Calculate spread and volume stats
        price, spread_points, spread_pct, avg_volume, contract_size, bar_count = \
            calculate_spread_stats(symbol, connector)
        
        if price is None or spread_pct is None or avg_volume is None:
            continue
        
        # Get symbol type
        sym_type = get_symbol_type(symbol)
        
        results.append({
            'Symbol': symbol,
            'Type': sym_type,
            'Price': round(price, 5),
            'SpreadPoints': round(spread_points, 5),
            'Spread%': round(spread_pct, 5),
            'AvgVolume': round(avg_volume, 0),
            'Contract': contract_size,
            'Bars': bar_count
        })
    
    print(f"\nOK Analyzed {len(results)} symbols\n")
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Save raw results
    raw_output = 'GEN_01_all_symbols_raw.csv'
    df.to_csv(raw_output, index=False)
    print(f"File: Saved raw data: {raw_output}")
    
    # Apply filters
    print(f"\nApplying filters...")
    df_filtered = df[
        (df['Spread%'] <= MAX_SPREAD_PCT) &
        (df['AvgVolume'] >= MIN_AVG_VOLUME) &
        (df['Bars'] >= MIN_BARS_REQUIRED)
    ].copy()
    
    # Sort by spread quality (lower spread % = better)
    df_filtered = df_filtered.sort_values('Spread%')
    
    # Save filtered results
    filtered_output = 'GEN_01_liquid_symbols.csv'
    df_filtered.to_csv(filtered_output, index=False)
    
    print(f"OK Filtered: {len(df_filtered)} / {len(df)} symbols passed\n")
    
    # Summary statistics
    print("=" * 70)
    print("SUMMARY BY ASSET TYPE")
    print("=" * 70)
    summary = df_filtered.groupby('Type').agg({
        'Symbol': 'count',
        'Spread%': 'mean',
        'AvgVolume': 'mean'
    }).round(3)
    summary.columns = ['Count', 'Avg Spread%', 'Avg Volume']
    print(summary.to_string())
    
    print(f"\nFile: Saved filtered symbols: {filtered_output}")
    print(f"\nOK Ready for optimization!\n")
    
    # Show some examples
    print("=" * 70)
    print("TOP 20 SYMBOLS (by spread quality)")
    print("=" * 70)
    print(df_filtered[['Symbol', 'Type', 'Spread%', 'AvgVolume']].head(20).to_string(index=False))
    
    mt5.shutdown()

if __name__ == '__main__':
    main()
