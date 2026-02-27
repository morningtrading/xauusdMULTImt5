#!/bin/bash
# Complete optimization pipeline with Wine Python
# Runs all steps: optimize → select → portfolio → cost analysis

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════╗"
echo "║     OPTIMIZATION2 - Complete Pipeline (Wine)           ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Run optimization
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1/4: Running optimization..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./wine_python.sh optimize.py
if [ $? -ne 0 ]; then
    echo "❌ Optimization failed!"
    exit 1
fi
echo "✅ Optimization complete"
echo ""

# Step 2: Select robust configurations
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2/4: Selecting robust configurations..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./wine_python.sh select_robust.py
if [ $? -ne 0 ]; then
    echo "❌ Selection failed!"
    exit 1
fi
echo "✅ Selection complete"
echo ""

# Step 3: Build portfolio
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 3/4: Building diversified portfolio..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./wine_python.sh portfolio_optimizer.py --max-positions 15
if [ $? -ne 0 ]; then
    echo "❌ Portfolio optimization failed!"
    exit 1
fi
echo "✅ Portfolio built"
echo ""

# Step 4: Cost sensitivity analysis
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 4/4: Analyzing transaction costs..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
./wine_python.sh cost_sensitivity.py
if [ $? -ne 0 ]; then
    echo "❌ Cost analysis failed!"
    exit 1
fi
echo "✅ Cost analysis complete"
echo ""

# Summary
echo "╔════════════════════════════════════════════════════════╗"
echo "║              PIPELINE COMPLETE! ✅                      ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "📊 Output Files:"
echo "   • optimization_results_enhanced.csv"
echo "   • robust_portfolio.csv"
echo "   • top_20_portfolio.csv"
echo "   • diversified_portfolio.csv ⭐"
echo "   • deployment_config.csv"
echo "   • cost_sensitivity_results.csv"
echo ""
echo "🎯 Next: Review diversified_portfolio.csv"
echo ""
