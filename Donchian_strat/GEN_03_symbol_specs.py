#!/usr/bin/env python3
"""
Query MT5 for contract specs needed for accurate backtest PnL calculation.
Outputs: symbol, contract_size, tick_size, tick_value, currency_profit, point, digits
"""
import json
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    print("MetaTrader5 not installed. Install with: pip install MetaTrader5")
    exit(1)

CONFIG_PATH = Path(__file__).parent / "config" / "trading_config.json"

with open(CONFIG_PATH) as f:
    config = json.load(f)

symbols = config["symbols"]["enabled"]

if not mt5.initialize():
    print(f"MT5 init failed: {mt5.last_error()}")
    exit(1)

print(f"{'Symbol':<14} {'ContractSz':>11} {'TickSize':>12} {'TickValue':>10} {'Point':>12} {'Digits':>6} {'CurrProfit':<10}")
print("-" * 90)

specs = {}
for sym in symbols:
    info = mt5.symbol_info(sym)
    if info is None:
        print(f"{sym:<14} NOT FOUND")
        continue

    # tick_value = dollar value of 1 tick movement for 1 lot
    print(f"{sym:<14} {info.trade_contract_size:>11.2f} {info.trade_tick_size:>12.5f} "
          f"{info.trade_tick_value:>10.4f} {info.point:>12.5f} {info.digits:>6} {info.currency_profit:<10}")

    specs[sym] = {
        "contract_size": info.trade_contract_size,
        "tick_size": info.trade_tick_size,
        "tick_value": info.trade_tick_value,
        "point": info.point,
        "digits": info.digits,
        "currency_profit": info.currency_profit,
    }

# Show how to calculate real PnL
print("\n" + "=" * 90)
print("PnL FORMULA:  real_pnl = (price_change / tick_size) * tick_value * volume")
print("=" * 90)

# Example calculation with backtest results
bt_results = {
    "Nikkei225": {"raw_pnl": 6310.83, "volume": 0.1},
    "JPN225ft":  {"raw_pnl": 7061.31, "volume": 0.1},
    "XAUUSD":    {"raw_pnl": 791.76, "volume": 0.01},
    "BTCUSD":    {"raw_pnl": -11053.35, "volume": 0.01},
    "GER40":     {"raw_pnl": 550.64, "volume": 0.1},
    "GER40ft":   {"raw_pnl": -1914.32, "volume": 0.1},
    "NAS100":    {"raw_pnl": 539.55, "volume": 0.1},
}

print(f"\n{'Symbol':<14} {'RawPnL(pts)':>12} {'Vol':>5} {'TickSz':>10} {'TickVal':>8} {'REAL PnL($)':>12} {'Old PnL($)':>11}")
print("-" * 80)

total_real = 0
total_old = 0
for sym, bt in bt_results.items():
    if sym in specs:
        sp = specs[sym]
        ticks = bt["raw_pnl"] / sp["tick_size"]
        real_pnl = ticks * sp["tick_value"] * bt["volume"]
        old_pnl = bt["raw_pnl"] * bt["volume"]
        total_real += real_pnl
        total_old += old_pnl
        print(f"{sym:<14} {bt['raw_pnl']:>+12.2f} {bt['volume']:>5.2f} {sp['tick_size']:>10.5f} "
              f"{sp['tick_value']:>8.4f} {real_pnl:>+12.2f} {old_pnl:>+11.2f}")

print("-" * 80)
print(f"{'TOTAL':<14} {'':>12} {'':>5} {'':>10} {'':>8} {total_real:>+12.2f} {total_old:>+11.2f}")

mt5.shutdown()
