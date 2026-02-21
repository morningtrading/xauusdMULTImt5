
import json
from pathlib import Path

def main():
    # Symbols to add
    new_symbols = [
        "NAS100ft", "BTCUSD", "HK50ft", "ES35", "HK50",
        "AAPL", "AMAZON", "MSFT", "NVIDIA", "TSLA", 
        "GOOG", "MU", "EXXON", "AMD", "PLTR"
    ]
    
    config_path = Path('config/trading_config.json')
    if not config_path.exists():
        print("Config not found!")
        return
        
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    enabled = config.get('symbols', {}).get('enabled', [])
    settings = config.get('symbols', {}).get('settings', {})
    
    print(f"Current Enabled count: {len(enabled)}")
    
    added_count = 0
    for sym in new_symbols:
        if sym not in enabled:
            enabled.append(sym)
            added_count += 1
            print(f"  + Adding {sym}")
        else:
            print(f"  = {sym} already exists")
            
        # Ensure setting is enabled
        if sym in settings:
            settings[sym]['enabled'] = True
        else:
            # Create default if missing (though optimization should have created it)
            settings[sym] = {
                'enabled': True,
                'timeframe': 'M5',
                'fast_ema': 9,
                'slow_ema': 21,
                'min_volume': 0.01,
                'volume': 0.01,
                'max_spread_points': 9999,
                '_note': 'Manually Added'
            }
            
    config['symbols']['enabled'] = enabled
    config['symbols']['settings'] = settings
    
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
        
    print(f"\nUpdated Config. Added {added_count} new symbols.")
    print(f"Total Enabled: {len(enabled)}")

if __name__ == "__main__":
    main()
