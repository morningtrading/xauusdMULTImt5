#!/bin/bash
# Run Donchian Channel Optimizer
# No MT5 needed - reads from dataticks/

echo "======================================================================"
echo "DONCHIAN CHANNEL OPTIMIZER"
echo "======================================================================"

python3 "$(dirname "$0")/GEN_01_donchian_optimize.py"

echo ""
echo "Output: GEN_01_donchian_results.csv"
