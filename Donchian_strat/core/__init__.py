"""
Donchian Trading Engine - Core Module

This package contains the core components:
- MT5Connector: MetaTrader 5 connection management
- DonchianStrategy: Donchian Channel breakout signal generation
- PositionManager: Trade execution and risk management
- TelegramNotifier: Trade alerts and notifications
"""

from .mt5_connector import MT5Connector
from .donchian_strategy import DonchianStrategy, Signal, SignalType
from .position_manager import PositionManager, TradeResult
from .telegram_notifier import TelegramNotifier, get_notifier

__all__ = [
    'MT5Connector',
    'DonchianStrategy',
    'Signal',
    'SignalType',
    'PositionManager',
    'TradeResult',
    'TelegramNotifier',
    'get_notifier'
]
