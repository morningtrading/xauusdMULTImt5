# OPTIMIZATION2 - Quick Start Guide

## 🎯 TL;DR - Run This

**Note: Data already exists in `dataticks/` - no need to download!**

**IMPORTANT: Use Wine Python wrappers (for MT5 support on Linux)**

```bash
cd OPTIMIZATION2

# Option 1: Run complete pipeline (all steps)
./run_pipeline.sh

# Option 2: Run steps individually
./run_optimize.sh                      # Step 1: Optimization (30-60 min)
./run_select_robust.sh                 # Step 2: Filter results
./run_portfolio.sh --max-positions 15  # Step 3: Build portfolio
./run_cost_sensitivity.sh              # Step 4: Cost analysis

# Done! Check diversified_portfolio.csv for your final portfolio
```

**Or use wine python directly:**
```bash
./wine_python.sh optimize.py
./wine_python.sh select_robust.py
# etc...
```

---

## 📁 What's Different from OPTIMIZATION?

### New Files:
- **config_optimization.json** - Enhanced config with strict thresholds
- **optimize.py** - New optimizer with validation split and fitness function
- **select_robust.py** - Strict filtering (Test PnL>0, WR>35%, PF>1.3)
- **portfolio_optimizer.py** - Builds diversified portfolio
- **cost_sensitivity.py** - Transaction cost analysis
- **README.md** - Comprehensive documentation
- **QUICKSTART.md** - This file!

### Key Changes:
1. **208 combinations** (vs 2,511) - Coarser grid reduces overfitting
2. **3-month validation** (Train → Validate → Test)
3. **Risk-adjusted fitness** (Return/DD ratio, not just PnL)
4. **Strict filters** (35% win rate, 1.3 profit factor, etc.)
5. **Portfolio diversification** (max 2 per symbol, 4 per group)
6. **Transaction cost testing** (1.5x, 2x spreads + slippage)

---

## ⚙️ Configuration

Edit `config_optimization.json` to customize:

```json
{
  "timeframes": ["15m", "1h", "4h"],  // Lower frequencies = more robust
  "thresholds": {
    "min_trades": 30,                   // Increase for more data
    "min_win_rate": 35.0,               // Increase for safety
    "max_dd_to_pnl_ratio": 2.0,         // Lower = less drawdown
    "min_profit_factor": 1.2            // Increase for profitability
  },
  "features": {
    "use_volume_filter": true,          // Filter low volume
    "use_trend_filter": true,           // Trade with trend
    "use_atr_stops": true               // Dynamic stops
  }
}
```

---

## 📊 Expected Results

### Before (OPTIMIZATION):
- Overfitting: **High** (Train PnL >> Test PnL)
- Profitable configs: **~25%**
- Avg win rate: **~25%**
- Drawdown: **3-5x PnL**

### After (OPTIMIZATION2):
- Overfitting: **Low** (validated)
- Profitable configs: **~50%**
- Avg win rate: **~40%**
- Drawdown: **<2x PnL**

---

## 🔧 Troubleshooting

### No configurations passed filters?
**Solution**: Edit `config_optimization.json`:
```json
{
  "thresholds": {
    "min_win_rate": 30.0,     // Lower from 35
    "min_profit_factor": 1.1  // Lower from 1.2
  }
}
```

### Optimization too slow?
**Solution**: Reduce symbols or timeframes:
```json
{
  "timeframes": ["1h", "4h"]  // Skip 15m
}
```

### Results too conservative?
**Solution**: Use more aggressive thresholds:
```json
{
  "thresholds": {
    "min_trades": 20,
    "min_win_rate": 30.0,
    "max_dd_to_pnl_ratio": 3.0
  }
}
```

---

## 📈 Understanding Output Files

| When | File | What to Check |
|------|------|---------------|
| After optimize.py | `optimization_results_enhanced.csv` | All raw results |
| After select_robust.py | `robust_portfolio.csv` | Passed all filters |
| After select_robust.py | `top_20_portfolio.csv` | Top 20 by Return/DD |
| After portfolio_optimizer.py | `diversified_portfolio.csv` | **Final portfolio** ⭐ |
| After portfolio_optimizer.py | `deployment_config.csv` | Ready to deploy |
| After cost_sensitivity.py | `cost_sensitivity_results.csv` | Robustness score |

---

## 🚀 Deploy to Live Trading

Once you have `deployment_config.csv`:

1. **Paper trade first** for 1-2 weeks
2. **Monitor** win rate and drawdown
3. **Start small** (1-5% of capital per position)
4. **Re-optimize monthly** to adapt to market changes

---

## 💡 Pro Tips

1. **Focus on 1h and 4h** - Most robust, lowest costs
2. **Max 15 positions** - Balance diversification and management
3. **Monitor correlation** - If all positions lose together, diversification failed
4. **Re-optimize regularly** - Markets change, adapt monthly
5. **Use cost sensitivity** - Always test with 1.5x-2x spreads

---

## 📞 Need Help?

Check `README.md` for full documentation including:
- Detailed metric explanations
- Advanced configuration options
- Comparison with OPTIMIZATION v1
- Contributing guidelines

---

**Built with ❤️ to combat overfitting and improve trading system robustness.**
