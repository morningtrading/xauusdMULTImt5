
import json
import pandas as pd
from pathlib import Path

def main():
    config_path = Path('config/trading_config.json')
    if not config_path.exists():
        print("Config not found!")
        return
        
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    settings = config.get('symbols', {}).get('settings', {})
    enabled = config.get('symbols', {}).get('enabled', [])
    
    data = []
    
    for symbol in enabled:
        if symbol in settings:
            s_data = settings[symbol]
            test_pnl = s_data.get('_opt_pnl_test', 0.0)
            data.append({'Symbol': symbol, 'PnL': test_pnl})
            
    if not data:
        print("No data found.")
        return
        
    df = pd.DataFrame(data)
    df = df.sort_values(by='PnL', ascending=True)
    
    losers = df.head(20)['Symbol'].tolist()
    
    print("Removing Top 20 Losers:")
    for sym in losers:
        pnl = df[df['Symbol'] == sym]['PnL'].values[0]
        print(f"  - {sym} (PnL: {pnl})")
        
    # Update Config
    new_enabled = [s for s in enabled if s not in losers]
    
    for sym in losers:
        if sym in settings:
            settings[sym]['enabled'] = False
            
    config['symbols']['enabled'] = new_enabled
    config['symbols']['settings'] = settings
    
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
        
    print(f"\nUpdated config. Enabled count: {len(enabled)} -> {len(new_enabled)}")

if __name__ == "__main__":
    main()
