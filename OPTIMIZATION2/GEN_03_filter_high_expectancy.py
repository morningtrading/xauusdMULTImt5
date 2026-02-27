#!/usr/bin/env python3
"""
GEN_03_filter_high_expectancy.py

Filter optimization results to find only high-expectancy configurations.

Criteria:
- Expectancy (PnL per trade) > $5.00
- Profit Factor > 1.5
- Min 15 trades
- Sort by expectancy (descending)
"""

import pandas as pd
import sys

# Input/Output files
INPUT_FILE = "GEN_02_optimization_results.csv"
OUTPUT_FILE = "GEN_03_high_expectancy.csv"

# Filter thresholds
MIN_EXPECTANCY = 5.0      # $ per trade
MIN_PROFIT_FACTOR = 1.5
MIN_TRADES = 15

def main():
    print("=" * 70)
    print("HIGH EXPECTANCY FILTER")
    print("=" * 70)
    print(f"\nCriteria:")
    print(f"  - Min Expectancy: ${MIN_EXPECTANCY}/trade")
    print(f"  - Min Profit Factor: {MIN_PROFIT_FACTOR}")
    print(f"  - Min Trades: {MIN_TRADES}")
    print()
    
    # Load results
    try:
        df = pd.read_csv(INPUT_FILE)
    except FileNotFoundError:
        print(f"ERROR ERROR: {INPUT_FILE} not found")
        print("   Run optimization first: python3 optimize.py GEN_02_config_optimization.json")
        sys.exit(1)
    
    print(f"Loaded {len(df)} optimization results\n")
    
    # Calculate expectancy if not present
    if 'Expectancy' not in df.columns:
        pnl_col = 'Test_PnL' if 'Test_PnL' in df.columns else 'TotalPnL'
        if pnl_col in df.columns and 'Trades' in df.columns:
            df['Expectancy'] = df[pnl_col] / df['Trades']
        else:
            print(f"ERROR ERROR: Cannot calculate expectancy - missing {pnl_col} or Trades columns")
            print(f"Available columns: {df.columns.tolist()}")
            sys.exit(1)
    
    # Apply filters
    pf_col = 'Profit_Factor' if 'Profit_Factor' in df.columns else 'ProfitFactor'
    df_filtered = df[
        (df['Expectancy'] >= MIN_EXPECTANCY) &
        (df[pf_col] >= MIN_PROFIT_FACTOR) &
        (df['Trades'] >= MIN_TRADES)
    ].copy()
    
    if len(df_filtered) == 0:
        print("WARNING  WARNING: No configurations meet the criteria!")
        print("\nTrying relaxed criteria:")
        print(f"  - Min Expectancy: ${MIN_EXPECTANCY * 0.5}/trade")
        print(f"  - Min Profit Factor: {MIN_PROFIT_FACTOR * 0.8}")
        
        pf_col = 'Profit_Factor' if 'Profit_Factor' in df.columns else 'ProfitFactor'
        df_filtered = df[
            (df['Expectancy'] >= MIN_EXPECTANCY * 0.5) &
            (df[pf_col] >= MIN_PROFIT_FACTOR * 0.8) &
            (df['Trades'] >= MIN_TRADES)
        ].copy()
        
        if len(df_filtered) == 0:
            print("\nERROR Still no results. Check optimization_results.csv manually.")
            sys.exit(1)
    
    # Sort by expectancy (descending)
    df_filtered = df_filtered.sort_values('Expectancy', ascending=False)
    
    # Save results
    df_filtered.to_csv(OUTPUT_FILE, index=False)
    
    print(f"OK Found {len(df_filtered)} high-expectancy configs\n")
    
    # Summary by asset type - skip if Type column doesn't exist
    print("=" * 70)
    print("SUMMARY BY SYMBOL")
    print("=" * 70)
    pnl_col = 'Test_PnL' if 'Test_PnL' in df_filtered.columns else 'TotalPnL'
    pf_col = 'Profit_Factor' if 'Profit_Factor' in df_filtered.columns else 'ProfitFactor'
    summary = df_filtered.groupby('Symbol').agg({
        'Timeframe': 'count',
        'Expectancy': 'mean',
        pf_col: 'mean',
        pnl_col: 'sum'
    }).round(2)
    summary.columns = ['Configs', 'Avg Expectancy', 'Avg PF', 'Total PnL']
    print(summary.to_string())
    print()
    
    # Top 20 by expectancy
    print("=" * 70)
    print("TOP 20 CONFIGURATIONS (by expectancy)")
    print("=" * 70)
    pnl_col = 'Test_PnL' if 'Test_PnL' in df_filtered.columns else 'TotalPnL'
    pf_col = 'Profit_Factor' if 'Profit_Factor' in df_filtered.columns else 'ProfitFactor'
    wr_col = 'Win_Rate' if 'Win_Rate' in df_filtered.columns else 'WinRate'
    display_cols = ['Symbol', 'Timeframe', 'Fast_EMA', 'Slow_EMA', 'Expectancy', 
                    pf_col, 'Trades', pnl_col, wr_col]
    
    # Filter to available columns
    display_cols = [col for col in display_cols if col in df_filtered.columns]
    
    top20 = df_filtered[display_cols].head(20)
    
    # Format for display
    pnl_col = 'Test_PnL' if 'Test_PnL' in top20.columns else 'TotalPnL'
    pf_col = 'Profit_Factor' if 'Profit_Factor' in top20.columns else 'ProfitFactor'
    wr_col = 'Win_Rate' if 'Win_Rate' in top20.columns else 'WinRate'
    
    if 'Expectancy' in top20.columns:
        top20['Expectancy'] = top20['Expectancy'].apply(lambda x: f"${x:.2f}")
    if pf_col in top20.columns:
        top20[pf_col] = top20[pf_col].apply(lambda x: f"{x:.2f}")
    if pnl_col in top20.columns:
        top20[pnl_col] = top20[pnl_col].apply(lambda x: f"${x:,.0f}")
    if wr_col in top20.columns:
        top20[wr_col] = top20[wr_col].apply(lambda x: f"{x:.1f}%")
    
    print(top20.to_string(index=False))
    print()
    
    # Distribution analysis
    print("=" * 70)
    print("EXPECTANCY DISTRIBUTION")
    print("=" * 70)
    print(f"$5-10:     {len(df_filtered[(df_filtered['Expectancy'] >= 5) & (df_filtered['Expectancy'] < 10)])} configs")
    print(f"$10-20:    {len(df_filtered[(df_filtered['Expectancy'] >= 10) & (df_filtered['Expectancy'] < 20)])} configs")
    print(f"$20-50:    {len(df_filtered[(df_filtered['Expectancy'] >= 20) & (df_filtered['Expectancy'] < 50)])} configs")
    print(f"$50+:      {len(df_filtered[df_filtered['Expectancy'] >= 50])} configs")
    print()
    
    print(f"File: Saved: {OUTPUT_FILE}")
    print("\nOK Ready for portfolio construction!\n")

if __name__ == '__main__':
    main()
