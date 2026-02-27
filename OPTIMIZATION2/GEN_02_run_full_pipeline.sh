#!/bin/bash
# GEN_02_run_full_pipeline.sh
# Full optimization pipeline: Filter symbols -> Optimize -> Filter results

set -e

echo "======================================================================"
echo "FULL OPTIMIZATION PIPELINE"
echo "======================================================================"
echo ""

# Step 1: Filter symbols from MT5
echo "STEP 1: Filtering symbols from MT5..."
echo "----------------------------------------------------------------------"
wine python GEN_01_filter_symbols_from_mt5.py
if [ ! -f "GEN_01_liquid_symbols.csv" ]; then
    echo "ERROR: Symbol filtering failed"
    exit 1
fi
echo ""

# Count symbols
SYMBOL_COUNT=$(tail -n +2 GEN_01_liquid_symbols.csv | wc -l)
echo "✅ Found $SYMBOL_COUNT liquid symbols"
echo ""

# Step 2: Download data (optional - skip if data already exists)
read -p "Download fresh data from MT5? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "STEP 2: Downloading data from MT5..."
    echo "----------------------------------------------------------------------"
    
    # Create temporary download config
    cat > temp_download_config.py << 'EOF'
INPUT_CSV_FILENAME = "GEN_01_liquid_symbols.csv"
OUTPUT_DIR = "dataticks"
TIMEFRAMES = {
    '15m': 15,
    '1h': 60
}
BAR_COUNTS = {
    '15m': 20000,
    '1h': 5000
}
EOF
    
    python3 download_data.py
    rm -f temp_download_config.py
    echo ""
fi

# Step 3: Run optimization
echo "STEP 3: Running optimization (this will take 10-20 minutes)..."
echo "----------------------------------------------------------------------"
python3 optimize.py GEN_02_config_optimization.json

if [ ! -f "GEN_02_optimization_results.csv" ]; then
    echo "ERROR: Optimization failed"
    exit 1
fi
echo ""

# Step 4: Filter for high expectancy
echo "STEP 4: Filtering for high expectancy configs..."
echo "----------------------------------------------------------------------"
python3 GEN_03_filter_high_expectancy.py

echo ""
echo "======================================================================"
echo "✅ PIPELINE COMPLETE"
echo "======================================================================"
echo ""
echo "Output files:"
echo "  1. GEN_01_liquid_symbols.csv      - Filtered symbols"
echo "  2. GEN_02_optimization_results.csv - All optimization results"
echo "  3. GEN_03_high_expectancy.csv      - High expectancy configs"
echo ""
echo "Next steps:"
echo "  - Review GEN_03_high_expectancy.csv"
echo "  - Run portfolio optimizer: python3 portfolio_optimizer.py"
echo "  - Run cost sensitivity: python3 run_cost_sensitivity.py"
echo ""
