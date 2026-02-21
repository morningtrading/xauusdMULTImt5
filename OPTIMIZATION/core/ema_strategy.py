"""
================================================================================
EMA STRATEGY MODULE - EMAX Trading Engine
================================================================================

PURPOSE:
    Implements the EMA Crossover trading strategy. Uses a fast EMA (default 9)
    and slow EMA (default 41) to generate buy and sell signals. Handles signal
    detection, duplicate prevention, and direction filtering.

INPUTS:
    - OHLCV price data from MT5Connector
    - Configuration from trading_config.json:
        * fast_ema_period (default: 9)
        * slow_ema_period (default: 41)
        * direction: "both", "long", "short"
        * prevent_duplicate_signals: true/false
        * min_bars_between_trades: number

OUTPUTS:
    - Trading signals: {"action": "BUY/SELL/HOLD", "reason": "...", "strength": 0-1}
    - EMA values for dashboard display
    - Signal history for analysis

HOW TO INSTALL:
    This module is part of the EMAX trading engine. No separate installation needed.
    Dependencies: numpy, pandas (included in requirements.txt)

SEQUENCE IN OVERALL SYSTEM:
    [MT5 Connector] -> [EMA Strategy] -> [Position Manager] -> [MT5 Connector]
                           ^
                           |
                    [Config File]

    The EMA Strategy receives price data, calculates EMAs, detects crossovers,
    and outputs trading signals to the Position Manager.

OBJECTIVE:
    Generate reliable trading signals based on EMA crossovers with proper
    filtering to avoid whipsaws and duplicate entries during the same candle.

SIGNAL LOGIC:
    - BUY: Fast EMA crosses ABOVE slow EMA (bullish crossover)
    - SELL: Fast EMA crosses BELOW slow EMA (bearish crossover)
    - EXIT LONG: Fast EMA crosses below slow EMA OR price 0.1% below slow EMA
    - EXIT SHORT: Fast EMA crosses above slow EMA OR price 0.1% above slow EMA

AUTHOR: EMAX Trading Engine
VERSION: 1.0.0
LAST UPDATED: 2026-01-22
================================================================================
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger('EMAStrategy')


class SignalType(Enum):
    """Trading signal types"""
    BUY = "BUY"
    SELL = "SELL"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"
    HOLD = "HOLD"


@dataclass
class Signal:
    """Trading signal with metadata"""
    action: SignalType
    symbol: str
    reason: str
    strength: float  # 0.0 to 1.0
    fast_ema: float
    slow_ema: float
    price: float
    timestamp: str
    bar_time: str  # Time of the bar that generated this signal


class EMAStrategy:
    """
    EMA Crossover Trading Strategy
    
    Generates trading signals based on Exponential Moving Average crossovers.
    Includes duplicate signal prevention and direction filtering.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize EMA Strategy
        
        Args:
            config_path: Path to trading_config.json
        """
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'trading_config.json'
        self.config = self._load_config(config_path)
        
        # Strategy parameters from config
        # STRICT CONFIG ACCESS
        try:
            strategy_config = self.config['strategy']
            self.fast_period = strategy_config['fast_ema_period']
            self.slow_period = strategy_config['slow_ema_period']
            self.direction = strategy_config['direction']
            self.prevent_duplicates = strategy_config['prevent_duplicate_signals']
            self.min_bars_between = strategy_config['min_bars_between_trades']
            self.trading_enabled = strategy_config['trading_enabled']
            
            # Exit Rules (Strict)
            exit_config = self.config['exit_rules']
            self.exit_on_cross = exit_config['exit_on_ema_cross']
            self.exit_on_price_deviation = exit_config['exit_on_price_below_slow_ema']
            self.price_deviation_percent = exit_config['price_below_slow_ema_percent']
        except KeyError as e:
            logger.error(f"STRICT CONFIG ERROR: Missing key {e} in strategy/exit_rules")
            # Set fail-safe defaults or allow crash? User asked for strict errors.
            # But we are in __init__, so we can't easily "stop" without raising.
            raise ValueError(f"CRITICAL: Missing configuration key {e}")
        
        # Per-symbol settings from config
        self.symbol_settings = self.config.get('symbols', {}).get('settings', {})
        
        # State tracking per symbol
        self.last_signal: Dict[str, Signal] = {}
        self.last_signal_bar: Dict[str, str] = {}  # Track which bar generated last signal
        self.current_position: Dict[str, str] = {}  # "LONG", "SHORT", or None
        
        # EMA cache
        self.ema_cache: Dict[str, Dict] = {}
        
        logger.info(f"EMAStrategy initialized: Default Fast={self.fast_period}, Slow={self.slow_period}, Direction={self.direction}")
    
    def get_symbol_ema_settings(self, symbol: str) -> tuple:
        """
        Get EMA settings for a specific symbol.
        Falls back to global settings if not defined per-symbol.
        
        Returns:
            Tuple of (fast_period, slow_period)
        """
        # STRICT ACCESS
        sym_config = self.symbol_settings.get(symbol, {})
        # Note: If symbol not in settings, we fall back to GLOBAL defaults (self.fast_period),
        # which were strictly validated in __init__.
        # But if symbol IS in settings, we expect 'fast_ema' and 'slow_ema' to be there?
        # Logic: get() returns None if missing? No, user wants STRICT.
        # If 'XAUUSD' is in config, it MUST have 'fast_ema'.
        
        if symbol in self.symbol_settings:
            try:
                fast = sym_config['fast_ema']
                slow = sym_config['slow_ema']
            except KeyError as e:
                logger.error(f"[{symbol}] STRICT CONFIG ERROR: Missing EMA setting {e}")
                # Fallback to global? Or Raise?
                # User wants strict.
                raise ValueError(f"[{symbol}] Missing {e} in config")
        else:
             # Symbol not in config at all? Use global defaults (which are valid).
             fast = self.fast_period
             slow = self.slow_period
             
        return fast, slow
        return fast, slow
    
    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}, using defaults")
            return {}
    
    def calculate_ema(self, prices: List[float], period: int) -> List[float]:
        """
        Calculate Exponential Moving Average
        
        Args:
            prices: List of close prices
            period: EMA period
            
        Returns:
            List of EMA values (same length as prices, with NaN for insufficient data)
        """
        if len(prices) < period:
            return [None] * len(prices)
        
        ema = []
        multiplier = 2 / (period + 1)
        
        # Start with SMA for first EMA value
        sma = sum(prices[:period]) / period
        ema = [None] * (period - 1) + [sma]
        
        # Calculate EMA for remaining values
        for i in range(period, len(prices)):
            ema_value = (prices[i] * multiplier) + (ema[-1] * (1 - multiplier))
            ema.append(ema_value)
        
        return ema
    
    def analyze(self, symbol: str, bars: List[Dict], current_position: Optional[str] = None) -> Signal:
        """
        Analyze price data and generate trading signal
        
        Args:
            symbol: Trading symbol
            bars: List of OHLCV dicts from MT5Connector.get_rates()
            current_position: Current position type ("LONG", "SHORT", or None)
            
        Returns:
            Signal object with action and metadata
        """
        # Get per-symbol EMA settings
        sym_fast_period, sym_slow_period = self.get_symbol_ema_settings(symbol)
        
        if not bars or len(bars) < sym_slow_period + 2:
            return Signal(
                action=SignalType.HOLD,
                symbol=symbol,
                reason=f"Insufficient data ({len(bars)} bars, need {sym_slow_period + 2})",
                strength=0.0,
                fast_ema=0.0,
                slow_ema=0.0,
                price=0.0,
                timestamp=datetime.now().isoformat(),
                bar_time=""
            )
        
        # Extract close prices
        closes = [bar['close'] for bar in bars]
        
        # Calculate EMAs using per-symbol periods
        fast_ema = self.calculate_ema(closes, sym_fast_period)
        slow_ema = self.calculate_ema(closes, sym_slow_period)
        
        # Get current and previous values
        current_fast = fast_ema[-1]
        current_slow = slow_ema[-1]
        prev_fast = fast_ema[-2]
        prev_slow = slow_ema[-2]
        current_price = closes[-1]
        current_bar_time = bars[-1]['time']
        current_low = bars[-1]['low']
        current_high = bars[-1]['high']
        
        # Cache EMA values (Store last 3 for trend analysis)
        self.ema_cache[symbol] = {
            'fast_ema': fast_ema[-3:] if len(fast_ema) >= 3 else fast_ema,
            'slow_ema': slow_ema[-3:] if len(slow_ema) >= 3 else slow_ema,
            'price': current_price,
            'updated': datetime.now().isoformat()
        }
        
        # Update current position tracking
        if current_position:
            self.current_position[symbol] = current_position
        
        # Check for exit signals first if we have a position
        position = self.current_position.get(symbol)
        
        if position == "LONG":
            exit_signal = self._check_exit_long(
                symbol, current_fast, current_slow, prev_fast, prev_slow,
                current_low, current_price, current_bar_time
            )
            if exit_signal:
                return exit_signal
        
        elif position == "SHORT":
            exit_signal = self._check_exit_short(
                symbol, current_fast, current_slow, prev_fast, prev_slow,
                current_high, current_price, current_bar_time
            )
            if exit_signal:
                return exit_signal
        
        # Check for entry signals only if no position
        if position is None:
            entry_signal = self._check_entry(
                symbol, current_fast, current_slow, prev_fast, prev_slow,
                current_price, current_bar_time
            )
            if entry_signal:
                return entry_signal
        
        # No signal
        return Signal(
            action=SignalType.HOLD,
            symbol=symbol,
            reason="No signal",
            strength=0.0,
            fast_ema=current_fast,
            slow_ema=current_slow,
            price=current_price,
            timestamp=datetime.now().isoformat(),
            bar_time=current_bar_time
        )
    
    def _check_entry(self, symbol: str, current_fast: float, current_slow: float,
                     prev_fast: float, prev_slow: float, price: float, 
                     bar_time: str) -> Optional[Signal]:
        """Check for entry signals (crossovers)"""
        
        # Check if trading is enabled
        if not self.trading_enabled:
            return None
        
        # Prevent duplicate signals on same bar
        if self.prevent_duplicates:
            if self.last_signal_bar.get(symbol) == bar_time:
                return None
        
        # BULLISH CROSSOVER: Fast crosses above slow
        if prev_fast <= prev_slow and current_fast > current_slow:
            if self.direction in ['both', 'long']:
                signal = Signal(
                    action=SignalType.BUY,
                    symbol=symbol,
                    reason=f"Bullish EMA crossover: Fast({self.fast_period})={current_fast:.5f} > Slow({self.slow_period})={current_slow:.5f}",
                    strength=self._calculate_strength(current_fast, current_slow),
                    fast_ema=current_fast,
                    slow_ema=current_slow,
                    price=price,
                    timestamp=datetime.now().isoformat(),
                    bar_time=bar_time
                )
                self.last_signal[symbol] = signal
                self.last_signal_bar[symbol] = bar_time
                logger.info(f"[{symbol}] BUY signal: {signal.reason}")
                return signal
        
        # BEARISH CROSSOVER: Fast crosses below slow
        if prev_fast >= prev_slow and current_fast < current_slow:
            if self.direction in ['both', 'short']:
                signal = Signal(
                    action=SignalType.SELL,
                    symbol=symbol,
                    reason=f"Bearish EMA crossover: Fast({self.fast_period})={current_fast:.5f} < Slow({self.slow_period})={current_slow:.5f}",
                    strength=self._calculate_strength(current_fast, current_slow),
                    fast_ema=current_fast,
                    slow_ema=current_slow,
                    price=price,
                    timestamp=datetime.now().isoformat(),
                    bar_time=bar_time
                )
                self.last_signal[symbol] = signal
                self.last_signal_bar[symbol] = bar_time
                logger.info(f"[{symbol}] SELL signal: {signal.reason}")
                return signal
        
        return None
    
    def _check_exit_long(self, symbol: str, current_fast: float, current_slow: float,
                         prev_fast: float, prev_slow: float, current_low: float,
                         price: float, bar_time: str) -> Optional[Signal]:
        """Check for exit signals for long positions"""
        
        reasons = []
        
        # Exit on bearish crossover
        if self.exit_on_cross:
            if prev_fast >= prev_slow and current_fast < current_slow:
                reasons.append(f"Bearish EMA crossover")
        
        # Exit if price deviates too far below slow EMA
        if self.exit_on_price_deviation:
            threshold = current_slow * (1 - self.price_deviation_percent / 100)
            if current_low < threshold:
                reasons.append(f"Price {current_low:.5f} below {self.price_deviation_percent}% of slow EMA ({threshold:.5f})")
        
        if reasons:
            signal = Signal(
                action=SignalType.EXIT_LONG,
                symbol=symbol,
                reason=" | ".join(reasons),
                strength=1.0,
                fast_ema=current_fast,
                slow_ema=current_slow,
                price=price,
                timestamp=datetime.now().isoformat(),
                bar_time=bar_time
            )
            self.current_position[symbol] = None
            logger.info(f"[{symbol}] EXIT_LONG signal: {signal.reason}")
            return signal
        
        return None
    
    def _check_exit_short(self, symbol: str, current_fast: float, current_slow: float,
                          prev_fast: float, prev_slow: float, current_high: float,
                          price: float, bar_time: str) -> Optional[Signal]:
        """Check for exit signals for short positions"""
        
        reasons = []
        
        # Exit on bullish crossover
        if self.exit_on_cross:
            if prev_fast <= prev_slow and current_fast > current_slow:
                reasons.append(f"Bullish EMA crossover")
        
        # Exit if price deviates too far above slow EMA
        if self.exit_on_price_deviation:
            threshold = current_slow * (1 + self.price_deviation_percent / 100)
            if current_high > threshold:
                reasons.append(f"Price {current_high:.5f} above {self.price_deviation_percent}% of slow EMA ({threshold:.5f})")
        
        if reasons:
            signal = Signal(
                action=SignalType.EXIT_SHORT,
                symbol=symbol,
                reason=" | ".join(reasons),
                strength=1.0,
                fast_ema=current_fast,
                slow_ema=current_slow,
                price=price,
                timestamp=datetime.now().isoformat(),
                bar_time=bar_time
            )
            self.current_position[symbol] = None
            logger.info(f"[{symbol}] EXIT_SHORT signal: {signal.reason}")
            return signal
        
        return None
    
    def _calculate_strength(self, fast_ema: float, slow_ema: float) -> float:
        """
        Calculate signal strength based on EMA separation
        
        Returns:
            float: 0.0 to 1.0
        """
        if slow_ema == 0:
            return 0.0
        
        separation_percent = abs(fast_ema - slow_ema) / slow_ema * 100
        # Normalize: 0.5% separation = 1.0 strength
        strength = min(separation_percent / 0.5, 1.0)
        return strength
    
    def get_ema_values(self, symbol: str) -> Optional[Dict]:
        """
        Get cached EMA values for a symbol
        
        Returns:
            Dict with fast_ema, slow_ema, price, updated timestamp
        """
        return self.ema_cache.get(symbol)
    
    def set_position(self, symbol: str, position_type: Optional[str]):
        """
        Update position tracking
        
        Args:
            symbol: Trading symbol
            position_type: "LONG", "SHORT", or None
        """
        self.current_position[symbol] = position_type
    
    def set_trading_enabled(self, enabled: bool):
        """Enable or disable trading signals"""
        self.trading_enabled = enabled
        logger.info(f"Trading {'enabled' if enabled else 'disabled'}")
    
    def set_direction(self, direction: str):
        """
        Set trading direction filter
        
        Args:
            direction: "both", "long", or "short"
        """
        if direction in ['both', 'long', 'short']:
            self.direction = direction
            logger.info(f"Direction set to: {direction}")
    
    def get_strategy_status(self) -> Dict:
        """Get current strategy status for dashboard"""
        return {
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "direction": self.direction,
            "trading_enabled": self.trading_enabled,
            "prevent_duplicates": self.prevent_duplicates,
            "exit_on_cross": self.exit_on_cross,
            "exit_on_price_deviation": self.exit_on_price_deviation,
            "price_deviation_percent": self.price_deviation_percent,
            "positions": dict(self.current_position),
            "ema_cache": dict(self.ema_cache)
        }

    def analyze_trend_momentum(self, fast_ema: List[float], slow_ema: List[float]) -> Dict:
        """
        Analyze trend and momentum for dashboard display
        
        Returns:
            Dict: {'state': 'BULL'/'BEAR', 'momentum': 'INCREASING'/'DECREASING'/'FLAT'}
        """
        if len(fast_ema) < 3 or len(slow_ema) < 3:
            if self.trading_enabled:
                logger.debug(f"Trend Analysis Failed: Insufficient history. FastLen={len(fast_ema)}, SlowLen={len(slow_ema)}")
            return {"trend": "N/A", "momentum": "FLAT"}
            
        curr_fast, prev_fast = fast_ema[-1], fast_ema[-2]
        curr_slow, prev_slow = slow_ema[-1], slow_ema[-2]
        
        if curr_fast is None or curr_slow is None:
             if self.trading_enabled:
                 logger.debug(f"Trend Analysis Failed: Null values. Fast={curr_fast}, Slow={curr_slow}")
             return {"trend": "N/A", "momentum": "FLAT"}
        
        # Trend State
        trend = "BULL" if curr_fast > curr_slow else "BEAR"
        
        # Momemtum (Rate of separation)
        curr_sep = abs(curr_fast - curr_slow)
        
        if prev_fast is not None and prev_slow is not None:
            prev_sep = abs(prev_fast - prev_slow)
            diff = curr_sep - prev_sep
            
            # Strict momentum check (any expansion is increasing momentum)
            if curr_sep > prev_sep:
                momentum = "INCREASING"
            elif curr_sep < prev_sep:
                momentum = "DECREASING"
            else:
                momentum = "FLAT"
                # Log why it's flat to debug user issue
                if self.trading_enabled: # Reduce log spam, only valid symbols needed
                    logger.debug(f"FLAT Momentum for separation: Curr={curr_sep:.8f}, Prev={prev_sep:.8f}, Diff={diff:.8f}")
        else:
            momentum = "FLAT"
            diff = 0.0
            
        return {"trend": trend, "momentum": momentum, "separation": curr_sep, "diff": diff}


def test_strategy():
    """Quick test of EMA strategy with sample data"""
    from datetime import datetime, timedelta
    import random
    
    # Generate sample price data
    bars = []
    base_price = 30.0  # Sample for XAGUSD
    
    for i in range(100):
        # Simulate trending price with noise
        trend = 0.05 * i / 100
        noise = random.uniform(-0.1, 0.1)
        price = base_price + trend + noise
        
        bars.append({
            'time': (datetime.now() - timedelta(minutes=5*(100-i))).isoformat(),
            'open': price - random.uniform(0, 0.05),
            'high': price + random.uniform(0, 0.1),
            'low': price - random.uniform(0, 0.1),
            'close': price,
            'volume': random.randint(100, 1000)
        })
    
    # Test strategy
    strategy = EMAStrategy()
    signal = strategy.analyze("XAGUSD", bars)
    
    print("\n" + "="*50)
    print("EMA STRATEGY TEST")
    print("="*50)
    print(f"Signal: {signal.action.value}")
    print(f"Reason: {signal.reason}")
    print(f"Strength: {signal.strength:.2f}")
    print(f"Fast EMA: {signal.fast_ema:.5f}")
    print(f"Slow EMA: {signal.slow_ema:.5f}")
    print(f"Price: {signal.price:.5f}")
    print("="*50)


if __name__ == "__main__":
    test_strategy()
