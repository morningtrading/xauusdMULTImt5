
import json
import pandas as pd
from pathlib import Path

def main():
    # Priority 1: Check for rolling CSV
    rolling_csv = Path("optimization_rolling.csv")
    csv_path = Path("optimization_results.csv")
    
    if rolling_csv.exists() and rolling_csv.stat().st_mtime > csv_path.stat().st_mtime:
         csv_path = rolling_csv
         
    if csv_path.exists():
        print(f"Loading results from {csv_path}...")
        df = pd.read_csv(csv_path)
        
        # Renaissance mapping for consistency
        # CSV cols: Symbol,Timeframe,Fast_EMA,Slow_EMA,Train_PnL,Test_PnL,Trades,Win_Rate,Max_DD
        # Target cols for display: Symbol, Test PnL, Trades, Win%, MaxDD, Streak(W/L) (Streak missing in CSV currently)
        
        df = df.rename(columns={
            'Test_PnL': 'Test PnL',
            'Win_Rate': 'Win%',
            'Max_DD': 'MaxDD'
        })
        
        # Add missing columns if needed
        if 'Streak(W/L)' not in df.columns:
            df['Streak(W/L)'] = "N/A"
            
    else:
        # Priority 2: Config
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
                details = s_data.get('_opt_details', {})
                
                row = {
                    'Symbol': symbol,
                    'Test PnL': test_pnl,
                    'Trades': details.get('trades', 0),
                    'Win%': details.get('win_rate', 0.0),
                    'MaxDD': details.get('max_dd', 0.0),
                    'Streak(W/L)': f"{details.get('max_win_streak',0)}/{details.get('max_loss_streak',0)}"
                }
                data.append(row)
                
        if not data:
            print("No optimization data found in config.")
            return
            
        df = pd.DataFrame(data)
    
    # Stats
    total_symbols = len(df)
    profitable = df[df['Test PnL'] > 0]
    win_rate = (len(profitable) / total_symbols) * 100 if total_symbols > 0 else 0
    
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
    cols = ['Symbol', 'Timeframe', 'Test PnL', 'Trades', 'Win%', 'MaxDD']
    if 'Streak(W/L)' in df.columns:
        cols.append('Streak(W/L)')
        
    # Clean up formatting
    # df['Test PnL'] = df['Test PnL'].map('{:,.2f}'.format)
    
    print("\nTOP 10 WINNERS:")
    print("-" * 80)
    print(df.sort_values(by='Test PnL', ascending=False).head(10).to_string(index=False, columns=cols))
    
    print("\n\nTOP 10 LOSERS:")
    print("-" * 80)
    print(df.sort_values(by='Test PnL', ascending=True).head(10).to_string(index=False, columns=cols))
    
    # --- Consolidated Analysis ---
    print("\n" + "="*80)
    print("CONSOLIDATED ANALYSIS (Best Timeframe per Symbol)")
    print("="*80)
    
    # 1. Best per Symbol
    # Sort by Symbol (asc) then PnL (desc) so we can drop duplicates keeping first
    best_df = df.sort_values(by=['Symbol', 'Test PnL'], ascending=[True, False]).drop_duplicates(subset=['Symbol'])
    best_df = best_df.sort_values(by='Test PnL', ascending=False)
    
    print(f"\nTop 15 Best Performing Symbols (Best Config Selected):")
    print("-" * 80)
    # Add Fast/Slow columns if available in CSV but not in cols
    disp_cols = ['Symbol', 'Timeframe', 'Test PnL', 'Trades', 'Win%', 'MaxDD']
    if 'Fast_EMA' in df.columns: disp_cols.extend(['Fast_EMA', 'Slow_EMA'])
    if 'Long_PnL' in df.columns: disp_cols.extend(['Long_PnL', 'Short_PnL'])
    
    print(best_df.head(15).to_string(index=False, columns=disp_cols))
    
    # 2. Recommendations
    # Criteria: Test PnL > 0, Trades > 10 (statistical significance?), Win% > 30%?
    # Let's be lenient for now: PnL > 500
    
    rec_df = best_df[ (best_df['Test PnL'] > 500) & (best_df['Trades'] >= 10) ]
    
    print("\n" + "="*80)
    print(f"RECOMMENDED PORTFOLIO (PnL > 500, Trades >= 10)")
    print("="*80)
    
    if not rec_df.empty:
        print(rec_df.to_string(index=False, columns=disp_cols))
        
        print(f"\nTotal Portfolio PnL: {rec_df['Test PnL'].sum():.2f}")
        print(f"Count: {len(rec_df)}")
    else:
        print("No symbols met recommendation criteria.")
        
    # Save Recommendations to CSV
    rec_file = "recommended_portfolio.csv"
    rec_df.to_csv(rec_file, index=False)
    print(f"\nSaved recommendations to: {rec_file}")
    
    # --- Pareto Analysis ---
    print("\n" + "="*80)
    print("PARETO ANALYSIS (Contribution to Total Profit)")
    print("="*80)
    
    # Filter for profitable symbols only
    profit_df = df[df['Test PnL'] > 0].copy()
    
    if not profit_df.empty:
        # Sort by PnL Descending
        profit_df = profit_df.sort_values(by='Test PnL', ascending=False)
        
        # Calculate Cumulative PnL
        total_profit = profit_df['Test PnL'].sum()
        profit_df['Cum PnL'] = profit_df['Test PnL'].cumsum()
        profit_df['% Total'] = (profit_df['Test PnL'] / total_profit) * 100
        profit_df['Cum %'] = (profit_df['Cum PnL'] / total_profit) * 100
        
    # Format columns for display
        pareto_cols = ['Symbol', 'Timeframe', 'Test PnL', 'Cum PnL', '% Total', 'Cum %']
        
        # Add Long/Short to Pareto if available
        if 'Long_PnL' in df.columns:
            pareto_cols.extend(['Long_PnL', 'Short_PnL'])
        
        print(f"Total Gross Profit (Positive PnL only): {total_profit:.2f}")
        print(f"Count of Profitable Configs: {len(profit_df)}")
        print("-" * 80)
        print(profit_df.to_string(index=False, columns=pareto_cols, float_format=lambda x: "{:.2f}".format(x)))
    else:
        print("No profitable symbols found for Pareto analysis.")

if __name__ == "__main__":
    main()
