
import sys
import os
import json
from datetime import datetime
import MetaTrader5 as mt5

# Add project root to path
# Add project root to path (parent of scripts/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.mt5_connector import MT5Connector

def debug_symbol(symbol):
    print(f"\n--- Debugging {symbol} ---")
    
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"❌ symbol_info({symbol}) returned None")
        return

    print(f"Select success: {mt5.symbol_select(symbol, True)}")
    
    # Print as dict to see all properties
    print(info._asdict())

def main():
    connector = MT5Connector()
    if not connector.connect():
        print("Failed to start MT5")
        return
    
    # Calculate server offset to debug time differences
    print(f"\nServer Time Offset: {connector.server_time_offset}")
    current_server_time = datetime.now().timestamp() - connector.server_time_offset
    print(f"Estimated Server Time: {datetime.fromtimestamp(current_server_time)}")
    
    # Check ARKB specifically for connection/stops issues
    symbols_to_check = ["ARKB"]
    
    for sym in symbols_to_check:
        print(f"\n--- Checking {sym} ---")
        info = mt5.symbol_info(sym)
        if not info:
            print("Symbol not found")
            continue
            
        print(f"Trade Mode: {info.trade_mode}")
        print(f"Stops Level: {info.trade_stops_level}")
        print(f"Freeze Level: {info.trade_freeze_level}")
        print(f"Point: {info.point}")
        print(f"Digits: {info.digits}")
        print(f"Ask: {info.ask}")
        print(f"Bid: {info.bid}")
        print(f"Spread: {info.spread}")
        print(f"Contract Size: {info.trade_contract_size}")
        
        # Calculate min stop distance
        min_dist = info.trade_stops_level * info.point
        print(f"Min Stop Distance: {min_dist}")
        
        tick = mt5.symbol_info_tick(sym)
        if tick:
            print(f"Tick Time: {datetime.fromtimestamp(tick.time)} ({tick.time})")
            staleness = current_server_time - tick.time
            print(f"Staleness: {staleness:.2f} seconds")
        else:
            print("No tick data")
            
        is_open = connector.is_market_open(sym)
        print(f"is_market_open: {is_open}")
    
    # Check for Nasdaq symbols
    print("\nSearching for Nasdaq symbols...")
    for query in ["*NAS*", "*100*", "*NDX*", "*TECH*"]:
        print(f"Query: {query}")
        symbols = mt5.symbols_get(group=query)
        if symbols:
            for s in symbols:
                print(f"Found: {s.name} (TradeMode: {s.trade_mode})")

    mt5.shutdown()

if __name__ == "__main__":
    main()
