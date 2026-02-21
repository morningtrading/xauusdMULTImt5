"""
================================================================================
POSITION MANAGER MODULE - EMAX Trading Engine
================================================================================

PURPOSE:
    Manages position sizing, entry/exit execution, stop loss placement, and
    risk management. Acts as the bridge between strategy signals and MT5 order
    execution.

INPUTS:
    - Signals from Strategy
    - Market Data from MT5Connector
    - Configuration (risk limits, position sizing rules)

OUTPUTS:
    - Validated trade requests to MT5Connector
    - Risk status updates (daily loss, margin usage)
    - Trade history logs

CONTEXT:
    Middle layer between Strategy and Connector.
    Enforces risk rules defined in constants.py and config validation.

VERSION HISTORY:
    1.1.0 (2026-01-28) - Added constants.py integration and robust headers
    1.0.0 (2026-01-22) - Initial release

AUTHOR: EMAX Trading Engine
================================================================================
"""

import json
import logging
import sys
import os
import csv
from datetime import datetime, time as dtime
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.constants import DEFAULTS, LIMITS


logger = logging.getLogger('PositionManager')


@dataclass
class TradeResult:
    """Result of a trade execution"""
    success: bool
    action: str  # "OPEN_LONG", "OPEN_SHORT", "CLOSE_LONG", "CLOSE_SHORT"
    symbol: str
    volume: float
    price: float
    sl: Optional[float]
    tp: Optional[float]
    ticket: Optional[int]
    error: Optional[str]
    margin_used: float
    timestamp: str


class PositionManager:
    """
    Position Manager for trade execution and risk management
    
    Handles:
    - Position sizing based on margin limits
    - Stop loss calculation (fixed or ATR-based)
    - Trade execution through MT5Connector
    - Session and spread filtering
    - Daily loss tracking
    """
    
    def __init__(self, mt5_connector, config_path: Optional[str] = None):
        """
        Initialize Position Manager
        
        Args:
            mt5_connector: Instance of MT5Connector
            config_path: Path to trading_config.json
        """
        self.mt5 = mt5_connector
        
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'trading_config.json'
        self.config = self._load_config(config_path)
        
        # Extract config values
        account_config = self.config.get('account', {})
        self.max_margin = account_config.get('max_margin_per_trade_usd', 10.0)
        self.max_daily_loss_percent = account_config.get('max_daily_loss_percent', 75.0)
        self.leverage = account_config.get('default_leverage', 1000)
        self.position_size_type = account_config.get('position_size_type', 'margin')
        self.fixed_volume = account_config.get('fixed_volume', 0.01)
        self.magic_number = self.config.get('magic_number', 123456)
        
        # Stop loss config
        sl_config = self.config.get('stop_loss', {})
        self.sl_type = sl_config.get('type', 'fixed')  # fixed or atr
        self.sl_fixed_percent = sl_config.get('fixed_percent_of_margin', 50.0)
        self.sl_atr_multiplier = sl_config.get('atr_multiplier', 1.5)
        self.sl_atr_period = sl_config.get('atr_period', 14)
        
        # Trailing SL config
        tsl_config = self.config.get('trailing_sl', {})
        self.tsl_enabled = tsl_config.get('enabled', True)
        self.tsl_activation = tsl_config.get('activation_points', 200)
        self.tsl_distance = tsl_config.get('distance_points', 50)
        self.tsl_step = tsl_config.get('step_points', 10)
        
        # Session filter config
        session_config = self.config.get('session_filter', {})
        self.session_filter_enabled = session_config.get('enabled', True)
        self.overlap_start = session_config.get('overlap_start_utc', '13:30')
        self.overlap_end = session_config.get('overlap_end_utc', '16:30')
        self.london_open = session_config.get('london_open_utc', '08:00')
        self.ny_close = session_config.get('ny_close_utc', '20:00')
        
        # Symbol settings
        self.symbol_settings = self.config.get('symbols', {}).get('settings', {})
        
        # State tracking
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.starting_balance = None
        self.last_reset_date = None
        self.trade_history: List[TradeResult] = []

        # Freeze trading state (for news events, etc.)
        # When frozen: NO new trades, but existing positions continue (TP/SL active)
        self.trading_frozen = False
        self.freeze_reason = None
        self.freeze_timestamp = None


        # Trade logging setup
        self.log_dir = Path(__file__).parent.parent / 'data'
        self.trade_log_path = self.log_dir / 'trade_history.csv'
        self._init_trade_log()

        logger.info(f"PositionManager initialized: max_margin=${self.max_margin}, SL_type={self.sl_type}")
    
    def _init_trade_log(self):
        """Initialize trade log CSV if not exists"""
        try:
            self.log_dir.mkdir(exist_ok=True)
            
            if not self.trade_log_path.exists():
                with open(self.trade_log_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'Timestamp', 'Ticket', 'Symbol', 'Action', 'Volume', 
                        'Price', 'SL', 'TP', 'Profit', 'Swap', 'Commission', 
                        'Margin_Used', 'Balance', 'Equity', 'Comment'
                    ])
                logger.info(f"Created new trade log at {self.trade_log_path}")
        except Exception as e:
            logger.error(f"Failed to init trade log: {e}")

    def _log_trade_event(self, trade_result: TradeResult, account_info: Optional[Dict] = None, profit: float = 0.0):
        """
        Log trade event to CSV
        
        Args:
            trade_result: TradeResult object
            account_info: Optional account info dict
            profit: Realized profit (for CLOSE events)
        """
        try:
            timestamp = datetime.now().isoformat()
            
            balance = account_info.get('balance', 0) if account_info else 0
            equity = account_info.get('equity', 0) if account_info else 0
            
            # Default values for missing fields
            # profit is passed as argument
            swap = 0.0
            commission = 0.0
            
            # If closing, profit might be available via history check, but here we log the action immediately.
            # Real profit comes from history deals, but we can log estimated or just the event.
            # For OPEN events, profit is 0.
            
            row = [
                timestamp,
                trade_result.ticket,
                trade_result.symbol,
                trade_result.action,
                trade_result.volume,
                trade_result.price,
                trade_result.sl,
                trade_result.tp,
                profit, # Realized profit passed explicitly
                swap,   # swap
                commission, # commission
                trade_result.margin_used,
                balance,
                equity,
                trade_result.error or "Success"
            ]
            
            with open(self.trade_log_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(row)
                
        except Exception as e:
            logger.error(f"Failed to log trade event: {e}")
    
    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}, using defaults")
            return {}
    
    def _reset_daily_stats(self):
        """Reset daily statistics at start of new trading day"""
        today = datetime.now().date()
        if self.last_reset_date != today:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.last_reset_date = today
            
            # Get starting balance
            account = self.mt5.get_account_summary()
            if 'balance' in account:
                self.starting_balance = account['balance']
            
            logger.info(f"Daily stats reset. Starting balance: ${self.starting_balance:.2f}")
    
    def check_session_filter(self) -> Tuple[bool, str]:
        """
        Check if current time is within trading session
        
        Returns:
            Tuple of (is_allowed, reason)
        """
        if not self.session_filter_enabled:
            return True, "Session filter disabled"
        
        now_utc = datetime.utcnow().time()
        
        # Parse session times
        london_open = dtime(*map(int, self.london_open.split(':')))
        ny_close = dtime(*map(int, self.ny_close.split(':')))
        overlap_start = dtime(*map(int, self.overlap_start.split(':')))
        overlap_end = dtime(*map(int, self.overlap_end.split(':')))
        
        # Check if within main session (London open to NY close)
        if london_open <= now_utc <= ny_close:
            # Check if we're in overlap (best time)
            if overlap_start <= now_utc <= overlap_end:
                return True, "Within London/NY overlap - optimal"
            return True, "Within main trading session"
        
        return False, f"Outside trading session ({self.london_open}-{self.ny_close} UTC)"
    
    def check_spread(self, symbol: str) -> Tuple[bool, float]:
        """
        Check if spread is acceptable for trading
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Tuple of (is_acceptable, current_spread_points)
        """
        symbol_config = self.symbol_settings.get(symbol, {})
        max_spread = symbol_config.get('max_spread_points', 100)
        
        # Get symbol info
        info = self.mt5.get_symbol_info(symbol)
        if info is None:
            return False, 0
        
        current_spread = info.get('spread', 0)
        
        if current_spread > max_spread:
            logger.warning(f"[{symbol}] Spread too wide: {current_spread} > {max_spread}")
            return False, current_spread
        
        return True, current_spread
    
    def check_daily_loss_limit(self) -> Tuple[bool, float]:
        """
        Check if daily loss limit has been reached
        
        Returns:
            Tuple of (can_trade, current_loss_percent)
        """
        self._reset_daily_stats()
        
        if self.starting_balance is None or self.starting_balance == 0:
            return True, 0.0
        
        account = self.mt5.get_account_summary()
        if 'balance' not in account:
            return True, 0.0
        
        current_balance = account['balance']
        loss_percent = ((self.starting_balance - current_balance) / self.starting_balance) * 100
        
        if loss_percent >= self.max_daily_loss_percent:
            logger.error(f"Daily loss limit reached: {loss_percent:.1f}% >= {self.max_daily_loss_percent}%")
            return False, loss_percent
        
        return True, loss_percent
    
    def calculate_position_size(self, symbol: str) -> Tuple[float, Dict]:
        """
        Calculate position size based on margin limit
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Tuple of (volume, calculation_details)
        """
        info = self.mt5.get_symbol_info(symbol)
        if info is None:
            return 0.0, {"error": "Symbol info unavailable"}
        
        # Get account info
        account = self.mt5.get_account_summary()
        if 'error' in account:
            return 0.0, {"error": account['error']}
        
        current_price = info.get('bid', 0)
        if current_price == 0:
            return 0.0, {"error": "Price unavailable"}
        
        contract_size = info.get('trade_contract_size', 1)
        min_volume = info.get('volume_min', 0.01)
        volume_step = info.get('volume_step', 0.01)
        leverage = account.get('leverage', self.leverage)
        
        # Calculate margin required for min lot
        # Margin = (Contract Size * Lot Size * Price) / Leverage
        margin_per_lot = (contract_size * 1.0 * current_price) / leverage
        
        # Check position sizing type
        if self.position_size_type == "fixed":
            # Use fixed volume
            volume = self.fixed_volume
            # Round to volume step to be safe
            volume = round(volume / volume_step) * volume_step
        else:
            # MARGIN BASED SIZING
            if margin_per_lot == 0:
                return min_volume, {"error": "Zero margin calculation"}
            
            # Calculate max volume based on margin limit
            max_volume = self.max_margin / margin_per_lot
            
            # Round to volume step
            volume = max(min_volume, round(max_volume / volume_step) * volume_step)
        
        # CRITICAL: Ensure volume is at least MT5's minimum and properly rounded
        volume = max(volume, min_volume)
        
        # Round to step with precision protection
        if volume_step > 0:
            volume = round(volume / volume_step) * volume_step
            # Remove potential floating point artifacts (e.g. 0.300000000004)
            decimals = 0
            if volume_step < 1:
                str_step = str(float(volume_step))
                if '.' in str_step:
                    decimals = len(str_step.split('.')[1])
            volume = round(volume, decimals)
        
        # Safety floor check
        if volume < min_volume:
            volume = min_volume
            logger.warning(f"[{symbol}] Volume adjusted to min_volume: {min_volume}")
        
        details = {
            "calculated_volume": volume,
            "margin_per_lot": margin_per_lot,
            "max_margin": self.max_margin,
            "leverage": leverage,
            "contract_size": contract_size,
            "current_price": current_price,
            "min_volume": min_volume,
            "volume_step": volume_step,
            "sizing_type": self.position_size_type
        }
        
        logger.info(f"[{symbol}] Position size: {volume} lots (min={min_volume}, step={volume_step})")
        
        return volume, details
    
    def calculate_stop_loss(self, symbol: str, entry_price: float, 
                           direction: str, atr_value: Optional[float] = None) -> Optional[float]:
        """
        Calculate stop loss price
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price
            direction: "LONG" or "SHORT"
            atr_value: ATR value if using ATR-based SL
            
        Returns:
            Stop loss price or None
        """
        if self.sl_type == 'atr' and atr_value:
            # ATR-based stop loss
            sl_distance = atr_value * self.sl_atr_multiplier
        else:
            # Fixed percentage of margin -> convert to price distance
            # SL triggers when loss = fixed_percent of margin
            # For a $10 margin with 50% SL, max loss = $5
            
            # Get position size
            volume, _ = self.calculate_position_size(symbol)
            if volume == 0:
                return None
            
            info = self.mt5.get_symbol_info(symbol)
            if info is None:
                return None
            
            contract_size = info.get('trade_contract_size', 1)
            point = info.get('point', 0.00001)
            
            # Max loss in dollars
            max_loss = self.max_margin * (self.sl_fixed_percent / 100)
            
            # Convert to price distance
            # Loss = Volume * Contract_Size * Price_Movement
            # Price_Movement = Loss / (Volume * Contract_Size)
            if volume * contract_size == 0:
                return None
            
            sl_distance = max_loss / (volume * contract_size)
        
        # Calculate SL price based on direction
        if direction == "LONG":
            sl_price = entry_price - sl_distance
        else:
            sl_price = entry_price + sl_distance
        
        # Round to symbol precision
        info = self.mt5.get_symbol_info(symbol)
        if info:
            digits = info.get('digits', 5)
            point = info.get('point', 0.00001)
            spread_points = info.get('spread', 0)
            spread_val = spread_points * point
            
            sl_price = round(sl_price, digits)
            
            # spread safety check
            # For LONG: SL must be < Bid. Entry is Ask. Bid = Ask - Spread.
            # For SHORT: SL must be > Ask. Entry is Bid. Ask = Bid + Spread.
            
            if direction == "LONG":
                # Assuming entry_price is Ask
                approx_bid = entry_price - spread_val
                if sl_price >= approx_bid:
                    safe_sl = approx_bid - (3 * point) # 3 points safety
                    safe_sl = round(safe_sl, digits)
                    logger.warning(f"[{symbol}] Calculated SL ({sl_price}) >= Bid ({approx_bid}). Clamping to {safe_sl}")
                    sl_price = safe_sl
            else:
                # Assuming entry_price is Bid
                approx_ask = entry_price + spread_val
                if sl_price <= approx_ask:
                    safe_sl = approx_ask + (3 * point) # 3 points safety
                    safe_sl = round(safe_sl, digits)
                    logger.warning(f"[{symbol}] Calculated SL ({sl_price}) <= Ask ({approx_ask}). Clamping to {safe_sl}")
                    sl_price = safe_sl

        logger.info(f"[{symbol}] SL calculated: {sl_price} (distance: {sl_distance})")
        
        return sl_price
    
    def open_position(self, symbol: str, direction: str, 
                      reason: str = "EMA Signal") -> TradeResult:
        """
        Open a new position
        
        Args:
            symbol: Trading symbol
            direction: "LONG" or "SHORT"
            reason: Reason for trade
            
        Returns:
            TradeResult with execution details
        """
        timestamp = datetime.now().isoformat()
        
        # Pre-flight checks
        # 0. Market closed check
        symbol_info = self.mt5.get_symbol_info(symbol)
        if symbol_info and not symbol_info.get('trade_allowed', False):
            logger.warning(f"[{symbol}] Market CLOSED - skipping trade")
            return TradeResult(
                success=False, action=f"OPEN_{direction}", symbol=symbol,
                volume=0, price=0, sl=None, tp=None, ticket=None,
                error="Market closed (trade disabled)", margin_used=0,
                timestamp=timestamp
            )
        
        # 1. Session filter
        session_ok, session_reason = self.check_session_filter()
        if not session_ok:
            return TradeResult(
                success=False, action=f"OPEN_{direction}", symbol=symbol,
                volume=0, price=0, sl=None, tp=None, ticket=None,
                error=f"Session filter: {session_reason}", margin_used=0,
                timestamp=timestamp
            )
        
        # 2. Spread check
        spread_ok, spread = self.check_spread(symbol)
        if not spread_ok:
            return TradeResult(
                success=False, action=f"OPEN_{direction}", symbol=symbol,
                volume=0, price=0, sl=None, tp=None, ticket=None,
                error=f"Spread too wide: {spread}", margin_used=0,
                timestamp=timestamp
            )
        
        # 3. Daily loss check
        can_trade, loss_percent = self.check_daily_loss_limit()
        if not can_trade:
            return TradeResult(
                success=False, action=f"OPEN_{direction}", symbol=symbol,
                volume=0, price=0, sl=None, tp=None, ticket=None,
                error=f"Daily loss limit: {loss_percent:.1f}%", margin_used=0,
                timestamp=timestamp
            )
        
        # 4. Calculate position size
        volume, size_details = self.calculate_position_size(symbol)
        if volume == 0:
            return TradeResult(
                success=False, action=f"OPEN_{direction}", symbol=symbol,
                volume=0, price=0, sl=None, tp=None, ticket=None,
                error=f"Position size error: {size_details.get('error', 'Unknown')}", 
                margin_used=0, timestamp=timestamp
            )
        
        # 5. Get current price
        price_info = self.mt5.get_current_price(symbol)
        if price_info is None:
            return TradeResult(
                success=False, action=f"OPEN_{direction}", symbol=symbol,
                volume=volume, price=0, sl=None, tp=None, ticket=None,
                error="Failed to get price", margin_used=0, timestamp=timestamp
            )
        
        entry_price = price_info['ask'] if direction == "LONG" else price_info['bid']
        
        # 6. Calculate stop loss
        sl_price = self.calculate_stop_loss(symbol, entry_price, direction)
        
        # 7. Execute trade
        order_type = "BUY" if direction == "LONG" else "SELL"
        result = self.mt5.place_order(
            symbol=symbol,
            order_type=order_type,
            volume=volume,
            sl=sl_price,
            magic=self.magic_number,
            comment="EMAX"
        )
        
        if result['success']:
            margin_used = size_details.get('margin_per_lot', 0) * volume
            self.daily_trades += 1
            
            trade_result = TradeResult(
                success=True, action=f"OPEN_{direction}", symbol=symbol,
                volume=volume, price=result.get('price', entry_price), 
                sl=sl_price, tp=None, ticket=result.get('ticket'),
                error=None, margin_used=margin_used, timestamp=timestamp
            )
            
            self.trade_history.append(trade_result)
            logger.info(f"[{symbol}] Position opened: {direction} {volume} @ {entry_price}, SL={sl_price}, Ticket={result.get('ticket')}")
            
            # Log to CSV
            try:
                account = self.mt5.get_account_summary()
                self._log_trade_event(trade_result, account)
            except Exception as e:
                logger.error(f"CSV Logging failed: {e}")
            
            return trade_result
        else:
            return TradeResult(
                success=False, action=f"OPEN_{direction}", symbol=symbol,
                volume=volume, price=entry_price, sl=sl_price, tp=None, ticket=None,
                error=result.get('error', 'Unknown error'), margin_used=0,
                timestamp=timestamp
            )
    
    def close_position(self, symbol: str, ticket: Optional[int] = None,
                       reason: str = "Signal") -> TradeResult:
        """
        Close a position
        
        Args:
            symbol: Trading symbol
            ticket: Optional specific ticket to close
            reason: Reason for closing
            
        Returns:
            TradeResult with execution details
        """
        timestamp = datetime.now().isoformat()
        
        # Get position(s) to close
        if ticket:
            positions = [p for p in self.mt5.get_positions(symbol) if p['ticket'] == ticket]
        else:
            positions = self.mt5.get_positions(symbol)
        
        if not positions:
            return TradeResult(
                success=False, action="CLOSE", symbol=symbol,
                volume=0, price=0, sl=None, tp=None, ticket=ticket,
                error="No position found", margin_used=0, timestamp=timestamp
            )
        
        # Close first/only position
        pos = positions[0]
        result = self.mt5.close_position(pos['ticket'])
        
        if result['success']:
            direction = "LONG" if pos['type'] == "BUY" else "SHORT"
            self.daily_pnl += pos['profit']
            
            trade_result = TradeResult(
                success=True, action=f"CLOSE_{direction}", symbol=symbol,
                volume=pos['volume'], price=result.get('close_price', 0),
                sl=None, tp=None, ticket=pos['ticket'],
                error=None, margin_used=0, timestamp=timestamp
            )
            
            self.trade_history.append(trade_result)
            logger.info(f"[{symbol}] Position closed: {direction} {pos['volume']} PnL=${pos['profit']:.2f}")
            
            # Log to CSV
            try:
                account = self.mt5.get_account_summary()
                self._log_trade_event(trade_result, account, profit=pos.get('profit', 0.0))
            except Exception as e:
                logger.error(f"CSV Logging close failed: {e}")
            
            return trade_result
        else:
            return TradeResult(
                success=False, action="CLOSE", symbol=symbol,
                volume=pos['volume'], price=0, sl=None, tp=None, ticket=pos['ticket'],
                error=result.get('error', 'Unknown error'), margin_used=0,
                timestamp=timestamp
            )
    
    def close_all_positions(self) -> Dict:
        """
        Close all open positions (panic button)
        
        Returns:
            Dict with summary of closed positions
        """
        result = self.mt5.close_all_positions()
        
        if result['closed'] > 0:
            logger.warning(f"PANIC: Closed {result['closed']} positions")
        
        return result
    
    def get_current_positions(self) -> List[Dict]:
        """Get all current positions"""
        return self.mt5.get_positions()
    
    def get_daily_stats(self) -> Dict:
        """Get daily trading statistics from Broker History (Robust to restarts)"""
        # Define start of day
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get actual deals from broker
        daily_deals = self.mt5.get_history_deals(from_date=today_start)
        
        # Filter for this bot (Magic Number)
        my_deals = [d for d in daily_deals if d.get('magic') == self.magic_number]
        
        # Calculate Real PnL & Trades
        real_pnl = 0.0
        closed_trades_count = 0
        
        for deal in my_deals:
            # Sum all financial impacts (profit, swap, commission, fee)
            real_pnl += deal.get('profit', 0.0)
            real_pnl += deal.get('swap', 0.0)
            real_pnl += deal.get('commission', 0.0)
            real_pnl += deal.get('fee', 0.0)
            
            # Count exits (Entry Out or OutBy) as "Trades"
            # entry: 0=IN, 1=OUT, 2=IN/OUT, 3=OUT_BY
            if deal.get('entry') in [1, 3]:
                closed_trades_count += 1
        
        # Update internal state with source of truth
        self.daily_pnl = real_pnl
        self.daily_trades = closed_trades_count # Reflect closed trades count
        
        # Update starting balance (optional, for consistency)
        if self.starting_balance is None:
             account = self.mt5.get_account_summary()
             self.starting_balance = account.get('balance', 0)
        
        return {
            "date": datetime.now().date().isoformat(),
            "starting_balance": self.starting_balance,
            "daily_pnl": self.daily_pnl,
            "daily_trades": self.daily_trades,
            "current_drawdown": 0.0,
            "max_drawdown": 0.0
        }
        
    def get_stats_since(self, start_time: datetime) -> Dict:
        """Get trading statistics since specific time (Session Stats)"""
        if not start_time:
            return {"pnl": 0.0, "trades": 0}
            
        # Get actual deals from broker
        session_deals = self.mt5.get_history_deals(from_date=start_time)
        
        # Filter for this bot
        my_deals = [d for d in session_deals if d.get('magic') == self.magic_number]
        
        # Calculate PnL & Trades
        pnl = 0.0
        trades = 0
        
        for deal in my_deals:
            pnl += deal.get('profit', 0.0)
            pnl += deal.get('swap', 0.0)
            pnl += deal.get('commission', 0.0)
            pnl += deal.get('fee', 0.0)
            
            if deal.get('entry') in [1, 3]:
                trades += 1
                
        return {
            "pnl": pnl,
            "trades": trades,
            "start_time": start_time.isoformat()
        }
    
    def freeze_trading(self, reason: str = "Manual freeze"):
        """
        Freeze trading - prevents NEW trades but allows existing positions to run

        This is useful for:
        - High-impact news events
        - Market volatility periods
        - Manual risk management
        - Automated news detection (future feature)

        Args:
            reason: Reason for freezing (e.g., "News event", "High volatility")
        """
        self.trading_frozen = True
        self.freeze_reason = reason
        self.freeze_timestamp = datetime.now().isoformat()
        logger.warning(f"⏸️ TRADING FROZEN: {reason}")

    def unfreeze_trading(self):
        """Unfreeze trading - resume taking new trades"""
        was_frozen = self.trading_frozen
        self.trading_frozen = False
        self.freeze_reason = None
        self.freeze_timestamp = None
        if was_frozen:
            logger.info("▶️ TRADING UNFROZEN: Resuming new trades")

    def is_trading_frozen(self) -> bool:
        """Check if trading is currently frozen"""
        return self.trading_frozen

    def get_manager_status(self) -> Dict:
        """Get current manager status for dashboard"""
        can_trade, loss_percent = self.check_daily_loss_limit()
        session_ok, session_reason = self.check_session_filter()

        return {
            "max_margin_per_trade": self.max_margin,
            "sl_type": self.sl_type,
            "sl_fixed_percent": self.sl_fixed_percent,
            "sl_atr_multiplier": self.sl_atr_multiplier,
            "session_filter_enabled": self.session_filter_enabled,
            "session_allowed": session_ok,
            "session_reason": session_reason,
            "daily_loss_limit": self.max_daily_loss_percent,
            "current_daily_loss": loss_percent,
            "can_trade": can_trade,
            "daily_trades": self.daily_trades,
            "trading_frozen": self.trading_frozen,
            "freeze_reason": self.freeze_reason,
            "freeze_timestamp": self.freeze_timestamp
        }

    def update_trailing_sl(self, position: Dict) -> bool:
        """
        Update trailing stop loss
        
        Args:
            position: Position dictionary from MT5
            
        Returns:
            bool: True if SL was updated, False otherwise
        """
        ticket = position['ticket']
        symbol = position['symbol']
        order_type = position['type']
        current_sl = position.get('sl', 0.0)
        
        # Get current price
        price_current = position.get('price_current', 0.0)
        if price_current == 0:
            # Try to get fresh price
            tick = self.mt5.get_current_price(symbol)
            if tick:
                price_current = tick['bid'] if order_type == 0 else tick['ask']
        
        if price_current == 0:
            return False
            
        price_open = position['price_open']
        
        if not self.tsl_enabled:
            return False
            
        # Define trailing parameters from config
        point = self.mt5.get_symbol_info(symbol).get('point', 0.00001)
        activation_dist_points = self.tsl_activation
        trail_dist_points = self.tsl_distance
        step_points = self.tsl_step
        
        new_sl = current_sl
        
        if order_type == 0: # BUY
            # Profit in points
            profit_points = (price_current - price_open) / point
            
            if profit_points > activation_dist_points:
                # Target SL level
                target_sl = price_current - (trail_dist_points * point)
                
                # Only move SL up
                if target_sl > current_sl and target_sl > price_open:
                    if (target_sl - current_sl) >= (step_points * point):
                        new_sl = target_sl
                        
        elif order_type == 1: # SELL
            # Profit in points
            profit_points = (price_open - price_current) / point
            
            if profit_points > activation_dist_points:
                 # Target SL level
                target_sl = price_current + (trail_dist_points * point)
                
                # Only move SL down
                if (current_sl == 0 or target_sl < current_sl) and target_sl < price_open:
                    if current_sl == 0 or (current_sl - target_sl) >= (step_points * point):
                        new_sl = target_sl
        
        # Apply modification if needed
        if new_sl != current_sl:
             # Round to digits
            info = self.mt5.get_symbol_info(symbol)
            digits = info.get('digits', 5) if info else 5
            new_sl = round(new_sl, digits)
            
            request = {
                "action": self.mt5.mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "sl": new_sl,
                "tp": position.get('tp', 0.0)
            }
            
            res = self.mt5.mt5.order_send(request)
            if res.retcode == self.mt5.mt5.TRADE_RETCODE_DONE:
                logger.info(f"[{symbol}] Trailing SL updated: {current_sl} -> {new_sl}")
                return True
            else:
                logger.error(f"[{symbol}] Failed to update SL: {res.comment}")
                
        return False

    def manage_position(self, position: Dict) -> Dict[str, int]:
        """
        Manage an existing position (Trailing SL, etc)
        
        Args:
            position: Position dictionary from MT5
            
        Returns:
            Dict[str, int]: Dictionary with 'sl' and 'tp' modification counts
        """
        mods = {'sl': 0, 'tp': 0}
        
        # Trailing SL logic
        if self.update_trailing_sl(position):
            mods['sl'] += 1
            
        return mods


def test_position_manager():
    """Test position manager (requires MT5 connection)"""
    print("Position Manager test requires MT5 connection")
    print("Use integration tests with mock connector for unit testing")


if __name__ == "__main__":
    test_position_manager()
