# Focused Optimization Guide

## Overview
This guide covers the enhanced optimization setup focusing on proven winners with advanced features including position sizing, filters, and portfolio optimization.

## What Changed

### 1. Filtered Symbol List (23 Top Performers)
**Criteria**: PnL > 0, Trades ≥ 20, Profit Factor ≥ 1.5, Timeframes: 15m & 1h only

**Top Symbols**:
- **Indices**: BVSPX, Nikkei225, JPN225ft, SWI20
- **Crypto**: BTCUSD, ETHUSD, GBTC
- **Precious Metals**: XAUUSD, XAUUSD.crp, XAGUSD, GLD
- **Stocks**: AAPL, ARKK, EXXON, FAZ, GOOG, IWM, MU, NVIDIA, XLK
- **Forex**: USDTJPY
- **Indices (HK)**: HK50ft, HKTECH

### 2. Position Sizing Module
**File**: `position_sizing.py`

**Features**:
- Fixed cash risk per trade (default: $20)
- ATR-based stop distance (2× ATR)
- Auto-detect symbol type (forex/stock/crypto)
- Calculate appropriate lot/share size

**Usage**:
```python
from position_sizing import calculate_position_size_auto

result = calculate_position_size_auto(
    symbol='BTCUSD',
    risk_amount_usd=20.0,
    current_price=45000,
    atr_value=1500,
    atr_multiplier=2.0
)
# Returns: {'lots': 0.007, 'type': 'crypto', 'stop_distance': 3000}
```

### 3. Enhanced Configuration
**File**: `config_optimization_focused.json`

**Key Changes**:
- Timeframes: 15m, 1h only (removed 4h - too few bars)
- Tighter thresholds:
  - min_trades: 20 (was 10)
  - min_win_rate: 35% (was 25%)
  - min_profit_factor: 1.5 (was 1.0)
  - max_dd_to_pnl_ratio: 3.0 (was 5.0)

- Filters enabled:
  - Volume filter: YES (reduce noise on 15m)
  - ATR stops: YES (risk management)
  - Trend filter: NO (too restrictive)

- Position sizing:
  - Enabled: YES
  - Risk per trade: $20 (customizable)
  - Stop distance: 2× ATR

## Running Focused Optimization

### Step 1: Standard Run
```bash
./run_optimize_focused.sh
```

This will:
- Use `config_optimization_focused.json`
- Process 23 top symbols
- Apply volume filter + ATR stops
- Save results to `optimization_results_enhanced.csv`

### Step 2: Custom Risk Amount
Edit `config_optimization_focused.json`:
```json
"position_sizing": {
    "risk_per_trade_usd": 50.0,  // Change from 20 to 50
    ...
}
```

### Step 3: Portfolio Optimization
After optimization completes:
```bash
./run_portfolio_optimizer.sh
```

This finds uncorrelated pairs for diversification.

### Step 4: Transaction Cost Sensitivity
Test robustness with higher costs:
```bash
./run_cost_sensitivity.sh
```

Tests with 1.5× and 2× spreads + slippage.

## Expected Results

### From Initial Run (No Filters)
- 214 profitable configs out of 285 (75%)
- Total PnL: +80,910
- Best: BVSPX 1h (+22,048, PF=3.32)
- Top Crypto: BTCUSD 4h (+19,960, PF=5.64)
- Top Gold: XAUUSD 15m (+999, PF=2.23)

### With Filters Enabled (Focused)
**Expected changes**:
- Fewer total configs (stricter thresholds)
- Higher average profit factor
- More consistent performance
- Better risk-adjusted returns

## Analysis Commands

### View Top Results
```bash
# Top 20 by PnL
awk -F, 'NR>1 && $6 > 0' optimization_results_enhanced.csv | sort -t, -k6 -nr | head -20

# Best profit factors (PF > 2)
awk -F, 'NR>1 && $6 > 0 && $16 > 2' optimization_results_enhanced.csv | sort -t, -k16 -nr

# By timeframe
awk -F, 'NR>1 && $6 > 0 {print $2,$6}' optimization_results_enhanced.csv | \
  awk '{tf[$1]++; sum[$1]+=$2} END {for(t in tf) print t": "sum[t]" ("tf[t]" configs)"}'
```

### Filter Final Candidates
```bash
# Create final list: PF > 2.0, Trades > 30, PnL > 100
awk -F, 'NR==1 || ($6 > 100 && $7 > 30 && $16 > 2.0)' \
  optimization_results_enhanced.csv > final_candidates.csv
```

## Next Steps

1. **Run focused optimization** with new config
2. **Review results** - compare to initial run
3. **Adjust filters** if needed:
   - If too few results: disable volume filter OR lower thresholds
   - If still too noisy: enable trend filter
4. **Portfolio optimization** - find 5-10 uncorrelated pairs
5. **Forward test** top configs in paper trading
6. **Live deployment** after validation

## Configuration Reference

### Risk Sizing Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `risk_per_trade_usd` | 20.0 | Fixed $ risk per trade |
| `atr_multiplier_for_stop` | 2.0 | Stop distance in ATR units |
| `min_lot` | 0.01 | Minimum position size |
| `max_lot` | 100.0 | Maximum position size |

### Filter Parameters
| Filter | Enabled | Effect |
|--------|---------|--------|
| Volume | YES | Only trade when volume > 20-bar MA |
| Trend | NO | Restrict direction based on slow EMA |
| ATR Stops | YES | Exit when loss > 2× ATR |
| Time | NO | Restrict trading hours |

### Threshold Parameters
| Threshold | Value | Purpose |
|-----------|-------|---------|
| min_trades | 20 | Ensure statistical significance |
| min_win_rate | 35% | Baseline win rate |
| min_profit_factor | 1.5 | Quality filter |
| max_dd_to_pnl_ratio | 3.0 | Risk-adjusted filter |

## Files Created

| File | Purpose |
|------|---------|
| `position_sizing.py` | Position size calculation |
| `config_optimization_focused.json` | Focused optimization config |
| `filtered_symbols_top.csv` | Top 23 symbols list |
| `top_symbols.txt` | Symbol list (text format) |
| `run_optimize_focused.sh` | Wrapper script for focused run |
| `FOCUSED_OPTIMIZATION_GUIDE.md` | This guide |

## Troubleshooting

### Issue: Still too many failures
**Solution**: Lower `min_trades` to 15 in config

### Issue: All validation failing
**Solution**: Disable ATR stops OR lower `atr_multiplier` to 1.5

### Issue: Not enough profitable configs
**Solution**: 
1. Lower `min_profit_factor` to 1.3
2. Disable volume filter
3. Check data quality

### Issue: Position sizes too small/large
**Solution**: Adjust `risk_per_trade_usd` or `atr_multiplier_for_stop`

## Contact & Support
For issues or questions, check the main README.md or QUICKSTART.md files.
