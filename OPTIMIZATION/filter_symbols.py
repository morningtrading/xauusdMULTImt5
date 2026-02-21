
import sys
import os
import time
import argparse
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import tabulate

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.mt5_connector import MT5Connector

def calculate_metrics(symbol_name, timeframe=mt5.TIMEFRAME_M5, bars=50):
    """
    Fetch price history and calculate spread/volume metrics
    """
    # Ensure symbol is selected to get fresh data
    if not mt5.symbol_select(symbol_name, True):
        return None
        
    # Get recent rates
    rates = mt5.copy_rates_from_pos(symbol_name, timeframe, 0, bars)
    
    if rates is None or len(rates) < 10:
        return None

    df = pd.DataFrame(rates)
    
    # Avg Volume
    if 'tick_volume' in df.columns:
        avg_volume = df['tick_volume'].mean()
    else:
        avg_volume = 0
    
    # Current Spread %
    tick = mt5.symbol_info_tick(symbol_name)
    if tick is None or tick.bid == 0:
        return None
        
    spread_points = tick.ask - tick.bid
    spread_percent = (spread_points / tick.bid) * 100
    
    # Price
    price = tick.bid
    
    # Determine Type/Category from Path
    sym_info = mt5.symbol_info(symbol_name)
    path = sym_info.path
    category = "Unknown"
    
    if path:
        parts = path.split('\\')
        if len(parts) > 0:
            category = parts[0]
            
    # Refine Category for Metals
    uname = symbol_name.upper()
    if "XAU" in uname or "GOLD" in uname:
        category = "Metal"
    elif "XAG" in uname or "SILVER" in uname:
        category = "Metal"
    elif "XPT" in uname or "PLAT" in uname:
        category = "Metal"
    elif "XPD" in uname or "PALL" in uname:
        category = "Metal"
    elif "COPPER" in uname:
        category = "Metal"
    
    return {
        "Symbol": symbol_name,
        "Type": category,
        "Price": price,
        "SpreadPoints": spread_points,
        "Spread%": round(spread_percent, 5),
        "AvgVolume": round(avg_volume, 0),
        "Contract": sym_info.trade_contract_size
    }

def main():
    parser = argparse.ArgumentParser(description='Filter symbols by Spread and Volume')
    parser.add_argument('--max-spread', type=float, default=0.05, help='Max Spread % (default: 0.05)')
    parser.add_argument('--min-vol', type=float, default=100, help='Min Avg Tick Volume (default: 100)')
    parser.add_argument('--limit', type=int, default=50, help='Limit results (default: 50)')
    
    args = parser.parse_args()
    
    print("Initializing MT5 Connection...")
    connector = MT5Connector()
    if not connector.connect():
        print("Failed to connect to MT5")
        return

    print("Fetching all symbols...")
    symbols = mt5.symbols_get()
    if not symbols:
        print("No symbols found")
        connector.disconnect()
        return

    print(f"Found {len(symbols)} symbols. Scanning and filtering...")
    print(f"Criteria: Spread% <= {args.max_spread}%, AvgVolume >= {args.min_vol}")
    
    results = []
    count = 0
    scanned = 0
    
    for sym in symbols:
        scanned += 1
        if scanned % 100 == 0:
            print(f"Scanning {scanned}/{len(symbols)}... Found: {len(results)}", end='\r')
            
        # Basic pre-filter check to save time
        # If symbol is not visible, select it? 
        # Selecting thousands of symbols might crash MT5 or be slow.
        # Let's try to query info first.
        
        try:
            # Skip if custom or disabled?
            # if not sym.visible: continue 
            
            metrics = calculate_metrics(sym.name)
            if not metrics:
                continue
                
            # FILTER
            if metrics['Spread%'] <= args.max_spread and metrics['AvgVolume'] >= args.min_vol:
                results.append(metrics)
                
        except Exception as e:
            continue
            
    print(f"\nScanning complete. Found {len(results)} matches.")
    
    if not results:
        print("No symbols matched the criteria.")
        connector.disconnect()
        return
        
    # Deduplicate: Remove non-USD pairs if USD pair exists
    # e.g. Remove BTCEUR if BTCUSD exists
    # Only applies to Crypto/Forex mostly, but logic can be generic
    
    print(f"Deduplicating {len(results)} results (preferring USD)...")
    
    # Create a set of USD symbols
    usd_symbols = set()
    for r in results:
        sym = r['Symbol']
        if sym.endswith("USD"):
            usd_symbols.add(sym)
            
    filtered_results = []
    dropped_count = 0
    
    # List of suffixes to check against
    suffixes = ["EUR", "GBP", "AUD", "NZD", "CAD", "CHF", "JPY", "SGD", "HKD", "CNH", "TRY", "MXN", "ZAR"]
    
    for r in results:
        sym = r['Symbol']
        
        # Check if this is a non-USD variant of an existing USD symbol
        is_duplicate = False
        for suf in suffixes:
            if sym.endswith(suf):
                base = sym[:-len(suf)]
                usd_variant = base + "USD"
                if usd_variant in usd_symbols:
                    # We have a USD variant, drop this one
                    is_duplicate = True
                    break
        
        if is_duplicate:
            dropped_count += 1
            continue
            
        filtered_results.append(r)
        
    print(f"Dropped {dropped_count} duplicates. Remaining: {len(filtered_results)}")
    results = filtered_results

    # Sort by Type then Spread% ascending
    df = pd.DataFrame(results)
    df = df.sort_values(by=["Type", "Spread%"])
    
    # Save to CSV
    filename = f"filtered_symbols_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(filename, index=False)
    print(f"Saved results to {filename}")
    
    # Display
    print("\n" + "="*80)
    print(f"TOP CANDIDATES (Spread < {args.max_spread}%, Vol > {args.min_vol})")
    print("="*80)
    
    print(tabulate.tabulate(df.head(args.limit), headers='keys', tablefmt='psql', showindex=False))
    
    # Generate JSON list for config
    print("\nJSON Format (for trading_config.json):")
    print(json.dumps(df['Symbol'].head(args.limit).tolist(), indent=4))

    connector.disconnect()

if __name__ == "__main__":
    import json
    main()
