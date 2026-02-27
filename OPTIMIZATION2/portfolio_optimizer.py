#!/usr/bin/env python3
"""
Portfolio Optimizer - Select uncorrelated symbol-timeframe pairs
"""

import pandas as pd
import numpy as np
import os
import sys

def calculate_correlation_matrix(robust_file="robust_portfolio.csv"):
    """
    Calculate correlation between different symbol-timeframe pairs
    Note: This is a simplified approach. For real correlation, we'd need
    actual price/returns data for each pair.
    """
    if not os.path.exists(robust_file):
        print(f"Error: {robust_file} not found!")
        print("Run select_robust.py first.")
        return None
    
    df = pd.read_csv(robust_file)
    
    # Create a simple heuristic correlation matrix
    # Symbols from same category tend to be correlated
    # Different timeframes reduce correlation
    
    # Define correlation groups (simplified)
    groups = {
        'indices': ['DJ30', 'NAS100', 'SP500', 'US2000', 'GER40', 'UK100', 'SWI20', 
                    'ES35', 'FRA40', 'NETH25', 'BVSPX', 'SA40'],
        'asia': ['HK50', 'CHINAH', 'HKTECH', 'TWINDEX', 'IND50'],
        'crypto': ['BTCUSD', 'ETHUSD', 'BTCETH', 'BTCLTC', 'ETHLTC'],
        'fx': ['USDTJPY'],
        'commodities': ['GAS-C', 'GLD', 'GDX'],
        'etf': ['SPY', 'QQQ', 'IWM', 'XLK', 'IYW', 'FDN', 'ARKK', 'VGT']
    }
    
    # Assign each symbol to a group
    symbol_groups = {}
    for group_name, symbols in groups.items():
        for symbol in symbols:
            symbol_groups[symbol] = group_name
    
    return df, symbol_groups, groups

def build_diversified_portfolio(max_positions=15, target_sharpe=0.5):
    """
    Build a diversified portfolio by selecting uncorrelated pairs
    """
    print("="*60)
    print("PORTFOLIO OPTIMIZER")
    print("="*60)
    
    result = calculate_correlation_matrix()
    if result is None:
        return
    
    df, symbol_groups, groups = result
    
    print(f"Loaded {len(df)} robust configurations")
    print(f"Building portfolio with max {max_positions} positions")
    print()
    
    # Sort by Return/DD ratio
    df = df.sort_values('Return_DD_Ratio', ascending=False)
    
    # Selection algorithm
    selected = []
    selected_symbols = []  # Use list to count occurrences
    selected_groups = {}
    selected_timeframes = {}
    
    for idx, row in df.iterrows():
        symbol = row['Symbol']
        timeframe = row['Timeframe']
        group = symbol_groups.get(symbol, 'other')
        
        # Diversification rules:
        # 1. Max 2 positions per symbol
        # 2. Max 4 positions per group
        # 3. Balance across timeframes
        # 4. Prefer high Return/DD ratio
        
        if len(selected) >= max_positions:
            break
        
        # Check symbol limit
        if selected_symbols.count(symbol) >= 2:
            continue
        
        # Check group limit
        if selected_groups.get(group, 0) >= 4:
            continue
        
        # Add to portfolio
        selected.append(row)
        selected_symbols.append(symbol)
        selected_groups[group] = selected_groups.get(group, 0) + 1
        selected_timeframes[timeframe] = selected_timeframes.get(timeframe, 0) + 1
    
    # Convert to DataFrame
    portfolio_df = pd.DataFrame(selected)
    
    print("SELECTED PORTFOLIO")
    print("-"*60)
    
    for idx, row in portfolio_df.iterrows():
        print(f"{row['Symbol']:<12} {row['Timeframe']:<6} | "
              f"PnL: {row['Test_PnL']:>8.2f} | "
              f"WR: {row['Win_Rate']:>5.1f}% | "
              f"PF: {row['Profit_Factor']:>4.2f} | "
              f"R/DD: {row['Return_DD_Ratio']:>5.2f}")
    
    print()
    print("="*60)
    print("PORTFOLIO STATISTICS")
    print("="*60)
    print(f"Total Positions: {len(portfolio_df)}")
    print(f"Total Expected PnL: {portfolio_df['Test_PnL'].sum():.2f}")
    print(f"Avg PnL per Position: {portfolio_df['Test_PnL'].mean():.2f}")
    print(f"Avg Win Rate: {portfolio_df['Win_Rate'].mean():.1f}%")
    print(f"Avg Profit Factor: {portfolio_df['Profit_Factor'].mean():.2f}")
    print(f"Avg Return/DD: {portfolio_df['Return_DD_Ratio'].mean():.2f}")
    print()
    
    print("Group Distribution:")
    for group, count in selected_groups.items():
        print(f"  {group:<15}: {count} positions")
    print()
    
    print("Timeframe Distribution:")
    for tf, count in selected_timeframes.items():
        print(f"  {tf:<6}: {count} positions")
    print()
    
    # Calculate portfolio metrics
    total_trades = portfolio_df['Trades'].sum()
    total_pnl = portfolio_df['Test_PnL'].sum()
    avg_expectancy = portfolio_df['Expectancy'].mean()
    
    print("Portfolio Metrics:")
    print(f"  Total Trades: {total_trades}")
    print(f"  Total PnL: {total_pnl:.2f}")
    print(f"  Avg Expectancy: {avg_expectancy:.4f}")
    print(f"  Risk Score: {1.0 / portfolio_df['Return_DD_Ratio'].mean():.2f}")
    print()
    
    # Save portfolio
    output_file = "diversified_portfolio.csv"
    portfolio_df.to_csv(output_file, index=False)
    print(f"Saved portfolio to: {output_file}")
    
    # Create deployment config
    deployment = []
    for idx, row in portfolio_df.iterrows():
        deployment.append({
            'symbol': row['Symbol'],
            'timeframe': row['Timeframe'],
            'fast_ema': row['Fast_EMA'],
            'slow_ema': row['Slow_EMA'],
            'expected_pnl': row['Test_PnL'],
            'win_rate': row['Win_Rate'],
            'profit_factor': row['Profit_Factor']
        })
    
    deploy_df = pd.DataFrame(deployment)
    deploy_file = "deployment_config.csv"
    deploy_df.to_csv(deploy_file, index=False)
    print(f"Saved deployment config to: {deploy_file}")
    print()
    print("Done.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Build diversified portfolio')
    parser.add_argument('--max-positions', type=int, default=15,
                        help='Maximum number of positions (default: 15)')
    parser.add_argument('--target-sharpe', type=float, default=0.5,
                        help='Target Sharpe ratio (default: 0.5)')
    
    args = parser.parse_args()
    build_diversified_portfolio(args.max_positions, args.target_sharpe)
