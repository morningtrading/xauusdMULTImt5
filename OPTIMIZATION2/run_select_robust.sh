#!/bin/bash
# Run select_robust.py with Wine Python
# Usage: ./run_select_robust.sh

echo "Running robust selection with Wine Python..."
./wine_python.sh select_robust.py "$@"
