#!/bin/bash
# Run portfolio_optimizer.py with Wine Python
# Usage: ./run_portfolio.sh [--max-positions N]

echo "Running portfolio optimizer with Wine Python..."
./wine_python.sh portfolio_optimizer.py "$@"
