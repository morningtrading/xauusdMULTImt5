
import json
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: python disable_symbol.py <SYMBOL>")
        return
        
    symbol_to_disable = sys.argv[1]
    config_path = Path('config/trading_config.json')
    
    if not config_path.exists():
        print("Config not found!")
        return
        
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    enabled = config.get('symbols', {}).get('enabled', [])
    settings = config.get('symbols', {}).get('settings', {})
    
    if symbol_to_disable in enabled:
        print(f"Disabling {symbol_to_disable}...")
        enabled.remove(symbol_to_disable)
        config['symbols']['enabled'] = enabled
        
        if symbol_to_disable in settings:
            settings[symbol_to_disable]['enabled'] = False
            config['symbols']['settings'] = settings
            
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        print("Config updated.")
    else:
        print(f"{symbol_to_disable} is not in enabled list.")

if __name__ == "__main__":
    main()
