"""
================================================================================
MT5 CONNECTOR MODULE - EMAX Trading Engine
================================================================================

PURPOSE:
    This module provides a robust connection layer to MetaTrader 5 running under
    Wine on Linux. It handles all communication with the MT5 terminal including
    initialization, account info, price data, order management, and position
    tracking.

INPUTS:
    - Configuration: Uses constants.py and trading_config.json
    - System: Requires MT5 terminal running under Wine

OUTPUTS:
    - Connection to MT5 terminal
    - Real-time price data streams
    - Account balance and margin updates
    - Trade execution (Orders/Positions)

CONTEXT:
    This is the foundational infrastructure layer.
    Imported by:
    - main.py
    - core/position_manager.py

VERSION HISTORY:
    1.1.0 (2026-01-28) - Added constants.py integration
    1.0.0 (2026-01-22) - Initial release

AUTHOR: EMAX Trading Engine
================================================================================
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.constants import DEFAULTS, LIMITS


# Configure logging - Delegated to main application
logger = logging.getLogger('MT5Connector')

# Import MetaTrader5 - must be run under Wine Python
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 module not available. Running in simulation mode.")


class MT5Connector:
    """
    MetaTrader 5 Connection Manager
    
    Handles all communication with MT5 terminal including:
    - Connection management
    - Account information
    - Price data retrieval
    - Order execution
    - Position tracking
    """
    
    # Timeframe mapping
    TIMEFRAMES = {
        'M1': 1,    # mt5.TIMEFRAME_M1
        'M5': 5,    # mt5.TIMEFRAME_M5
        'M15': 15,  # mt5.TIMEFRAME_M15
        'M30': 30,  # mt5.TIMEFRAME_M30
        'H1': 60,   # mt5.TIMEFRAME_H1
        'H4': 240,  # mt5.TIMEFRAME_H4
        'D1': 1440, # mt5.TIMEFRAME_D1
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize MT5 Connector
        
        Args:
            config_path: Path to trading_config.json. If None, uses default location.
        """
        self.connected = False
        self.account_info = None
        self.terminal_info = None
        self.is_demo = None
        self.last_error = None
        self.connection_time = None
        self.reconnect_attempts = 0
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.server_time_offset = 0  # Difference: System Time - Server Time
        
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'trading_config.json'
        self.config = self._load_config(config_path)
        
        logger.info("MT5Connector initialized")
    
    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Configuration loaded from {config_path}")
            return config
        except FileNotFoundError:
            logger.warning(f"Config file not found at {config_path}, using defaults")
            return {"account": {"demo_only": True}}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return {"account": {"demo_only": True}}
    
    def connect(self, path: Optional[str] = None) -> bool:
        """
        Connect to MetaTrader 5 terminal
        
        Args:
            path: Optional path to MT5 terminal executable
            
        Returns:
            bool: True if connection successful
        """
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 module not available")
            self.last_error = "MT5 module not available"
            return False
        
        logger.info("Connecting to MetaTrader 5...")
        
        # Initialize MT5
        init_params = {}
        if path:
            init_params['path'] = path
            
        if not mt5.initialize(**init_params):
            error = mt5.last_error()
            logger.error(f"Failed to initialize MT5: {error}")
            self.last_error = str(error)
            return False
        
        # Get terminal info
        self.terminal_info = mt5.terminal_info()
        if not self.terminal_info:
            logger.error("Failed to get terminal info")
            self.last_error = "Terminal info unavailable"
            mt5.shutdown()
            return False
        
        logger.info(f"Connected to: {self.terminal_info.name}")
        logger.info(f"Company: {self.terminal_info.company}")
        
        # Get account info
        self.account_info = mt5.account_info()
        if not self.account_info:
            logger.error("Failed to get account info")
            self.last_error = "Account info unavailable"
            mt5.shutdown()
            return False
        
        # Check if demo account
        self.is_demo = self.account_info.trade_mode == 0  # 0 = demo, 1 = contest, 2 = real
        
        # Safety check: demo only mode
        if self.config.get('account', {}).get('demo_only', True) and not self.is_demo:
            logger.error("SAFETY: Real account detected but demo_only mode is enabled!")
            self.last_error = "Real account blocked - demo_only mode"
            mt5.shutdown()
            return False
        
        self.connected = True
        self.connection_time = datetime.now()
        self.reconnect_attempts = 0
        
        logger.info(f"Account: {self.account_info.login} ({'DEMO' if self.is_demo else 'REAL'})")
        logger.info(f"Server: {self.account_info.server}")
        logger.info(f"Balance: ${self.account_info.balance:.2f}")
        
        # Calculate server time offset
        self._calculate_server_offset()
        
        return True

    def _calculate_server_offset(self):
        """
        Calculate time offset between local system and MT5 server.
        Positive offset means System Time is ahead of Server Time.
        """
        # List of liquid symbols to check for latest tick
        ref_symbols = ['BTCUSD', 'EURUSD', 'GBPUSD', 'XAUUSD', 'SP500', 'USTEC']
        max_tick_time = 0
        
        for sym in ref_symbols:
            # Ensure symbol is selected
            if not mt5.symbol_select(sym, True):
                continue
                
            tick = mt5.symbol_info_tick(sym)
            if tick and tick.time > max_tick_time:
                max_tick_time = tick.time
        
        if max_tick_time > 0:
            # We assume the "latest" tick is close to "now" in Server Time
            # So Offset = System_Now - Server_Now (approx max_tick_time)
            self.server_time_offset = datetime.now().timestamp() - max_tick_time
            logger.info(f"Server Time Offset calculated: {self.server_time_offset:.2f} seconds")
        else:
            logger.warning("Could not calculate server time offset (no live ticks found)")
            self.server_time_offset = 0
    
    def disconnect(self):
        """Disconnect from MetaTrader 5"""
        if self.connected and MT5_AVAILABLE:
            mt5.shutdown()
            self.connected = False
            logger.info("Disconnected from MetaTrader 5")
    
    def ensure_connected(self) -> bool:
        """Ensure connection is active, reconnect if needed"""
        if not self.connected:
            return self.connect()
        
        # Check if connection is still valid
        if MT5_AVAILABLE:
            info = mt5.terminal_info()
            if info is None:
                logger.warning("Connection lost, attempting reconnect...")
                self.connected = False
                return self.connect()
        
        return True
    
    def get_account_summary(self) -> Dict:
        """
        Get account summary information
        
        Returns:
            Dict with account details
        """
        if not self.ensure_connected():
            return {"error": self.last_error}
        
        account = mt5.account_info()
        if not account:
            return {"error": "Failed to get account info"}
        
        return {
            "login": account.login,
            "server": account.server,
            "name": account.name,
            "currency": account.currency,
            "balance": account.balance,
            "equity": account.equity,
            "margin": account.margin,
            "margin_free": account.margin_free,
            "profit": account.profit,
            "leverage": account.leverage,
            "is_demo": self.is_demo,
            "timestamp": datetime.now().isoformat()
        }
    
    def is_market_open(self, symbol: str) -> bool:
        """
        Check if market is currently open for a symbol.
        Uses a heuristic based on data staleness since native session API is missing.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            bool: True if market appears open
        """
        info = mt5.symbol_info(symbol)
        if not info:
            return False
            
        if info.trade_mode != 4:  # 4 = SYMBOL_TRADE_MODE_FULL
            return False
            
        # Check staleness
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False
            
        # If last tick is older than configured staleness (default 5 mins), assume market is closed
        # This handles weekends/holidays where trade_mode stays FULL
        # We adjust "now" by the server offset to compare apples to apples
        server_now = datetime.now().timestamp() - self.server_time_offset
        staleness = server_now - tick.time
        
        limit = DEFAULTS.get('MARKET_STALENESS_SEC', 300)
        
        # Debug only if very stale but claimed open
        if staleness > limit and info.trade_mode == 4:
            # logger.debug(f"{symbol} stale: {staleness:.1f}s (Limit: {limit}s)")
            pass
            
        return staleness < limit

    def _get_filling_mode(self, symbol: str) -> int:
        """
        Get the correct filling mode for a symbol.
        Checks symbol info flags:
        1 (SYMBOL_FILLING_FOK) -> ORDER_FILLING_FOK (0)
        2 (SYMBOL_FILLING_IOC) -> ORDER_FILLING_IOC (1)
        
        Returns:
            int: MT5 filling mode constant
        """
        try:
            # Use raw mt5 call to avoid wrapper overhead if needed, 
            # but symbol_info is cached by MT5 likely.
            info = mt5.symbol_info(symbol)
            if not info:
                return mt5.ORDER_FILLING_FOK # Default
            
            filling_mode = info.filling_mode
            
            # Priority: FOK > IOC > RETURN
            # Note: The flags are 1 (FOK) and 2 (IOC). 
            # The order filling constants are 0 (FOK), 1 (IOC), 2 (RETURN).
            
            # If FOK (1) is supported
            if filling_mode & 1:
                return mt5.ORDER_FILLING_FOK
                
            # If IOC (2) is supported
            if filling_mode & 2:
                return mt5.ORDER_FILLING_IOC
                
            # Fallback
            return mt5.ORDER_FILLING_RETURN
            
        except Exception as e:
            logger.error(f"Error determining filling mode for {symbol}: {e}")
            return mt5.ORDER_FILLING_FOK


    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Get detailed symbol information
        
        Args:
            symbol: Trading symbol name
            
        Returns:
            Dict with symbol details or None
        """
        if not self.ensure_connected():
            return None
        
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.warning(f"Symbol {symbol} not found")
            return None
        
        # Enable symbol for trading if not visible
        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                logger.warning(f"Failed to enable symbol {symbol}")
        
        tick = mt5.symbol_info_tick(symbol)
        
        return {
            "name": info.name,
            "description": info.description,
            "currency_base": info.currency_base,
            "currency_profit": info.currency_profit,
            "digits": info.digits,
            "point": info.point,
            "spread": info.spread,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_contract_size": info.trade_contract_size,
            "margin_initial": info.margin_initial,
            "trade_mode": info.trade_mode,  # 0=disabled, 4=full
            "trade_allowed": self.is_market_open(symbol),
            "bid": tick.bid if tick else None,
            "ask": tick.ask if tick else None,
            "path": info.path,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_current_price(self, symbol: str) -> Optional[Dict]:
        """
        Get current bid/ask price
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dict with price info or None
        """
        if not self.ensure_connected():
            return None
        
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.warning(f"Failed to get price for {symbol}")
            return None
        
        return {
            "symbol": symbol,
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": tick.ask - tick.bid,
            "time": datetime.fromtimestamp(tick.time).isoformat()
        }
    
    def get_rates(self, symbol: str, timeframe: str, count: int = 100) -> Optional[List[Dict]]:
        """
        Get historical OHLCV data
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe string (M1, M5, M15, H1, etc.)
            count: Number of bars to retrieve
            
        Returns:
            List of OHLCV dicts or None
        """
        if not self.ensure_connected():
            return None
        
        # Map timeframe string to MT5 constant
        tf_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
        }
        
        tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_M5)
        
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None:
            logger.warning(f"Failed to get rates for {symbol}")
            return None
        
        result = []
        for rate in rates:
            result.append({
                "time": datetime.fromtimestamp(rate['time']).isoformat(),
                "open": rate['open'],
                "high": rate['high'],
                "low": rate['low'],
                "close": rate['close'],
                "volume": rate['tick_volume']
            })
        
        return result

    def get_rates_range(self, symbol: str, timeframe: str, date_from: datetime, date_to: datetime) -> Optional[List[Dict]]:
        """
        Get historical OHLCV data for a specific date range
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe string (M1, M5, M15, H1, etc.)
            date_from: Start date
            date_to: End date
            
        Returns:
            List of OHLCV dicts or None
        """
        if not self.ensure_connected():
            return None
        
        # Map timeframe string to MT5 constant
        tf_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
        }
        
        tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_M5)
        
        rates = mt5.copy_rates_range(symbol, tf, date_from, date_to)
        if rates is None:
            logger.warning(f"Failed to get rates range for {symbol}")
            return None
        
        result = []
        for rate in rates:
            result.append({
                "time": datetime.fromtimestamp(rate['time']).isoformat(),
                "open": rate['open'],
                "high": rate['high'],
                "low": rate['low'],
                "close": rate['close'],
                "volume": rate['tick_volume']
            })
        
        return result
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get open positions
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of position dicts
        """
        if not self.ensure_connected():
            return []
        
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        
        if positions is None or len(positions) == 0:
            return []
        
        result = []
        for pos in positions:
            result.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": "BUY" if pos.type == 0 else "SELL",
                "volume": pos.volume,
                "price_open": pos.price_open,
                "price_current": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "swap": pos.swap,
                "time": datetime.fromtimestamp(pos.time).isoformat(),
                "magic": pos.magic,
                "comment": pos.comment
            })
        
        return result
    
    def get_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get pending orders
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of order dicts
        """
        if not self.ensure_connected():
            return []
        
        if symbol:
            orders = mt5.orders_get(symbol=symbol)
        else:
            orders = mt5.orders_get()
        
        if orders is None or len(orders) == 0:
            return []
        
        result = []
        for order in orders:
            result.append({
                "ticket": order.ticket,
                "symbol": order.symbol,
                "type": order.type,
                "volume": order.volume_current,
                "price_open": order.price_open,
                "sl": order.sl,
                "tp": order.tp,
                "time_setup": datetime.fromtimestamp(order.time_setup).isoformat(),
                "state": order.state,
                "magic": order.magic,
                "comment": order.comment
            })
        
        return result
    
    def get_history_orders(self, days: int = 1) -> List[Dict]:
        """
        Get historical orders from the last N days
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of historical order dicts
        """
        if not self.ensure_connected():
            return []
        
        from_date = datetime.now() - timedelta(days=days)
        to_date = datetime.now()
        
        history = mt5.history_orders_get(from_date, to_date)
        
        if history is None or len(history) == 0:
            return []
        
        result = []
        for order in history:
            result.append({
                "ticket": order.ticket,
                "symbol": order.symbol,
                "type": order.type,
                "volume": order.volume_current,
                "price_open": order.price_open,
                "price_current": order.price_current,
                "sl": order.sl,
                "tp": order.tp,
                "time_setup": datetime.fromtimestamp(order.time_setup).isoformat(),
                "time_done": datetime.fromtimestamp(order.time_done).isoformat() if order.time_done else None,
                "state": order.state,
                "profit": getattr(order, 'profit', 0),
                "magic": order.magic,
                "comment": order.comment
            })
        
        return result
    
    def get_history_deals(self, days: int = 1, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> List[Dict]:
        """
        Get historical deals (executed trades)
        
        Args:
            days: Number of days to look back (if from_date not specified)
            from_date: Start date (overrides days)
            to_date: End date (default: now)
            
        Returns:
            List of deal dicts with PnL
        """
        if not self.ensure_connected():
            return []
        
        if from_date is None:
            from_date = datetime.now() - timedelta(days=days)
        
        if to_date is None:
            to_date = datetime.now()
        
        deals = mt5.history_deals_get(from_date, to_date)
        
        if deals is None or len(deals) == 0:
            return []
        
        result = []
        for deal in deals:
            result.append({
                "ticket": deal.ticket,
                "order": deal.order,
                "symbol": deal.symbol,
                "type": deal.type,
                "entry": deal.entry,  # 0=in, 1=out, 2=inout, 3=out_by
                "volume": deal.volume,
                "price": deal.price,
                "profit": deal.profit,
                "swap": deal.swap,
                "commission": deal.commission,
                "fee": deal.fee,
                "time": datetime.fromtimestamp(deal.time).isoformat(),
                "magic": deal.magic,
                "comment": deal.comment
            })
        
        return result
    
    def place_order(self, symbol: str, order_type: str, volume: float,
                    price: Optional[float] = None, sl: Optional[float] = None,
                    tp: Optional[float] = None, magic: int = 12345,
                    comment: str = "EMAX") -> Dict:
        """
        Place a market or pending order
        
        Args:
            symbol: Trading symbol
            order_type: "BUY" or "SELL"
            volume: Lot size
            price: Price for pending orders (None for market)
            sl: Stop loss price
            tp: Take profit price
            magic: Magic number for identification
            comment: Order comment
            
        Returns:
            Dict with result info
        """
        if not self.ensure_connected():
            return {"success": False, "error": self.last_error}
        
        # Safety check
        if self.config.get('account', {}).get('demo_only', True) and not self.is_demo:
            return {"success": False, "error": "Real account blocked - demo_only mode"}
        
        # Get symbol info
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return {"success": False, "error": f"Symbol {symbol} not found"}
        
        # Enable symbol if needed
        if not symbol_info.visible:
            mt5.symbol_select(symbol, True)
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"success": False, "error": "Failed to get price"}
        
        # Determine order type and price
        if order_type.upper() == "BUY":
            mt5_order_type = mt5.ORDER_TYPE_BUY
            execution_price = tick.ask
        else:
            mt5_order_type = mt5.ORDER_TYPE_SELL
            execution_price = tick.bid
        
        # Build request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_order_type,
            "price": execution_price,
            "deviation": 20,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        if sl:
            request["sl"] = sl
        if tp:
            request["tp"] = tp
        
        # Determine filling mode dynamically
        filling_mode = self._get_filling_mode(symbol)
        request["type_filling"] = filling_mode
        
        # Send order
        result = mt5.order_send(request)
        
        # Fallback retry only if the specific mode failed with 10030
        if result is not None and result.retcode == 10030:
            logger.warning(f"Calculated filling mode {filling_mode} unsupported, trying alternatives")
            # Try others
            for mode in [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]:
                if mode == filling_mode: continue
                request["type_filling"] = mode
                result = mt5.order_send(request)
                if result.retcode != 10030:
                    break
        
        # Handle None result (MT5 rejected silently)
        if result is None:
            error_info = mt5.last_error()
            logger.error(f"Order rejected (None result): {error_info}")
            return {
                "success": False,
                "error": f"MT5 rejected order: {error_info}",
                "retcode": -1
            }
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Order placed: {order_type} {volume} {symbol} @ {execution_price}")
            return {
                "success": True,
                "ticket": result.order,
                "symbol": symbol,
                "type": order_type,
                "volume": volume,
                "price": execution_price,
                "sl": sl,
                "tp": tp
            }
        else:
            logger.error(f"Order failed: {result.comment} (retcode: {result.retcode})")
            return {
                "success": False,
                "error": result.comment,
                "retcode": result.retcode
            }
    
    def close_position(self, ticket: int, magic: Optional[int] = None) -> Dict:
        """
        Close a specific position by ticket
        
        Args:
            ticket: Position ticket number
            magic: Optional magic number override
            
        Returns:
            Dict with result info
        """
        if not self.ensure_connected():
            return {"success": False, "error": self.last_error}
        
        # Get position info
        position = mt5.positions_get(ticket=ticket)
        if position is None or len(position) == 0:
            return {"success": False, "error": f"Position {ticket} not found"}
        
        pos = position[0]
        symbol = pos.symbol
        volume = pos.volume
        pos_type = pos.type
        
        # Determine close type
        close_type = mt5.ORDER_TYPE_SELL if pos_type == 0 else mt5.ORDER_TYPE_BUY
        
        # Get price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"success": False, "error": "Failed to get price"}
        
        price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
        
        # Use provided magic or fallback to position magic (safer than default)
        magic_val = magic if magic is not None else pos.magic
        
        # Build close request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": magic_val,
            "comment": "Close by EMAX",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # Determine filling mode dynamically
        filling_mode = self._get_filling_mode(symbol)
        request["type_filling"] = filling_mode
        
        # Send order
        result = mt5.order_send(request)
        
        # Determine filling mode based on symbol info or try default
        if result is not None and result.retcode == 10030:
            logger.warning(f"Calculated closing filling mode {filling_mode} unsupported, trying alternatives")
            # Try others
            for mode in [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]:
                if mode == filling_mode: continue
                request["type_filling"] = mode
                result = mt5.order_send(request)
                if result.retcode != 10030:
                    break
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Position {ticket} closed @ {price}")
            return {"success": True, "ticket": ticket, "close_price": price}
        else:
            logger.error(f"Failed to close position {ticket}: {result.comment}")
            return {"success": False, "error": result.comment, "retcode": result.retcode}
    
    def close_all_positions(self, symbol: Optional[str] = None, magic: Optional[int] = None) -> Dict:
        """
        Close all open positions (panic button)
        
        Args:
            symbol: Optional symbol filter
            magic: Optional magic number filter (defaults to DEFAULT_MAGIC_NUMBER if None)
            
        Returns:
            Dict with summary
        """
        # Resolving Magic Number
        target_magic = magic if magic is not None else DEFAULTS.get("DEFAULT_MAGIC_NUMBER", 123456)
        
        positions = self.get_positions(symbol)
        
        if not positions:
            return {"success": True, "closed": 0, "message": "No positions to close"}
        
        # Filter by magic number
        positions = [p for p in positions if p.magic == target_magic]
        
        if not positions:
             return {"success": True, "closed": 0, "message": f"No positions found for Magic {target_magic}"}
        
        closed = 0
        failed = 0
        
        for pos in positions:
            result = self.close_position(pos['ticket'], magic=target_magic)
            if result['success']:
                closed += 1
            else:
                failed += 1
        
        return {
            "success": failed == 0,
            "closed": closed,
            "failed": failed,
            "total": len(positions)
        }
    
    def get_connection_status(self) -> Dict:
        """
        Get detailed connection status
        
        Returns:
            Dict with connection details
        """
        if not MT5_AVAILABLE:
            return {
                "connected": False,
                "error": "MT5 module not available",
                "is_demo": None
            }
        
        if not self.connected:
            return {
                "connected": False,
                "error": self.last_error,
                "is_demo": None
            }
        
        # Verify connection is still active
        info = mt5.terminal_info()
        if info is None:
            self.connected = False
            return {
                "connected": False,
                "error": "Connection lost",
                "is_demo": self.is_demo
            }
        
        account = mt5.account_info()
        
        return {
            "connected": True,
            "terminal": info.name,
            "company": info.company,
            "account": account.login if account else None,
            "server": account.server if account else None,
            "is_demo": self.is_demo,
            "connection_time": self.connection_time.isoformat() if self.connection_time else None,
            "uptime_seconds": (datetime.now() - self.connection_time).seconds if self.connection_time else 0
        }


# Export for easy testing
def test_connection():
    """Quick test of MT5 connection"""
    connector = MT5Connector()
    
    if connector.connect():
        print("\n" + "="*50)
        print("CONNECTION TEST SUCCESSFUL")
        print("="*50)
        
        status = connector.get_connection_status()
        for key, value in status.items():
            print(f"  {key}: {value}")
        
        print("\nAccount Summary:")
        summary = connector.get_account_summary()
        for key, value in summary.items():
            print(f"  {key}: {value}")
        
        connector.disconnect()
    else:
        print(f"Connection failed: {connector.last_error}")


if __name__ == "__main__":
    test_connection()
