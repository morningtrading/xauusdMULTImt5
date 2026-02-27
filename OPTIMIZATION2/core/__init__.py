"""
EMAX Trading Engine - Core Module

This package contains the core components of the EMAX trading system:
- MT5Connector: MetaTrader 5 connection management
- EMAStrategy: EMA crossover signal generation
- PositionManager: Trade execution and risk management
- TelegramNotifier: Trade alerts and notifications
"""

from .mt5_connector import MT5Connector
from .ema_strategy import EMAStrategy, Signal, SignalType
from .position_manager import PositionManager, TradeResult
from .telegram_notifier import TelegramNotifier, get_notifier

__all__ = [
    'MT5Connector',
    'EMAStrategy',
    'Signal',
    'SignalType',
    'PositionManager',
    'TradeResult',
    'TelegramNotifier',
    'get_notifier'
]
