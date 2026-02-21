
import sys
import os
from datetime import datetime
import logging

# Add project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.mt5_connector import MT5Connector
from core.position_manager import PositionManager

# Setup basic logging
logging.basicConfig(level=logging.INFO)

def main():
    print("Connecting to MT5...")
    connector = MT5Connector()
    if not connector.connect():
        print("Failed to connect")
        return

    print("Initializing Position Manager...")
    pm = PositionManager(connector)
    
    symbol = "ARKB"
    direction = "LONG"
    
    print(f"\n--- Debugging SL for {symbol} ({direction}) ---")
    
    # Get price
    price_info = connector.get_current_price(symbol)
    if not price_info:
        print("Failed to get price")
        return
        
    entry_price = price_info['ask'] # Buying at Ask
    print(f"Entry Price (Ask): {entry_price}")
    
    # Debug Position Size vars
    vol, details = pm.calculate_position_size(symbol)
    print(f"Volume Details: {details}")
    
    # Debug Max Loss vars
    max_margin = pm.max_margin
    sl_percent = pm.sl_fixed_percent
    max_loss = max_margin * (sl_percent / 100)
    print(f"Max Margin: {max_margin}")
    print(f"SL Percent: {sl_percent}")
    print(f"Max Loss: {max_loss}")
    
    # Debug SL Calculation
    sl_price = pm.calculate_stop_loss(symbol, entry_price, direction)
    print(f"Calculated SL Price: {sl_price}")
    
    if sl_price:
        dist = entry_price - sl_price
        print(f"Implied Distance: {dist}")
        
    # Check if SL > Entry (Invalid for Buy)
    if sl_price > entry_price:
        print("❌ ERROR: SL is ABOVE Entry for LONG position!")
    else:
        print("✅ SL is below Entry (Valid)")

    connector.disconnect()

if __name__ == "__main__":
    main()
