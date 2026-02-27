#!/bin/bash
# Run focused optimization on top performers

echo "Starting Focused Optimization on Top Performers..."
echo "Using config: config_optimization_focused.json"
echo "Symbols: 23 top performers"
echo "Timeframes: 15m, 1h (no 4h)"
echo "Filters: Volume + ATR Stops enabled"
echo "Position Sizing: Fixed $20 risk per trade"
echo ""

# Use wine python wrapper
./wine_python.sh optimize.py config_optimization_focused.json

echo ""
echo "Focused optimization complete. Results in optimization_results_enhanced.csv"
