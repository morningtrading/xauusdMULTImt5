#!/usr/bin/env python3
"""
Transaction Cost Sensitivity Analyzer
Tests portfolio performance under different cost scenarios
"""

import pandas as pd
import numpy as np
import os
import sys
import json

def analyze_cost_sensitivity(portfolio_file="diversified_portfolio.csv"):
    """
    Analyze how portfolio performs under different transaction cost scenarios
    """
    print("="*60)
    print("TRANSACTION COST SENSITIVITY ANALYSIS")
    print("="*60)
    
    if not os.path.exists(portfolio_file):
        print(f"Error: {portfolio_file} not found!")
        print("Run portfolio_optimizer.py first.")
        return
    
    df = pd.read_csv(portfolio_file)
    
    print(f"Loaded {len(df)} portfolio positions")
    print()
    
    # Cost scenarios
    scenarios = {
        'Current (1.0x)': 1.0,
        'Conservative (1.5x)': 1.5,
        'Pessimistic (2.0x)': 2.0,
        'With Slippage (+2 pips)': 1.0  # Will add slippage separately
    }
    
    print("Analyzing cost scenarios...")
    print("-"*60)
    
    results = []
    
    for scenario_name, multiplier in scenarios.items():
        # Estimate impact on PnL
        # Simplified: reduce PnL proportionally to cost increase
        # Real implementation would re-run backtest with new costs
        
        # Average cost per trade estimate (simplified)
        avg_cost_per_trade = 0.0001  # Placeholder
        
        if scenario_name == 'With Slippage (+2 pips)':
            # Add extra cost
            extra_cost = 0.0002 * df['Trades']
            adjusted_pnl = df['Test_PnL'] - extra_cost
        else:
            # Scale existing costs
            cost_increase_factor = multiplier - 1.0
            estimated_cost = df['Trades'] * avg_cost_per_trade * cost_increase_factor
            adjusted_pnl = df['Test_PnL'] - estimated_cost
        
        total_pnl = adjusted_pnl.sum()
        positive_count = (adjusted_pnl > 0).sum()
        avg_pnl = adjusted_pnl.mean()
        
        results.append({
            'Scenario': scenario_name,
            'Total_PnL': total_pnl,
            'Avg_PnL': avg_pnl,
            'Positive_Positions': positive_count,
            'Success_Rate': (positive_count / len(df)) * 100
        })
        
        print(f"{scenario_name:25} | "
              f"Total PnL: {total_pnl:>10.2f} | "
              f"Avg: {avg_pnl:>8.2f} | "
              f"Positive: {positive_count}/{len(df)}")
    
    print()
    print("="*60)
    print("RECOMMENDATIONS")
    print("="*60)
    
    # Calculate robustness score
    base_pnl = results[0]['Total_PnL']
    worst_case_pnl = min([r['Total_PnL'] for r in results])
    robustness = (worst_case_pnl / base_pnl) * 100 if base_pnl > 0 else 0
    
    print(f"Portfolio Robustness: {robustness:.1f}%")
    print(f"  (Worst case retains {robustness:.1f}% of base case PnL)")
    print()
    
    if robustness >= 80:
        print("✓ Portfolio is ROBUST to transaction cost increases")
    elif robustness >= 60:
        print("⚠ Portfolio is MODERATELY SENSITIVE to costs")
        print("  Consider focusing on longer timeframes")
    else:
        print("✗ Portfolio is HIGHLY SENSITIVE to costs")
        print("  Recommend:")
        print("  - Focus on 1h and 4h timeframes only")
        print("  - Reduce number of trades")
        print("  - Increase profit targets")
    
    print()
    
    # Cost breakdown by timeframe
    print("Cost Sensitivity by Timeframe:")
    for tf in df['Timeframe'].unique():
        tf_df = df[df['Timeframe'] == tf]
        print(f"  {tf:<6}: {len(tf_df)} positions, "
              f"Avg {tf_df['Trades'].mean():.0f} trades, "
              f"Total PnL: {tf_df['Test_PnL'].sum():.2f}")
    
    print()
    
    # Save results
    results_df = pd.DataFrame(results)
    output_file = "cost_sensitivity_results.csv"
    results_df.to_csv(output_file, index=False)
    print(f"Saved analysis to: {output_file}")
    
    # Generate recommendations file
    recommendations = {
        "robustness_score": robustness,
        "base_pnl": base_pnl,
        "worst_case_pnl": worst_case_pnl,
        "scenarios": results,
        "recommendations": []
    }
    
    if robustness < 70:
        recommendations["recommendations"].append("Focus on 1h and 4h timeframes")
        recommendations["recommendations"].append("Avoid 1m and 5m due to high frequency")
    
    if df['Trades'].mean() > 100:
        recommendations["recommendations"].append("Reduce number of trades per position")
    
    with open("cost_recommendations.json", 'w') as f:
        json.dump(recommendations, f, indent=2)
    
    print(f"Saved recommendations to: cost_recommendations.json")
    print()
    print("Done.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Analyze transaction cost sensitivity')
    parser.add_argument('--portfolio', type=str, default='diversified_portfolio.csv',
                        help='Portfolio file to analyze')
    
    args = parser.parse_args()
    analyze_cost_sensitivity(args.portfolio)
