"""
================================================================================
DONCHIAN CHANNEL BREAKOUT STRATEGY - Donchian Trading Engine
================================================================================

PURPOSE:
    Implements the Donchian Channel Breakout trading strategy. Uses a lookback
    period (default 20) to compute the highest high and lowest low, generating
    buy/sell signals when price breaks out of the channel.

INPUTS:
    - OHLCV price data from MT5Connector
    - Configuration from trading_config.json:
        * channel_period (default: 20)
        * direction: "both", "long", "short"
        * prevent_duplicate_signals: true/false
        * min_bars_between_trades: number

OUTPUTS:
    - Trading signals: {"action": "BUY/SELL/HOLD", "reason": "...", "strength": 0-1}
    - Channel values for dashboard display
    - Signal history for analysis

SIGNAL LOGIC:
    - BUY:  High breaks above upper channel (new N-bar high)
    - SELL: Low breaks below lower channel (new N-bar low)
    - EXIT LONG:  Price crosses below middle line OR bearish breakout
    - EXIT SHORT: Price crosses above middle line OR bullish breakout

SEQUENCE IN OVERALL SYSTEM:
    [MT5 Connector] -> [Donchian Strategy] -> [Position Manager] -> [MT5 Connector]

AUTHOR: Donchian Trading Engine
VERSION: 1.0.0
LAST UPDATED: 2026-02-22
================================================================================
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger('DonchianStrategy')


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
    upper_channel: float
    lower_channel: float
    mid_channel: float
    price: float
    timestamp: str
    bar_time: str


class DonchianStrategy:
    """
    Donchian Channel Breakout Trading Strategy

    Generates trading signals based on price breaking out of the
    N-period highest high / lowest low channel.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Donchian Strategy

        Args:
            config_path: Path to trading_config.json
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'trading_config.json'
        self.config = self._load_config(config_path)

        # Strategy parameters from config (STRICT)
        try:
            strategy_config = self.config['strategy']
            self.channel_period = strategy_config['channel_period']
            self.direction = strategy_config['direction']
            self.prevent_duplicates = strategy_config['prevent_duplicate_signals']
            self.min_bars_between = strategy_config['min_bars_between_trades']
            self.trading_enabled = strategy_config['trading_enabled']

            # Entry Filters
            self.adx_min = strategy_config.get('adx_min_threshold', 0)
            self.adx_period = strategy_config.get('adx_period', 14)
            self.close_confirm = strategy_config.get('close_confirm', False)
            self.cooldown_bars = strategy_config.get('cooldown_bars', 0)

            # Exit Rules
            exit_config = self.config['exit_rules']
            self.exit_on_mid_cross = exit_config['exit_on_mid_cross']
            self.exit_on_opposite_breakout = exit_config['exit_on_opposite_breakout']
        except KeyError as e:
            logger.error(f"STRICT CONFIG ERROR: Missing key {e}")
            raise ValueError(f"CRITICAL: Missing configuration key {e}")

        # Per-symbol settings
        self.symbol_settings = self.config.get('symbols', {}).get('settings', {})

        # State tracking per symbol
        self.last_signal: Dict[str, Signal] = {}
        self.last_signal_bar: Dict[str, str] = {}
        self.last_exit_bar_index: Dict[str, int] = {}  # bar index of last exit
        self.bar_counter: Dict[str, int] = {}  # running bar count per symbol
        self.current_position: Dict[str, str] = {}

        # Channel cache
        self.channel_cache: Dict[str, Dict] = {}

        # ADX cache per symbol
        self.adx_cache: Dict[str, float] = {}

        logger.info(f"DonchianStrategy initialized: Period={self.channel_period}, "
                    f"Direction={self.direction}, ADX>={self.adx_min}, "
                    f"CloseConfirm={self.close_confirm}, Cooldown={self.cooldown_bars}")

    def get_symbol_settings(self, symbol: str) -> int:
        """
        Get channel period for a specific symbol.
        Falls back to global default if not defined per-symbol.

        Returns:
            channel_period for the symbol
        """
        sym_config = self.symbol_settings.get(symbol, {})

        if symbol in self.symbol_settings:
            try:
                return sym_config['channel_period']
            except KeyError as e:
                logger.error(f"[{symbol}] STRICT CONFIG ERROR: Missing {e}")
                raise ValueError(f"[{symbol}] Missing {e} in config")
        else:
            return self.channel_period

    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}, using defaults")
            return {}

    def calculate_donchian(self, bars: List[Dict], period: int) -> List[Dict]:
        """
        Calculate Donchian Channel values

        Args:
            bars: List of OHLCV dicts
            period: Lookback period

        Returns:
            List of dicts with 'upper', 'mid', 'lower' keys (None for insufficient data)
        """
        channels = []
        for i in range(len(bars)):
            if i < period:
                channels.append({'upper': None, 'mid': None, 'lower': None})
            else:
                window = bars[i - period:i]
                upper = max(b['high'] for b in window)
                lower = min(b['low'] for b in window)
                mid = (upper + lower) / 2.0
                channels.append({'upper': upper, 'mid': mid, 'lower': lower})
        return channels

    def calculate_adx(self, bars: List[Dict], period: int = 14) -> float:
        """
        Calculate current ADX value from bar data.

        Args:
            bars: List of OHLCV dicts (needs at least 3*period bars)
            period: ADX smoothing period (default 14)

        Returns:
            Current ADX value, or 0.0 if insufficient data
        """
        n = len(bars)
        if n < period * 3:
            return 0.0

        # True Range, +DM, -DM
        tr = [0.0] * n
        pdm = [0.0] * n
        ndm = [0.0] * n

        for i in range(1, n):
            h, l, pc = bars[i]['high'], bars[i]['low'], bars[i - 1]['close']
            tr[i] = max(h - l, abs(h - pc), abs(l - pc))
            up = h - bars[i - 1]['high']
            dn = bars[i - 1]['low'] - l
            pdm[i] = up if up > dn and up > 0 else 0.0
            ndm[i] = dn if dn > up and dn > 0 else 0.0

        # Smoothed ATR, +DM, -DM
        atr = [0.0] * n
        spdm = [0.0] * n
        sndm = [0.0] * n

        atr[period] = sum(tr[1:period + 1]) / period
        spdm[period] = sum(pdm[1:period + 1]) / period
        sndm[period] = sum(ndm[1:period + 1]) / period

        for i in range(period + 1, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
            spdm[i] = (spdm[i - 1] * (period - 1) + pdm[i]) / period
            sndm[i] = (sndm[i - 1] * (period - 1) + ndm[i]) / period

        # DX series
        dx = [0.0] * n
        for i in range(period, n):
            if atr[i] > 0:
                pdi = 100 * spdm[i] / atr[i]
                ndi = 100 * sndm[i] / atr[i]
                if (pdi + ndi) > 0:
                    dx[i] = 100 * abs(pdi - ndi) / (pdi + ndi)

        # ADX = smoothed DX
        start = period * 2
        if start >= n:
            return 0.0

        adx = [0.0] * n
        adx[start] = sum(dx[period + 1:start + 1]) / period
        for i in range(start + 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

        return adx[-1]

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
        period = self.get_symbol_settings(symbol)

        if not bars or len(bars) < period + 2:
            return Signal(
                action=SignalType.HOLD,
                symbol=symbol,
                reason=f"Insufficient data ({len(bars)} bars, need {period + 2})",
                strength=0.0,
                upper_channel=0.0,
                lower_channel=0.0,
                mid_channel=0.0,
                price=0.0,
                timestamp=datetime.now().isoformat(),
                bar_time=""
            )

        # Calculate Donchian channels
        channels = self.calculate_donchian(bars, period)

        # Current and previous channel + price values
        curr_ch = channels[-1]
        prev_ch = channels[-2]
        current_bar = bars[-1]
        current_price = current_bar['close']
        current_high = current_bar['high']
        current_low = current_bar['low']
        current_bar_time = current_bar['time']

        if curr_ch['upper'] is None or prev_ch['upper'] is None:
            return Signal(
                action=SignalType.HOLD,
                symbol=symbol,
                reason="Channel not ready",
                strength=0.0,
                upper_channel=0.0,
                lower_channel=0.0,
                mid_channel=0.0,
                price=current_price,
                timestamp=datetime.now().isoformat(),
                bar_time=current_bar_time
            )

        upper = curr_ch['upper']
        lower = curr_ch['lower']
        mid = curr_ch['mid']

        # Calculate ADX if filter is active
        adx_value = 0.0
        if self.adx_min > 0:
            adx_value = self.calculate_adx(bars, self.adx_period)
            self.adx_cache[symbol] = adx_value

        # Cache channel values
        self.channel_cache[symbol] = {
            'upper': upper,
            'lower': lower,
            'mid': mid,
            'price': current_price,
            'period': period,
            'adx': adx_value,
            'updated': datetime.now().isoformat()
        }

        # Track bar count for cooldown
        self.bar_counter[symbol] = self.bar_counter.get(symbol, 0) + 1

        # Update position tracking
        if current_position:
            self.current_position[symbol] = current_position

        position = self.current_position.get(symbol)

        # Check for exit signals first
        if position == "LONG":
            exit_signal = self._check_exit_long(
                symbol, current_price, current_low, upper, lower, mid,
                prev_ch, current_bar_time
            )
            if exit_signal:
                self.last_exit_bar_index[symbol] = self.bar_counter[symbol]
                return exit_signal

        elif position == "SHORT":
            exit_signal = self._check_exit_short(
                symbol, current_price, current_high, upper, lower, mid,
                prev_ch, current_bar_time
            )
            if exit_signal:
                self.last_exit_bar_index[symbol] = self.bar_counter[symbol]
                return exit_signal

        # Check for entry signals only if no position
        if position is None:
            entry_signal = self._check_entry(
                symbol, current_price, current_high, current_low,
                upper, lower, mid, current_bar_time, adx_value
            )
            if entry_signal:
                return entry_signal

        # No signal
        return Signal(
            action=SignalType.HOLD,
            symbol=symbol,
            reason="No signal",
            strength=0.0,
            upper_channel=upper,
            lower_channel=lower,
            mid_channel=mid,
            price=current_price,
            timestamp=datetime.now().isoformat(),
            bar_time=current_bar_time
        )

    def _check_entry(self, symbol: str, price: float, high: float, low: float,
                     upper: float, lower: float, mid: float,
                     bar_time: str, adx_value: float = 0.0) -> Optional[Signal]:
        """Check for breakout entry signals with ADX, close confirm, cooldown filters"""

        if not self.trading_enabled:
            return None

        # Prevent duplicate signals on same bar
        if self.prevent_duplicates:
            if self.last_signal_bar.get(symbol) == bar_time:
                return None

        # ADX filter: skip entry if trend too weak
        if self.adx_min > 0 and adx_value < self.adx_min:
            return None

        # Cooldown filter: skip if too soon after last exit
        if self.cooldown_bars > 0:
            last_exit = self.last_exit_bar_index.get(symbol, -999)
            current_bar_idx = self.bar_counter.get(symbol, 0)
            if (current_bar_idx - last_exit) < self.cooldown_bars:
                return None

        # Breakout conditions (close_confirm requires close beyond channel)
        if self.close_confirm:
            buy_condition = price > upper
            sell_condition = price < lower
        else:
            buy_condition = high >= upper
            sell_condition = low <= lower

        # BULLISH BREAKOUT
        if buy_condition:
            if self.direction in ['both', 'long']:
                strength = self._calculate_strength(price, upper, lower)
                reason = f"Bullish breakout: {'Close' if self.close_confirm else 'High'} {price if self.close_confirm else high:.5f} {'>' if self.close_confirm else '>='} Upper({upper:.5f})"
                if self.adx_min > 0:
                    reason += f" ADX={adx_value:.1f}"
                signal = Signal(
                    action=SignalType.BUY,
                    symbol=symbol,
                    reason=reason,
                    strength=strength,
                    upper_channel=upper,
                    lower_channel=lower,
                    mid_channel=mid,
                    price=price,
                    timestamp=datetime.now().isoformat(),
                    bar_time=bar_time
                )
                self.last_signal[symbol] = signal
                self.last_signal_bar[symbol] = bar_time
                logger.info(f"[{symbol}] BUY signal: {signal.reason}")
                return signal

        # BEARISH BREAKOUT
        if sell_condition:
            if self.direction in ['both', 'short']:
                strength = self._calculate_strength(price, upper, lower)
                reason = f"Bearish breakout: {'Close' if self.close_confirm else 'Low'} {price if self.close_confirm else low:.5f} {'<' if self.close_confirm else '<='} Lower({lower:.5f})"
                if self.adx_min > 0:
                    reason += f" ADX={adx_value:.1f}"
                signal = Signal(
                    action=SignalType.SELL,
                    symbol=symbol,
                    reason=reason,
                    strength=strength,
                    upper_channel=upper,
                    lower_channel=lower,
                    mid_channel=mid,
                    price=price,
                    timestamp=datetime.now().isoformat(),
                    bar_time=bar_time
                )
                self.last_signal[symbol] = signal
                self.last_signal_bar[symbol] = bar_time
                logger.info(f"[{symbol}] SELL signal: {signal.reason}")
                return signal

        return None

    def _check_exit_long(self, symbol: str, price: float, low: float,
                         upper: float, lower: float, mid: float,
                         prev_ch: Dict, bar_time: str) -> Optional[Signal]:
        """Check for exit signals for long positions"""

        reasons = []

        # Exit on mid-line cross
        if self.exit_on_mid_cross:
            if price < mid:
                reasons.append(f"Price {price:.5f} below mid channel ({mid:.5f})")

        # Exit on opposite breakout
        if self.exit_on_opposite_breakout:
            if low <= lower:
                reasons.append(f"Bearish breakout: Low {low:.5f} <= Lower({lower:.5f})")

        if reasons:
            signal = Signal(
                action=SignalType.EXIT_LONG,
                symbol=symbol,
                reason=" | ".join(reasons),
                strength=1.0,
                upper_channel=upper,
                lower_channel=lower,
                mid_channel=mid,
                price=price,
                timestamp=datetime.now().isoformat(),
                bar_time=bar_time
            )
            self.current_position[symbol] = None
            logger.info(f"[{symbol}] EXIT_LONG signal: {signal.reason}")
            return signal

        return None

    def _check_exit_short(self, symbol: str, price: float, high: float,
                          upper: float, lower: float, mid: float,
                          prev_ch: Dict, bar_time: str) -> Optional[Signal]:
        """Check for exit signals for short positions"""

        reasons = []

        # Exit on mid-line cross
        if self.exit_on_mid_cross:
            if price > mid:
                reasons.append(f"Price {price:.5f} above mid channel ({mid:.5f})")

        # Exit on opposite breakout
        if self.exit_on_opposite_breakout:
            if high >= upper:
                reasons.append(f"Bullish breakout: High {high:.5f} >= Upper({upper:.5f})")

        if reasons:
            signal = Signal(
                action=SignalType.EXIT_SHORT,
                symbol=symbol,
                reason=" | ".join(reasons),
                strength=1.0,
                upper_channel=upper,
                lower_channel=lower,
                mid_channel=mid,
                price=price,
                timestamp=datetime.now().isoformat(),
                bar_time=bar_time
            )
            self.current_position[symbol] = None
            logger.info(f"[{symbol}] EXIT_SHORT signal: {signal.reason}")
            return signal

        return None

    def _calculate_strength(self, price: float, upper: float, lower: float) -> float:
        """
        Calculate signal strength based on channel width relative to price

        Returns:
            float: 0.0 to 1.0
        """
        if lower == 0 or upper == lower:
            return 0.0

        channel_width_pct = (upper - lower) / lower * 100
        # Wider channel = stronger breakout signal
        # Normalize: 2% channel width = 1.0 strength
        strength = min(channel_width_pct / 2.0, 1.0)
        return strength

    def get_channel_values(self, symbol: str) -> Optional[Dict]:
        """Get cached channel values for a symbol"""
        return self.channel_cache.get(symbol)

    def set_position(self, symbol: str, position_type: Optional[str]):
        """Update position tracking"""
        self.current_position[symbol] = position_type

    def set_trading_enabled(self, enabled: bool):
        """Enable or disable trading signals"""
        self.trading_enabled = enabled
        logger.info(f"Trading {'enabled' if enabled else 'disabled'}")

    def set_direction(self, direction: str):
        """Set trading direction filter"""
        if direction in ['both', 'long', 'short']:
            self.direction = direction
            logger.info(f"Direction set to: {direction}")

    def get_strategy_status(self) -> Dict:
        """Get current strategy status for dashboard"""
        return {
            "channel_period": self.channel_period,
            "direction": self.direction,
            "trading_enabled": self.trading_enabled,
            "prevent_duplicates": self.prevent_duplicates,
            "adx_min": self.adx_min,
            "close_confirm": self.close_confirm,
            "cooldown_bars": self.cooldown_bars,
            "exit_on_mid_cross": self.exit_on_mid_cross,
            "exit_on_opposite_breakout": self.exit_on_opposite_breakout,
            "positions": dict(self.current_position),
            "adx_values": dict(self.adx_cache),
            "channel_cache": dict(self.channel_cache)
        }

    def analyze_channel_state(self, symbol: str) -> Dict:
        """
        Analyze current channel state for dashboard display

        Returns:
            Dict: {'position_in_channel': 'UPPER'/'MID'/'LOWER', 'channel_width': float}
        """
        cache = self.channel_cache.get(symbol)
        if not cache or cache.get('upper') is None:
            return {"position_in_channel": "N/A", "channel_width": 0.0}

        price = cache['price']
        upper = cache['upper']
        lower = cache['lower']
        mid = cache['mid']

        channel_width = upper - lower

        if price >= upper:
            pos = "ABOVE_UPPER"
        elif price > mid:
            pos = "UPPER_HALF"
        elif price == mid:
            pos = "MID"
        elif price > lower:
            pos = "LOWER_HALF"
        else:
            pos = "BELOW_LOWER"

        return {
            "position_in_channel": pos,
            "channel_width": channel_width,
            "channel_width_pct": (channel_width / lower * 100) if lower > 0 else 0
        }


def test_strategy():
    """Quick test of Donchian strategy with sample data"""
    from datetime import timedelta
    import random

    bars = []
    base_price = 30.0

    for i in range(100):
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

    # Test with inline config
    strategy = DonchianStrategy.__new__(DonchianStrategy)
    strategy.channel_period = 20
    strategy.direction = 'both'
    strategy.prevent_duplicates = True
    strategy.min_bars_between = 0
    strategy.trading_enabled = True
    strategy.exit_on_mid_cross = True
    strategy.exit_on_opposite_breakout = True
    strategy.symbol_settings = {}
    strategy.last_signal = {}
    strategy.last_signal_bar = {}
    strategy.current_position = {}
    strategy.channel_cache = {}
    strategy.config = {}

    signal = strategy.analyze("XAUUSD", bars)

    print("\n" + "=" * 50)
    print("DONCHIAN STRATEGY TEST")
    print("=" * 50)
    print(f"Signal: {signal.action.value}")
    print(f"Reason: {signal.reason}")
    print(f"Strength: {signal.strength:.2f}")
    print(f"Upper: {signal.upper_channel:.5f}")
    print(f"Lower: {signal.lower_channel:.5f}")
    print(f"Mid:   {signal.mid_channel:.5f}")
    print(f"Price: {signal.price:.5f}")
    print("=" * 50)


if __name__ == "__main__":
    test_strategy()
