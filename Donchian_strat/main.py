"""
================================================================================
DONCHIAN TRADING ENGINE - Main Entry Point
================================================================================

Orchestrates all components for Donchian Channel Breakout trading:
- MT5 connection and data retrieval
- Donchian strategy signal generation
- Position management and execution
- Telegram notifications
- Web Dashboard server (port 8082)

HOW TO START:
    wine terminal64.exe   # Start MT5 first
    wine python main.py   # Then run engine

AUTHOR: Donchian Trading Engine
VERSION: 1.0.0
================================================================================
"""

import os
import sys
import json
import time
import logging
import signal
import threading
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.mt5_connector import MT5Connector
from core.donchian_strategy import DonchianStrategy, SignalType
from core.position_manager import PositionManager
from core.telegram_notifier import TelegramNotifier
from core.constants import DEFAULTS

CONFIG_PATH = Path(__file__).parent / 'config' / 'trading_config.json'
INSTANCE_ID = "DONCHIAN"
try:
    with open(CONFIG_PATH, 'r') as f:
        _cfg = json.load(f)
        INSTANCE_ID = _cfg.get('telegram', {}).get('message_prefix', 'DONCHIAN')
except (FileNotFoundError, json.JSONDecodeError):
    pass

log_file = Path(__file__).parent / 'trading_engine.log'
try:
    log_fp = open(str(log_file), 'a', buffering=1, encoding='utf-8')
    sys.stdout = log_fp
    sys.stderr = log_fp
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s - [{INSTANCE_ID}] - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('DonchianEngine')


class DonchianEngine:
    """
    Main Donchian Trading Engine

    Coordinates all trading components using Donchian Channel Breakout signals.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.running = False
        self.paused = False

        if config_path is None:
            config_path = Path(__file__).parent / 'config' / 'trading_config.json'

        self.config_path = config_path
        self.config = self._load_config(config_path)

        # Initialize components
        self.mt5 = MT5Connector(config_path)
        self.strategy = DonchianStrategy(config_path)
        self.position_manager = PositionManager(self.mt5, config_path)
        self.telegram = TelegramNotifier(config_path)

        # Trading state
        self.trading_enabled = self.config.get('strategy', {}).get('trading_enabled', True)
        self.direction = self.config.get('strategy', {}).get('direction', 'both')
        self.enabled_symbols = self.config.get('symbols', {}).get('enabled', [])

        # Data refresh
        data_config = self.config.get('data_refresh', {})
        self.price_refresh_ms = data_config.get('price_refresh_ms', 1000)
        
        # MT5 connection monitoring
        self.mt5_check_interval = 30  # Check MT5 connection every 30 seconds
        self.last_mt5_check = 0
        self.next_mt5_check = self.mt5_check_interval

        # Dashboard data
        self.dashboard_data = {
            'connection_status': {
                'mt5_connected': False,
                'mt5_status': 'Not connected',
                'next_check_seconds': self.mt5_check_interval
            },
            'account_info': {},
            'positions': [],
            'strategy_status': {},
            'last_signals': {},
            'channel_values': {},
            'engine_status': {
                'trading_enabled': self.trading_enabled,
                'direction': self.direction,
                'enabled_symbols': self.enabled_symbols,
                'running': False,
                'strategy_type': 'donchian'
            },
            'daily_pnl': {
                'today': 0.0,
                'starting_balance': 0.0,
                'current_balance': 0.0,
                'trades_today': 0,
                'winners': 0,
                'losers': 0
            },
            'trade_history': []  # Last 20 closed trades
        }
        self.dashboard_lock = threading.Lock()
        self.last_bar_time: Dict[str, str] = {}
        self.start_time = datetime.now()
        self.daily_start_balance = 0.0
        self.last_history_check = 0

        logger.info("DonchianEngine initialized")

    def _load_config(self, config_path) -> Dict:
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}

    def _get_timeframe_for_symbol(self, symbol: str) -> str:
        """Get configured timeframe for symbol"""
        settings = self.config.get('symbols', {}).get('settings', {})
        sym_settings = settings.get(symbol, {})
        return sym_settings.get('timeframe', 'H1')

    def update_daily_pnl(self):
        """Update daily P&L statistics"""
        try:
            account_info = self.mt5.get_account_summary()
            if not account_info or 'error' in account_info:
                return
            
            current_balance = account_info.get('balance', 0)
            
            # Initialize starting balance on first run or new day
            if self.daily_start_balance == 0 or datetime.now().date() != self.start_time.date():
                self.daily_start_balance = current_balance
                self.start_time = datetime.now()
            
            daily_pnl = current_balance - self.daily_start_balance
            
            # Get today's trade history
            today_deals = self.mt5.get_history_deals(days=1)
            trades_today = len([d for d in today_deals if d.get('entry') == 1])  # entry=1 means 'out' (closed)
            winners = len([d for d in today_deals if d.get('profit', 0) > 0 and d.get('entry') == 1])
            losers = len([d for d in today_deals if d.get('profit', 0) < 0 and d.get('entry') == 1])
            
            with self.dashboard_lock:
                self.dashboard_data['daily_pnl'] = {
                    'today': daily_pnl,
                    'starting_balance': self.daily_start_balance,
                    'current_balance': current_balance,
                    'trades_today': trades_today,
                    'winners': winners,
                    'losers': losers,
                    'win_rate': (winners / trades_today * 100) if trades_today > 0 else 0
                }
        except Exception as e:
            logger.error(f"Error updating daily P&L: {e}")
    
    def update_trade_history(self):
        """Update trade history with last 20 closed trades"""
        try:
            # Get last 7 days of deals to ensure we have enough
            deals = self.mt5.get_history_deals(days=7)
            
            # Filter for closed trades (entry=1 means 'out')
            closed_trades = [d for d in deals if d.get('entry') == 1]
            
            # Sort by time (newest first) and take last 20
            closed_trades.sort(key=lambda x: x.get('time', ''), reverse=True)
            trade_history = closed_trades[:20]
            
            with self.dashboard_lock:
                self.dashboard_data['trade_history'] = trade_history
        except Exception as e:
            logger.error(f"Error updating trade history: {e}")
    
    def close_all_positions(self):
        """Close all open positions (panic button)"""
        try:
            result = self.mt5.close_all_positions()
            logger.info(f"Close all positions: {result}")
            self.telegram.send_message(
                f"🚨 <b>ALL POSITIONS CLOSED</b>\n"
                f"Closed: {result.get('closed', 0)}\n"
                f"Failed: {result.get('failed', 0)}"
            )
            return result
        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            return {'success': False, 'error': str(e)}
    
    def update_mt5_connection_status(self):
        """Update MT5 connection status in dashboard data"""
        try:
            conn_status = self.mt5.get_connection_status()
            account_info = self.mt5.get_account_summary() if conn_status.get('connected') else {}
            
            with self.dashboard_lock:
                self.dashboard_data['connection_status'] = {
                    'mt5_connected': conn_status.get('connected', False),
                    'mt5_status': 'Connected' if conn_status.get('connected') else conn_status.get('error', 'Disconnected'),
                    'mt5_server': conn_status.get('server', '-'),
                    'mt5_account': conn_status.get('account', '-'),
                    'is_demo': conn_status.get('is_demo', None),
                    'next_check_seconds': self.next_mt5_check
                }
                self.dashboard_data['account_info'] = account_info
                
                # Update positions with duration and P&L percentage
                positions = self.mt5.get_positions()
                for pos in positions:
                    # Calculate position duration
                    if 'time' in pos:
                        try:
                            open_time = datetime.fromisoformat(pos['time'])
                            duration = datetime.now() - open_time
                            pos['duration_hours'] = duration.total_seconds() / 3600
                        except:
                            pos['duration_hours'] = 0
                    
                    # Calculate P&L percentage
                    if 'price_open' in pos and 'profit' in pos and 'volume' in pos:
                        try:
                            # Rough estimation of P&L %
                            pos['pnl_percent'] = (pos['profit'] / (pos['price_open'] * pos['volume'])) * 100
                        except:
                            pos['pnl_percent'] = 0
                
                self.dashboard_data['positions'] = positions
                
                # Update strategy status with timeframes
                symbol_timeframes = {sym: self._get_timeframe_for_symbol(sym) for sym in self.enabled_symbols}
                self.dashboard_data['strategy_status'] = {
                    'channel_period': self.strategy.channel_period,
                    'direction': self.direction,
                    'trading_enabled': self.trading_enabled,
                    'enabled_symbols': self.enabled_symbols,
                    'symbol_timeframes': symbol_timeframes
                }
                
                # Update daily P&L and trade history
                self.update_daily_pnl()
                
                # Update trade history every 60 seconds
                if time.time() - self.last_history_check > 60:
                    self.update_trade_history()
                    self.last_history_check = time.time()
                    
        except Exception as e:
            logger.error(f"Error updating MT5 connection status: {e}")
            with self.dashboard_lock:
                self.dashboard_data['connection_status'] = {
                    'mt5_connected': False,
                    'mt5_status': f'Error: {str(e)}',
                    'next_check_seconds': self.next_mt5_check
                }
    
    def run_cycle(self):
        """Single analysis cycle for all symbols"""
        # Update MT5 connection check countdown
        current_time = time.time()
        elapsed = current_time - self.last_mt5_check
        self.next_mt5_check = max(0, self.mt5_check_interval - int(elapsed))
        
        # Periodic MT5 connection check
        if elapsed >= self.mt5_check_interval:
            self.update_mt5_connection_status()
            self.last_mt5_check = current_time
            self.next_mt5_check = self.mt5_check_interval
        else:
            # Just update countdown without full check
            with self.dashboard_lock:
                self.dashboard_data['connection_status']['next_check_seconds'] = self.next_mt5_check
        
        for symbol in self.enabled_symbols:
            try:
                timeframe = self._get_timeframe_for_symbol(symbol)
                period = self.strategy.get_symbol_settings(symbol)

                # Fetch bars
                bars = self.mt5.get_rates(symbol, timeframe, period + 20)
                if not bars:
                    continue

                # Check current position
                positions = self.mt5.get_positions(symbol)
                current_pos = None
                if positions:
                    for pos in positions:
                        if pos.get('magic') == self.config.get('magic_number', 234567):
                            current_pos = "LONG" if pos.get('type') == 0 else "SHORT"
                            break

                # Analyze
                signal_result = self.strategy.analyze(symbol, bars, current_pos)

                # Update dashboard
                with self.dashboard_lock:
                    self.dashboard_data['last_signals'][symbol] = {
                        'action': signal_result.action.value,
                        'reason': signal_result.reason,
                        'strength': signal_result.strength,
                        'upper': signal_result.upper_channel,
                        'lower': signal_result.lower_channel,
                        'mid': signal_result.mid_channel,
                        'price': signal_result.price,
                        'timestamp': signal_result.timestamp
                    }
                    self.dashboard_data['channel_values'][symbol] = self.strategy.get_channel_values(symbol)

                # Execute signals
                if signal_result.action == SignalType.BUY:
                    self.position_manager.open_position(symbol, "LONG", reason=signal_result.reason)
                elif signal_result.action == SignalType.SELL:
                    self.position_manager.open_position(symbol, "SHORT", reason=signal_result.reason)
                elif signal_result.action in (SignalType.EXIT_LONG, SignalType.EXIT_SHORT):
                    self.position_manager.close_position(symbol, reason=signal_result.reason)

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")

    def start(self):
        """Start the trading engine main loop"""
        if not self.mt5.connect():
            logger.critical("Failed to connect to MT5")
            return

        self.running = True
        self.dashboard_data['engine_status']['running'] = True
        
        # Initialize MT5 connection status
        self.last_mt5_check = time.time()
        self.update_mt5_connection_status()

        # Start dashboard
        dash_config = self.config.get('dashboard', {})
        if dash_config.get('enabled', True):
            try:
                from dashboard.web_dashboard import start_dashboard
                dash_thread = threading.Thread(
                    target=start_dashboard,
                    args=(self,),
                    daemon=True
                )
                dash_thread.start()
                logger.info(f"Dashboard started on port {dash_config.get('port', 8082)}")
            except Exception as e:
                logger.warning(f"Dashboard failed to start: {e}")

        # Send startup notification
        self.telegram.send_message(
            f"🚀 <b>Donchian Engine Started</b>\n"
            f"Symbols: {', '.join(self.enabled_symbols)}\n"
            f"Strategy: Donchian Channel (period={self.strategy.channel_period})"
        )

        logger.info(f"Engine started. Symbols: {self.enabled_symbols}")

        # Main loop
        while self.running:
            try:
                if not self.paused:
                    self.run_cycle()
                time.sleep(self.price_refresh_ms / 1000.0)
            except KeyboardInterrupt:
                logger.info("Shutdown requested")
                self.running = False
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                time.sleep(5)

        self.mt5.disconnect()
        logger.info("Engine stopped")


if __name__ == "__main__":
    engine = DonchianEngine()
    engine.start()
