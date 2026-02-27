#!/usr/bin/env python3
"""
Enhanced Select Robust - Strict filtering of optimization results
"""

import pandas as pd
import numpy as np
import os
import sys

def main():
    # Load results
    input_file = "optimization_results_enhanced.csv"
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found!")
        print("Run optimize.py first to generate results.")
        return
    
    df = pd.read_csv(input_file)
    print(f"Loaded {len(df)} optimization results")
    print("="*60)
    
    # Display initial statistics
    print(f"Initial Stats:")
    print(f"  Total entries: {len(df)}")
    print(f"  Positive PnL: {len(df[df['Test_PnL'] > 0])}")
    print(f"  Avg PnL: {df['Test_PnL'].mean():.2f}")
    print(f"  Avg Win Rate: {df['Win_Rate'].mean():.1f}%")
    print(f"  Avg Profit Factor: {df['Profit_Factor'].mean():.2f}")
    print()
    
    # Apply strict filters
    print("Applying Enhanced Filters:")
    print("-"*60)
    
    # Filter 1: Positive Test PnL
    df_filtered = df[df['Test_PnL'] > 0].copy()
    print(f"1. Test PnL > 0: {len(df_filtered)} / {len(df)} remaining")
    
    # Filter 2: Skip Win Rate (placeholder in rolling validation)
    # df_filtered = df_filtered[df_filtered['Win_Rate'] >= 30.0]
    print(f"2. Win Rate filter: SKIPPED (rolling validation doesn't track this)")
    
    # Filter 3: Minimum trades >= 15 (relaxed)
    df_filtered = df_filtered[df_filtered['Trades'] >= 15]
    print(f"3. Trades >= 15: {len(df_filtered)} remaining")
    
    # Filter 4: Profit Factor >= 1.1 (relaxed)
    df_filtered = df_filtered[df_filtered['Profit_Factor'] >= 1.1]
    print(f"4. Profit Factor >= 1.1: {len(df_filtered)} remaining")
    
    # Filter 5: Max DD < 3x PnL (relaxed)
    df_filtered['DD_to_PnL_Ratio'] = df_filtered['Max_DD'] / df_filtered['Test_PnL']
    df_filtered = df_filtered[df_filtered['DD_to_PnL_Ratio'] < 3.0]
    print(f"5. Max DD < 3x PnL: {len(df_filtered)} remaining")
    
    # Calculate additional metrics
    df_filtered['Return_DD_Ratio'] = df_filtered['Test_PnL'] / df_filtered['Max_DD']
    df_filtered['Expectancy'] = df_filtered['Test_PnL'] / df_filtered['Trades']
    
    # Sort by Return/DD ratio (best first)
    df_filtered = df_filtered.sort_values('Return_DD_Ratio', ascending=False)
    
    print()
    print("="*60)
    print(f"ROBUST SELECTION RESULTS")
    print("="*60)
    print(f"Selected: {len(df_filtered)} / {len(df)} ({len(df_filtered)/len(df)*100:.1f}%)")
    
    if len(df_filtered) > 0:
        print(f"\nTop Performers (by Return/DD Ratio):")
        print("-"*60)
        
        display_cols = ['Symbol', 'Timeframe', 'Test_PnL', 'Win_Rate', 'Profit_Factor', 
                        'Return_DD_Ratio', 'Trades', 'Expectancy']
        
        top_10 = df_filtered[display_cols].head(10)
        
        for idx, row in top_10.iterrows():
            print(f"{row['Symbol']:<12} {row['Timeframe']:<6} | "
                  f"PnL: {row['Test_PnL']:>8.2f} | "
                  f"WR: {row['Win_Rate']:>5.1f}% | "
                  f"PF: {row['Profit_Factor']:>4.2f} | "
                  f"R/DD: {row['Return_DD_Ratio']:>5.2f} | "
                  f"Trades: {row['Trades']:>3.0f}")
        
        print()
        print("Aggregate Statistics:")
        print(f"  Total PnL: {df_filtered['Test_PnL'].sum():.2f}")
        print(f"  Avg PnL per Config: {df_filtered['Test_PnL'].mean():.2f}")
        print(f"  Avg Win Rate: {df_filtered['Win_Rate'].mean():.1f}%")
        print(f"  Avg Profit Factor: {df_filtered['Profit_Factor'].mean():.2f}")
        print(f"  Avg Return/DD: {df_filtered['Return_DD_Ratio'].mean():.2f}")
        print(f"  Avg Expectancy: {df_filtered['Expectancy'].mean():.4f}")
        print()
        
        # Symbol distribution
        print("Distribution by Symbol:")
        symbol_counts = df_filtered['Symbol'].value_counts()
        for symbol, count in symbol_counts.head(10).items():
            print(f"  {symbol:<12}: {count} configs")
        
        print()
        
        # Timeframe distribution
        print("Distribution by Timeframe:")
        tf_counts = df_filtered['Timeframe'].value_counts()
        for tf, count in tf_counts.items():
            print(f"  {tf:<6}: {count} configs")
        
        # Save filtered results
        output_file = "robust_portfolio.csv"
        df_filtered.to_csv(output_file, index=False)
        print()
        print(f"Saved robust selections to: {output_file}")
        
        # Create top 20 portfolio
        top_20 = df_filtered.head(20)
        top_20_file = "top_20_portfolio.csv"
        top_20.to_csv(top_20_file, index=False)
        print(f"Saved top 20 to: {top_20_file}")
        
    else:
        print("\nNo configurations passed all filters!")
        print("Consider relaxing the thresholds or improving optimization.")
    
    print()
    print("Done.")

if __name__ == "__main__":
    main()
