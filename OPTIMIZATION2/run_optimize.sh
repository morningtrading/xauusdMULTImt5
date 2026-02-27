#!/bin/bash
# Run optimize.py with Wine Python (for MT5 support on Linux)
# Usage: ./run_optimize.sh

echo "Running optimization with Wine Python..."
./wine_python.sh optimize.py "$@"
