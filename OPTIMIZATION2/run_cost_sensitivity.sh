#!/bin/bash
# Run cost_sensitivity.py with Wine Python
# Usage: ./run_cost_sensitivity.sh

echo "Running cost sensitivity analysis with Wine Python..."
./wine_python.sh cost_sensitivity.py "$@"
