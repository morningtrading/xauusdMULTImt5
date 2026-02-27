#!/bin/bash
# Run stats.py with Wine Python
# Usage: ./run_stats.sh

echo "Running stats with Wine Python..."
./wine_python.sh stats.py "$@"
