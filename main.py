"""
================================================================================
EMAX TRADING ENGINE - Main Entry Point
================================================================================

PURPOSE:
    The main trading engine that orchestrates all components:
    - MT5 connection and data retrieval
    - EMA strategy signal generation
    - Position management and execution
    - Telegram notifications
    - Web Dashboard server

INPUTS:
    - Configuration: config/trading_config.json
    - Environment: MetaTrader 5 terminal running under Wine
    - System: Linux OS with Python 3.10+

OUTPUTS:
    - Execution: Trades placed on MT5 terminal
    - UI: Web dashboard at http://localhost:8080 (configurable)
    - Logs: trading_engine.log
    - Alerts: Telegram notifications

INSTALLATION:
    1. Install Wine and MT5 (see README.md)
    2. Install dependencies: wine pip install -r requirements.txt
    3. Configure: config/trading_config.json
    
HOW TO START:
    # Start MT5 terminal first
    wine terminal64.exe
    
    # Then run the engine
    wine python main.py

SEQUENCE:
    1. Load and validate configuration
    2. Connect to MT5
    3. Initialize strategy and position manager
    4. Start web dashboard
    5. Main loop: fetch data -> analyze -> execute

CONTEXT:
    This is the central controller. It depends on:
    - core/mt5_connector.py
    - core/ema_strategy.py
    - core/position_manager.py
    - config/trading_config.json

VERSION HISTORY:
    1.1.0 (2026-01-28) - Added config validation, standardized headers, and constants
    1.0.0 (2026-01-22) - Initial release

AUTHOR: EMAX Trading Engine
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

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.mt5_connector import MT5Connector
from core.ema_strategy import EMAStrategy, SignalType
from core.position_manager import PositionManager
from core.telegram_notifier import TelegramNotifier
from core.constants import DEFAULTS
from config.validate_config import validate_config

# Load config early for logging setup
CONFIG_PATH = Path(__file__).parent / 'config' / 'trading_config.json'
INSTANCE_ID = "EMAX"
try:
    with open(CONFIG_PATH, 'r') as f:
        _cfg = json.load(f)
        INSTANCE_ID = _cfg.get('telegram', {}).get('message_prefix', 'EMAX')
        if not INSTANCE_ID:
            INSTANCE_ID = Path(__file__).parent.name
except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
    # Use default INSTANCE_ID if config cannot be read
    pass

# Configure logging
log_file = Path(__file__).parent / 'trading_engine.log'

# Redirect stdout/stderr to file to prevent WinError 6 in detached Wine mode
# and capture all output including print() statements
try:
    # Open file in append mode, buffered
    log_fp = open(str(log_file), 'a', buffering=1, encoding='utf-8')
    sys.stdout = log_fp
    sys.stderr = log_fp
except Exception as e:
    # If we can't open log file, we're in trouble, but try to continue
    pass

logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s - [{INSTANCE_ID}] - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout) # Now safe because stdout is a file
    ]
)
logger = logging.getLogger('TradingEngine')


class TradingEngine:
    """
    Main EMAX Trading Engine
    
    Coordinates all trading components:
    - MT5 connection
    - Strategy analysis
    - Position execution
    - Notifications
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Trading Engine
        
        Args:
            config_path: Path to trading_config.json
        """
        self.running = False
        self.paused = False
        
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent / 'config' / 'trading_config.json'
        
        # Validate Config
        if not validate_config(str(config_path)):
            logger.critical("Config validation failed! See logs for details.")
            if "--force" not in sys.argv:
                logger.critical("Startup aborted due to invalid config.")
                sys.exit(1)
        
        self.config_path = config_path
        self.config = self._load_config(config_path)
        
        # Initialize components
        self.mt5 = MT5Connector(config_path)
        self.strategy = EMAStrategy(config_path)
        self.position_manager = PositionManager(self.mt5, config_path)
        self.telegram = TelegramNotifier(config_path)
        
        # Trading state
        self.trading_enabled = self.config.get('strategy', {}).get('trading_enabled', True)
        self.direction = self.config.get('strategy', {}).get('direction', 'both')
        self.enabled_symbols = self.config.get('symbols', {}).get('enabled', [])
        
        # Data refresh settings
        data_config = self.config.get('data_refresh', {})
        self.price_refresh_ms = data_config.get('price_refresh_ms', 1000)
        self.order_refresh_ms = data_config.get('order_refresh_ms', 2000)
        
        # Dashboard data (shared with web server)
        self.dashboard_data = {
            'connection_status': {},
            'account_info': {},
            'positions': [],
            'orders_history': [],
            'strategy_status': {},
            'manager_status': {},
            'last_signals': {},
            'ema_values': {},
            'daily_stats': {},
            'engine_status': {
                'trading_enabled': self.trading_enabled,
                'direction': self.direction,
                'enabled_symbols': self.enabled_symbols,
                'running': False,
                'uptime': 0
            },
            'last_cycle_stats': {}
        }
        self.market_overview = {}
        self.dashboard_lock = threading.Lock()
        
        # Track last bar times to detect new bars
        self.last_bar_time: Dict[str, str] = {}
        
        # Start time for uptime stats and history filtering
        self.start_time = datetime.now()
        self.stats_reset_time = self.start_time
        
        # Connect to MT5 first to validate symbols
        if self.mt5.connect():
            self.enabled_symbols = self._validate_symbols()
        else:
            logger.warning("Could not connect to MT5 for symbol validation. Using config symbols.")
        
        logger.info("Trading Engine initialized")
        logger.info(f"Enabled symbols: {self.enabled_symbols}")
        
    def _validate_symbols(self):
        """Validate that enabled symbols exist on the broker"""
        valid_symbols = []
        
        # Ensure connected
        if not self.mt5.connected:
            return self.enabled_symbols
            
        for symbol in self.enabled_symbols:
            info = self.mt5.get_symbol_info(symbol)
            if info:
                valid_symbols.append(symbol)
                logger.info(f"Symbol verified: {symbol}")
            else:
                logger.error(f"Symbol NOT FOUND: {symbol}. Please check Market Watch.")
            
        return valid_symbols
    
    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def reload_config(self):
        """Reload configuration from file"""
        self.config = self._load_config(self.config_path)
        self.trading_enabled = self.config.get('strategy', {}).get('trading_enabled', True)
        self.direction = self.config.get('strategy', {}).get('direction', 'both')
        self.enabled_symbols = self.config.get('symbols', {}).get('enabled', [])
        
        # Re-validate symbols
        if self.mt5.connected:
            self.enabled_symbols = self._validate_symbols()
            
        logger.info("Configuration reloaded")
    
    def connect(self) -> bool:
        """
        Connect to MT5
        
        Returns:
            bool: True if connected successfully
        """
        if self.mt5.connect():
            # Verify demo account
            status = self.mt5.get_connection_status()
            if self.config.get('account', {}).get('demo_only', True):
                if not status.get('is_demo', False):
                    logger.error("SAFETY: Real account detected! Demo only mode is enabled.")
                    self.telegram.notify_error("Safety", "Real account blocked - demo_only mode")
                    self.mt5.disconnect()
                    return False
            
            # Send connection notification and store initial balance
            account_info = self.mt5.get_account_summary()
            self.initial_balance = account_info.get('balance', 0)
            self.telegram.send_status(True, account_info)
            
            return True
        
        return False
    
    def disconnect(self):
        """Disconnect from MT5"""
        self.mt5.disconnect()
    
    def set_trading_enabled(self, enabled: bool):
        """Enable or disable trading"""
        self.trading_enabled = enabled
        self.strategy.set_trading_enabled(enabled)
        logger.info(f"Trading {'enabled' if enabled else 'disabled'}")
    
    def set_direction(self, direction: str):
        """Set trading direction (both, long, short)"""
        if direction in ['both', 'long', 'short']:
            self.direction = direction
            self.strategy.set_direction(direction)
            logger.info(f"Direction set to: {direction}")

    def freeze_trading(self, reason: str = "Manual freeze"):
        """
        Freeze trading - stops NEW trades but lets existing positions run

        Useful for:
        - High-impact news events (manual or automated)
        - High volatility periods
        - Manual risk control

        Args:
            reason: Why trading is being frozen
        """
        self.position_manager.freeze_trading(reason)

    def unfreeze_trading(self):
        """Unfreeze trading - resume taking new trades"""
        self.position_manager.unfreeze_trading()

    def is_trading_frozen(self) -> bool:
        """Check if trading is currently frozen"""
        return self.position_manager.is_trading_frozen()

    def panic_close_all(self):
        """Close all positions immediately"""
        logger.warning("PANIC BUTTON PRESSED!")
        
        # Get current positions for PnL calculation
        positions = self.mt5.get_positions()
        total_pnl = sum(p.get('profit', 0) for p in positions)
        
        # Close all
        result = self.position_manager.close_all_positions()
        
        # Notify
        self.telegram.send_panic_alert(result.get('closed', 0), total_pnl)
        
        return result
    
    def _update_dashboard_data(self):
        """Update data for dashboard display"""
        with self.dashboard_lock:
            # Connection status
            self.dashboard_data['connection_status'] = self.mt5.get_connection_status()
            
            # Account info
            self.dashboard_data['account_info'] = self.mt5.get_account_summary()
            
            # Current positions
            self.dashboard_data['positions'] = self.mt5.get_positions()
            
            # Recent deals/orders (Session only)
            recent_deals = self.mt5.get_history_deals(days=1)
            cutoff = self.stats_reset_time.isoformat()
            self.dashboard_data['orders_history'] = [d for d in recent_deals if d['time'] >= cutoff][-100:]
            
            # Strategy and manager status
            self.dashboard_data['strategy_status'] = self.strategy.get_strategy_status()
            self.dashboard_data['manager_status'] = self.position_manager.get_manager_status()
            
            # Daily stats
            self.dashboard_data['daily_stats'] = self.position_manager.get_daily_stats()
            
            # Session Stats (Since bot start)
            self.dashboard_data['session_stats'] = self.position_manager.get_stats_since(self.start_time)
            
            # Engine status
            # Get timeframe from first enabled symbol's config
            # STRICT CONFIG ACCESS
            try:
                first_symbol = self.enabled_symbols[0] if self.enabled_symbols else 'XAUUSD'
                symbol_settings = self.config['symbols']['settings'][first_symbol]
                current_timeframe = symbol_settings['timeframe']
            except KeyError as e:
                logger.error(f"STRICT CONFIG ERROR: Missing key {e} in symbols/settings")
                # We can't proceed without knowing the timeframe for the dashboard
                current_timeframe = "ERROR"
            
            self.dashboard_data['engine_status'] = {
                'trading_enabled': self.trading_enabled,
                'direction': self.direction,
                'enabled_symbols': self.enabled_symbols,
                'running': self.running,
                'paused': self.paused,
                'uptime': (datetime.now() - self.start_time).seconds if self.start_time else 0,
                'timeframe': current_timeframe
            }
            
            # Market Overview
            self.dashboard_data['market_overview'] = dict(self.market_overview)
    
    def _execute_trade_entry(self, symbol: str, direction: str, result, signal_reason: str, timeframe: str):
        """
        Execute trade entry and send notifications
        
        Args:
            symbol: Trading symbol
            direction: "LONG" or "SHORT"
            result: TradeResult from position_manager.open_position()
            signal_reason: Reason for the trade signal
            timeframe: Timeframe for data retrieval
        """
        if result.success:
            # Console output
            emoji = "🟢" if direction == "LONG" else "🔴"
            print(f"\n{'='*50}")
            print(f"{emoji} TRADE OPENED: {symbol} {direction}")
            print(f"   Ticket: {result.ticket}")
            print(f"   Volume: {result.volume}")
            print(f"   Price:  {result.price}")
            print(f"   SL:     {result.sl}")
            print(f"{'='*50}\n")
            
            # Get account info and EMA values for telegram
            account = self.mt5.get_account_summary()
            bars = self.mt5.get_rates(symbol, timeframe, DEFAULTS['LOOKBACK_BARS'])
            fast_ema = slow_ema = None
            
            if bars is not None:
                symbol_settings = self.config.get('symbols', {}).get('settings', {}).get(symbol, {})
                fast_period = symbol_settings.get('fast_ema', 9)
                slow_period = symbol_settings.get('slow_ema', 41)
                from core.ema_strategy import EMAStrategy
                fast_ema = EMAStrategy.calculate_ema(bars['close'], fast_period)[-1]
                slow_ema = EMAStrategy.calculate_ema(bars['close'], slow_period)[-1]
            
            # Send Telegram notification
            self.telegram.notify_trade_entry(
                symbol, direction, result.volume, result.price, result.sl, signal_reason,
                margin=result.margin_used,
                fast_ema=fast_ema,
                slow_ema=slow_ema,
                balance=account.get('balance'),
                equity=account.get('equity')
            )
        elif result.error:
            print(f"\n❌ ORDER FAILED [{symbol}]: {result.error}\n")
            self.telegram.notify_error("Order Failed", result.error, symbol)
    
    def _process_symbol(self, symbol: str):
        """
        Process a single symbol: get data, analyze, execute
        
        Args:
            symbol: Trading symbol
        """
        # Get current position for this symbol
        positions = self.mt5.get_positions(symbol)
        current_position = None
        if positions:
            current_position = "LONG" if positions[0]['type'] == "BUY" else "SHORT"
        
        # Get price data with enough bars for EMA calculation
        # Get price data with enough bars for EMA calculation
        try:
             symbol_config = self.config['symbols']['settings'][symbol]
             timeframe = symbol_config['timeframe']
        except KeyError as e:
             logger.error(f"[{symbol}] STRICT CONFIG ERROR: Missing '{e}' setting")
             return
        
        bars = self.mt5.get_rates(symbol, timeframe, count=DEFAULTS['LOOKBACK_BARS'])
        if not bars:
            logger.warning(f"[{symbol}] Failed to get price data")
            return
        
        # Check for new bar
        current_bar_time = bars[-1]['time']
        if current_bar_time != self.last_bar_time.get(symbol):
            self.last_bar_time[symbol] = current_bar_time
            logger.debug(f"[{symbol}] New bar: {current_bar_time}")
        
        # Analyze with strategy
        self.strategy.set_position(symbol, current_position)
        signal = self.strategy.analyze(symbol, bars, current_position)
        
        # Store signal for dashboard
        with self.dashboard_lock:
            self.dashboard_data['last_signals'][symbol] = {
                'action': signal.action.value,
                'reason': signal.reason,
                'strength': signal.strength,
                'timestamp': signal.timestamp
            }
            self.dashboard_data['ema_values'][symbol] = self.strategy.get_ema_values(symbol)
            
        # Update Market Status (Sequential / Thread-Safe)
        ema_vals = self.strategy.get_ema_values(symbol)
        if ema_vals:
            fast = ema_vals.get('fast_ema', [])
            slow = ema_vals.get('slow_ema', [])
            analysis = self.strategy.analyze_trend_momentum(fast, slow)
            
            # Get trading status from symbol info
            symbol_info = self.mt5.get_symbol_info(symbol)
            trade_allowed = symbol_info.get('trade_allowed', False) if symbol_info else False
            
            # Get per-symbol EMA settings
            sym_fast, sym_slow = self.strategy.get_symbol_ema_settings(symbol)
            
            # Get symbol-specific timeframe from config (Strict)
            try:
                sym_config = self.config['symbols']['settings'][symbol]
                sym_timeframe = sym_config['timeframe']
            except KeyError:
                sym_timeframe = "CONFIG_ERROR" # Will show in dashboard
            
            # Derive Category from Path
            path = symbol_info.get('path', '').lower()
            category = "Other"
            if "crypto" in path: category = "Crypto"
            elif "indices" in path or "index" in path: category = "Indices"
            elif "forex" in path: category = "Forex"
            elif "xau" in symbol.lower() or "xag" in symbol.lower(): category = "Metals"
            elif "metals" in path or "commod" in path or "energy" in path or "gold" in path or "silver" in path or "oil" in path: category = "Commodities"
            elif "stock" in path or "share" in path: category = "Stocks"
            
            with self.dashboard_lock:
                self.market_overview[symbol] = {
                    'category': category,
                    'price': bars[-1]['close'],
                    'trend': analysis['trend'],
                    'momentum': analysis['momentum'],
                    'diff': analysis.get('diff', 0.0),
                    'trade_allowed': trade_allowed,
                    'min_volume': symbol_info.get('volume_min', 0.01) if symbol_info else 0.01,
                    'volume_step': symbol_info.get('volume_step', 0.01) if symbol_info else 0.01,
                    'spread': symbol_info.get('spread', 0) if symbol_info else 0,
                    'fast_ema': sym_fast,
                    'slow_ema': sym_slow,
                    'timeframe': sym_timeframe,
                    'polling': 'OK',
                    'updated': datetime.now().isoformat()
                }
        
        # Execute if trading enabled and we have a trading signal
        # IMPORTANT: Check both trading_enabled AND frozen state
        # - trading_enabled=False: Complete stop (no new trades)
        # - trading_frozen=True: Freeze new trades (existing positions still run TP/SL)
        if not self.trading_enabled or self.paused:
            return

        if self.position_manager.is_trading_frozen():
            logger.debug(f"[{symbol}] Trading frozen - skipping signal. Reason: {self.position_manager.freeze_reason}")
            # Still manage open positions!
            if positions:
                 return self.position_manager.manage_position(positions[0])
            return {'sl': 0, 'tp': 0}
            
        # Manage existing position even if no signal or trading enabled
        mods = {'sl': 0, 'tp': 0}
        if positions:
            mods = self.position_manager.manage_position(positions[0])

        if signal.action == SignalType.BUY:
            result = self.position_manager.open_position(symbol, "LONG", signal.reason)
            self._execute_trade_entry(symbol, "LONG", result, signal.reason, timeframe)
        
        elif signal.action == SignalType.SELL:
            result = self.position_manager.open_position(symbol, "SHORT", signal.reason)
            self._execute_trade_entry(symbol, "SHORT", result, signal.reason, timeframe)
        
        elif signal.action in [SignalType.EXIT_LONG, SignalType.EXIT_SHORT]:
            if positions:
                pos = positions[0]
                entry_time_iso = pos.get('time')
                try:
                    entry_time = datetime.fromisoformat(entry_time_iso).timestamp()
                except:
                   entry_time = datetime.now().timestamp()
                
                current_time = datetime.now().timestamp()
                hold_seconds = int(current_time - entry_time)
                hold_time = f"{hold_seconds // 3600}h {(hold_seconds % 3600) // 60}m"
                
                result = self.position_manager.close_position(symbol, pos['ticket'], signal.reason)
                if result.success:
                    direction = "LONG" if signal.action == SignalType.EXIT_LONG else "SHORT"
                    
                    # Calculate pips
                    price_diff = abs(result.price - pos['price_open'])
                    symbol_info = self.mt5.get_symbol_info(symbol)
                    point = symbol_info.get('point', 0.00001) if symbol_info else 0.00001
                    pips = price_diff / point / 10 if 'JPY' not in symbol else price_diff / point
                    
                    # Get account info
                    account = self.mt5.get_account_summary()
                    total_pnl = account.get('balance', 0) - self.initial_balance if hasattr(self, 'initial_balance') else None
                    
                    self.telegram.notify_trade_exit(
                        symbol, direction, pos['volume'],
                        pos['price_open'], result.price, pos['profit'], signal.reason,
                        hold_time=hold_time,
                        pips=pips,
                        balance=account.get('balance'),
                        equity=account.get('equity'),
                        total_pnl=total_pnl
                    )

        return mods
    
    def run(self, dashboard_only: bool = False):
        """
        Main trading loop
        
        Args:
            dashboard_only: If True, only update dashboard data without trading
        """
        if not self.connect():
            logger.error("Failed to connect to MT5")
            return
        
        self.running = True
        self.start_time = datetime.now()
        
        logger.info("Trading engine started")
        logger.info(f"Trading enabled: {self.trading_enabled}")
        logger.info(f"Direction: {self.direction}")
        logger.info(f"Symbols: {self.enabled_symbols}")
        
        try:
            while self.running:
                # Cycle Stats Initialization
                cycle_start = datetime.now()
                cycle_stats = {
                    'symbols_scanned': 0,
                    'markets_open': 0,
                    'markets_closed': 0,
                    'sl_modifications': 0,
                    'tp_modifications': 0,
                    'bull_count': 0,
                    'bear_count': 0,
                    'wait_count': 0,
                    'open_positions': 0,
                    'errors': 0,
                    'last_error': None,
                    'duration_ms': 0
                }
                
                # Update dashboard data
                self._update_dashboard_data()
                
                # Process each enabled symbol
                if not dashboard_only:
                    # Count open positions once
                    cycle_stats['open_positions'] = len(self.dashboard_data.get('positions', []))

                    for symbol in self.enabled_symbols:
                        try:
                            # Check market status
                            info = self.mt5.get_symbol_info(symbol)
                            if info and info.get('trade_allowed'):
                                cycle_stats['markets_open'] += 1
                            else:
                                cycle_stats['markets_closed'] += 1
                                
                            # Track modifications by getting return value
                            mods = self._process_symbol(symbol)
                            if isinstance(mods, dict):
                                cycle_stats['sl_modifications'] += mods.get('sl', 0)
                                cycle_stats['tp_modifications'] += mods.get('tp', 0)
                            
                            cycle_stats['symbols_scanned'] += 1
                            
                            # Track Trend from Market Overview
                            with self.dashboard_lock:
                                trend = self.market_overview.get(symbol, {}).get('trend', 'WAIT').upper()
                            
                            if 'BULL' in trend: cycle_stats['bull_count'] += 1
                            elif 'BEAR' in trend: cycle_stats['bear_count'] += 1
                            else: cycle_stats['wait_count'] += 1
                            
                        except Exception as e:
                            logger.error(f"Error processing {symbol}: {e}")
                            cycle_stats['errors'] += 1
                            cycle_stats['last_error'] = f"[{symbol}] {str(e)}"
                            self.telegram.notify_error("Processing Error", str(e), symbol)
                            
                # Calculate duration
                cycle_end = datetime.now()
                duration = (cycle_end - cycle_start).total_seconds() * 1000
                cycle_stats['duration_ms'] = int(duration)
                
                # Update dashboard with last cycle stats
                with self.dashboard_lock:
                    self.dashboard_data['last_cycle_stats'] = cycle_stats
                
                # Wait before next cycle
                time.sleep(self.price_refresh_ms / 1000)
        
        except KeyboardInterrupt:
            logger.info("Shutdown requested by user")
        
        finally:
            self.running = False
            self.disconnect()
            logger.info("Trading engine stopped")
    
    def stop(self):
        """Stop the trading engine"""
        self.running = False
    
    def pause(self):
        """Pause trading (but keep data updating)"""
        self.paused = True
        logger.info("Trading paused")
    
    def resume(self):
        """Resume trading"""
        self.paused = False
        logger.info("Trading resumed")
    
    def get_dashboard_data(self) -> Dict:
        """Get current dashboard data (thread-safe)"""
        with self.dashboard_lock:
            return dict(self.dashboard_data)


def main():
    """Main entry point"""
    print("="*60)
    print(f"   EMAX Trading Engine [{INSTANCE_ID}]")
    print("   EMA Crossover Strategy for MT5")
    print("="*60)
    
    # Import dashboard
    from dashboard.web_dashboard import WebDashboard
    
    # Create engine
    engine = TradingEngine()
    
    # Load dashboard port from config
    dashboard_port = engine.config.get('dashboard', {}).get('web_port', 8080)
    
    # Create and start dashboard
    dashboard = WebDashboard(trading_engine=engine, port=dashboard_port)
    dashboard.start(threaded=True)
    
    print(f"\n[Dashboard] Running at: http://localhost:{dashboard_port}")
    print("="*60)
    
    # Handle shutdown signals
    def signal_handler(sig, frame):
        print("\nShutting down...")
        engine.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start engine
    engine.run()


if __name__ == "__main__":
    main()

