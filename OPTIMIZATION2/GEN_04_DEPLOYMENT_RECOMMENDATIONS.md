# Optimization Results - Deployment Recommendations

## Summary

- **Total Symbols Tested**: 90 (filtered from 946 MT5 symbols)
- **Total Configurations**: 190 (90 symbols × 2 timeframes)
- **Profitable Configs**: 22 (11.6% success rate)
- **Total Test PnL**: $54,730.55

## Filter Criteria Used

### Symbol Filtering (from MT5)
- Max Spread: 0.30%
- Min Volume: 1,000 per bar
- Min History: 400 bars (H1)
- **Result**: 90 liquid symbols passed

### Optimization Filters
- Min Trades: 10
- Min Profit Factor: 1.1
- Timeframes: 15m, 1h only (4h removed as requested)
- Position Sizing: $20 fixed risk per trade, 2.5× ATR stops

## Top Configurations by Expectancy

### Tier 1: High Expectancy (>$50/trade)
| Symbol | TF | Expectancy | PnL | Trades | PF | Notes |
|--------|---|-----------|-----|--------|---|-------|
| **BVSPX** | 1h | **$958.62** | $22,048 | 23 | 3.32 | ⭐ Best performer |
| **BVSPX** | 15m | **$505.29** | $21,222 | 42 | 2.66 | ⭐ Best performer |
| **Nikkei225** | 1h | **$86.13** | $1,895 | 22 | 1.49 | Japan Index |
| **BTCUSD** | 15m | **$61.03** | $5,798 | 95 | 1.14 | Crypto, high volume |

### Tier 2: Good Expectancy ($10-50/trade)
| Symbol | TF | Expectancy | PnL | Trades | PF | Notes |
|--------|---|-----------|-----|--------|---|-------|
| JPN225ft | 1h | $24.11 | $530 | 22 | 1.38 | Japan futures |
| SWI20 | 1h | $20.37 | $754 | 37 | 1.64 | Swiss index |
| JPN225ft | 15m | $12.18 | $1,206 | 99 | 1.12 | High trade count |

### Tier 3: Moderate Expectancy ($1-10/trade)
| Symbol | TF | Expectancy | PnL | Trades | PF | Notes |
|--------|---|-----------|-----|--------|---|-------|
| ETHUSD | 1h | $3.24 | $227 | 70 | 1.33 | Crypto |
| GER40 | 15m | $2.53 | $245 | 97 | 1.12 | Germany DAX |
| XAUUSD | 15m | $2.51 | $126 | 50 | 1.14 | Gold |
| XAUUSD | 1h | $1.77 | $60 | 34 | 1.34 | Gold |
| XLK | 15m | $1.63 | $130 | 80 | 3.50 | Tech ETF, high PF |
| GLD | 15m | $1.56 | $33 | 21 | 1.89 | Gold ETF |

## Asset Class Breakdown

| Asset Class | Configs | Total PnL | Best Symbol |
|------------|---------|-----------|-------------|
| **Indices (CFDs)** | 7 | $46,064 | BVSPX |
| **Crypto** | 2 | $6,025 | BTCUSD |
| **Metals** | 5 | $241 | XAUUSD |
| **ETFs** | 4 | $177 | XLK |
| **Stocks** | 2 | $18 | AAPL |
| **Forex** | 1 | $0 | AUDUSD |

## Deployment Recommendations

### Portfolio A: Maximum Expectancy (Top 6)
Focus on highest expectancy regardless of trade count:

1. **BVSPX** (1h) - $958/trade, 23 trades, PF 3.32
2. **BVSPX** (15m) - $505/trade, 42 trades, PF 2.66
3. **Nikkei225** (1h) - $86/trade, 22 trades, PF 1.49
4. **BTCUSD** (15m) - $61/trade, 95 trades, PF 1.14
5. **JPN225ft** (1h) - $24/trade, 22 trades, PF 1.38
6. **SWI20** (1h) - $20/trade, 37 trades, PF 1.64

**Portfolio Stats:**
- Total PnL: $52,257 (95.5% of all profitable PnL)
- Total Trades: 241
- Avg Expectancy: $217/trade
- Geographic diversity: Brazil, Japan (2x), Switzerland, Crypto

### Portfolio B: Balanced (Top 10)
Add more diversification with moderate expectancy:

Add to Portfolio A:
7. **JPN225ft** (15m) - $12/trade, 99 trades, PF 1.12
8. **ETHUSD** (1h) - $3/trade, 70 trades, PF 1.33
9. **GER40** (15m) - $3/trade, 97 trades, PF 1.12
10. **XAUUSD** (15m) - $3/trade, 50 trades, PF 1.14

**Portfolio Stats:**
- Total PnL: $53,906 (98.5% of all profitable PnL)
- Total Trades: 557
- Avg Expectancy: $97/trade
- Asset classes: Indices, Crypto, Metals

### Portfolio C: Maximum Coverage (All Profitable)
Deploy all 22 profitable configs for maximum diversification.

**Portfolio Stats:**
- Total PnL: $54,731
- Total Trades: 1,179
- Avg Expectancy: $46/trade
- All asset classes included

## Risk Considerations

### Concentration Risk
- **BVSPX** represents 79% of total PnL across just 2 configs
- **Japan exposure** (Nikkei + JPN225ft) = 3 configs, $3,631 PnL
- Consider limiting exposure to any single symbol to 20-30% of capital

### Trade Frequency
- **Low frequency** (<25 trades): BVSPX 1h, Nikkei 1h, JPN225ft 1h, GLD
- **Medium frequency** (25-50 trades): BVSPX 15m, XAU USD, AAPL
- **High frequency** (>80 trades): BTCUSD, JPN225ft 15m, GER40, XLK

### Profit Factor Analysis
- **Excellent (PF > 2.5)**: BVSPX (2), XLK, AAPL, GBTC
- **Good (PF 1.5-2.5)**: GLD, SWI20, XAGUSD
- **Marginal (PF 1.1-1.5)**: Most others - vulnerable to cost increases

## Next Steps

1. **Review EMA Parameters**: Current results show "Rolling" - need to extract actual winning parameters from validation
2. **Run Portfolio Optimizer**: Use `portfolio_optimizer.py` on `GEN_03_all_profitable.csv`
3. **Cost Sensitivity Analysis**: Run `run_cost_sensitivity.py` to test robustness
4. **Forward Testing**: Deploy top 6-10 configs on demo account for 1-2 weeks
5. **Monitor BVSPX carefully**: It dominates results - validate it's not curve-fitted

## Comparison to Previous Results

### Previous Optimization (23 symbols, focused)
- Best: Nikkei225 15m ($10.57/trade), XAUUSD 1h ($8.78/trade)
- Issue: Limited high-expectancy opportunities

### Current Optimization (90 symbols, broad)
- Best: BVSPX 1h ($958/trade), BVSPX 15m ($505/trade)
- **Improvement**: 10-100x better expectancy!

## Files Generated

- `GEN_01_liquid_symbols.csv` - 90 filtered symbols from MT5
- `GEN_01_all_symbols_raw.csv` - Raw analysis of 939 MT5 symbols
- `GEN_02_optimization_results.csv` - All 190 optimization results
- `GEN_03_all_profitable.csv` - 22 profitable configurations
- `GEN_03_high_expectancy.csv` - 3 ultra-high expectancy configs (>$5, PF>1.5)

## Command Reference

```bash
# Step 1: Filter symbols from MT5
wine python GEN_01_filter_symbols_from_mt5.py

# Step 2: Run optimization
wine python optimize.py GEN_02_config_optimization.json

# Step 3: Analyze results
python3 GEN_03_filter_high_expectancy.py

# Next: Portfolio optimization
python3 portfolio_optimizer.py --input GEN_03_all_profitable.csv
```
