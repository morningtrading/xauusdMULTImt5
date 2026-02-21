
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
            train_pnl = s_data.get('_opt_pnl_train', 0.0)
            note = s_data.get('_note', '')
            
            # Try to guess type from symbol name or external list? 
            # For now just symbol
            
            details = s_data.get('_opt_details', {})
            
            row = {
                'Symbol': symbol,
                'Test PnL': test_pnl,
                'Train PnL': train_pnl,
                # 'Note': note
            }
            
            if details:
                row['Trades'] = details.get('trades', 0)
                row['Win%'] = details.get('win_rate', 0.0)
                row['MaxDD'] = details.get('max_dd', 0.0)
                row['Streak(W/L)'] = f"{details.get('max_win_streak',0)}/{details.get('max_loss_streak',0)}"
            else:
                row['Trades'] = 0
                row['Win%'] = 0.0
                row['MaxDD'] = 0.0
                row['Streak(W/L)'] = "0/0"
                
            data.append(row)
            
    if not data:
        print("No optimization data found in config.")
        return
        
    df = pd.DataFrame(data)
    
    # Stats
    total_symbols = len(df)
    profitable = df[df['Test PnL'] > 0]
    win_rate = (len(profitable) / total_symbols) * 100
    
    total_test_pnl = df['Test PnL'].sum()
    avg_test_pnl = df['Test PnL'].mean()
    
    print("="*80)
    print("OPTIMIZATION PnL STATISTICS (Walk-Forward Test Data)")
    print("="*80)
    print(f"Total Symbols: {total_symbols}")
    print(f"Profitable:    {len(profitable)} ({win_rate:.1f}%)")
    print(f"Total PnL:     {total_test_pnl:.2f}")
    print(f"Average PnL:   {avg_test_pnl:.2f}")
    print("-" * 80)
    
    # Columns to show
    cols = ['Symbol', 'Test PnL', 'Trades', 'Win%', 'MaxDD', 'Streak(W/L)']
    
    print("\nTOP 10 WINNERS:")
    print("-" * 80)
    print(df.sort_values(by='Test PnL', ascending=False).head(10).to_string(index=False, columns=cols))
    
    print("\n\nTOP 10 LOSERS:")
    print("-" * 80)
    print(df.sort_values(by='Test PnL', ascending=True).head(10).to_string(index=False, columns=cols))

if __name__ == "__main__":
    main()
