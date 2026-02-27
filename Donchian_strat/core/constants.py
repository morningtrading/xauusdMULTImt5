"""
================================================================================
CORE CONSTANTS - Donchian Trading Engine
================================================================================
Central repository for all constant values and default settings.
================================================================================
"""

DEFAULTS = {
    "LOG_LEVEL": "INFO",
    "LOG_FILE": "trading_engine.log",
    "CONNECTION_TIMEOUT_SEC": 30,
    "MAX_RECONNECT_ATTEMPTS": 5,
    "RECONNECT_DELAY_SEC": 5,
    "PRICE_REFRESH_MS": 1000,
    "ORDER_REFRESH_MS": 2000,
    "MARKET_STALENESS_SEC": 1200,

    # Donchian Strategy defaults
    "DEFAULT_CHANNEL_PERIOD": 20,
    "LOOKBACK_BARS": 100,

    # Risk
    "DEFAULT_RISK_PERCENT": 1.0,
    "MAX_SLIPPAGE_POINTS": 50,
    "DEFAULT_MAGIC_NUMBER": 234567,
}

LIMITS = {
    "MAX_LEVERAGE": 1000,
    "MIN_LOT_SIZE": 0.01,
    "MAX_LOT_SIZE": 100.0,
    "MAX_OPEN_POSITIONS": 20,
    "MAX_DAILY_LOSS_PERCENT": 95.0,
}

REQUIRED_CONFIG_KEYS = [
    "account",
    "symbols",
    "strategy",
    "risk_management"
]
