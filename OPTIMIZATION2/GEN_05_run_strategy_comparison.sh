#!/bin/bash
# GEN_05_run_strategy_comparison.sh
# Run multi-strategy comparison backtester
# No MT5 connection needed - reads data directly from dataticks/

echo "======================================================================"
echo "MULTI-STRATEGY COMPARISON"
echo "======================================================================"
echo ""
echo "Strategies: EMA Cross, RSI Reversion, MACD, Bollinger, Donchian, RSI+EMA"
echo "Data source: dataticks/"
echo ""

python3 GEN_05_multi_strategy_backtest.py

echo ""
echo "Output files:"
echo "  1. GEN_05_strategy_comparison.csv - Detailed per-symbol results"
echo "  2. GEN_05_strategy_summary.csv    - Strategy-level summary"
echo ""
