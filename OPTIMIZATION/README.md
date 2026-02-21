
# Optimization Suite

This directory contains a self-contained environment for optimizing the EMAX strategy.

## Usage

1. **Download Data:**
   `python download_data.py` (Downloads history for 1m, 5m, 15m, 1h, 4h timeframes to dataticks/)\n\n2. **Check Quality:**\n   `python check_data_quality.py` (Verify data coverage and gaps in dataticks/)

2. **Run Optimization:**
   `python optimize.py` (Walk-Forward Optimization on enabled symbols)

3. **Analyze Results:**
   `python stats.py` (View PnL, Win Rate, Drawdown)

4. **Refine Portfolio:**
   - `python remove_losers.py` (Remove worst performers)
   - `python select_robust.py` (Keep only symbols robust across splits)
   - `python add_symbols.py` (Manually add specific symbols)

## Configuration
Edit `config_optimization.json` to change settings.

### Modes
- **static**: Train Odd Months / Test Even Months (Single run per symbol)
- **rolling**: Re-optimize every month (Train M, Test M+1)

To switch modes:
```json
{
  "mode": "rolling"
}
```
