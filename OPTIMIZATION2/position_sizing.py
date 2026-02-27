"""
Position Sizing Module - Fixed Cash Risk per Trade

Calculates lot size based on:
- Fixed dollar risk (e.g., $20 per trade)
- ATR-based stop distance
- Account currency and symbol specifications
"""

import numpy as np

def calculate_lot_size(
    risk_amount_usd,
    atr_value,
    atr_multiplier,
    point_value,
    pip_size=0.0001,
    account_currency='USD',
    quote_currency='USD',
    min_lot=0.01,
    max_lot=100.0
):
    """
    Calculate lot size for fixed cash risk.
    
    Args:
        risk_amount_usd: Fixed risk per trade in USD (e.g., 20.0)
        atr_value: Current ATR value in price units
        atr_multiplier: Stop distance in ATR multiples (e.g., 2.0)
        point_value: Pip/point value for the symbol
        pip_size: Size of one pip (0.0001 for most FX, 0.01 for JPY pairs)
        account_currency: Account denomination (USD, EUR, etc.)
        quote_currency: Symbol quote currency
        min_lot: Minimum lot size
        max_lot: Maximum lot size
        
    Returns:
        float: Lot size rounded to 2 decimals
    """
    
    # Stop distance in price units
    stop_distance = atr_value * atr_multiplier
    
    # Stop distance in pips
    stop_distance_pips = stop_distance / pip_size
    
    # Value per pip for 1 lot
    # For forex: standard lot = 100,000 units
    # For stocks/indices: depends on contract specifications
    value_per_pip_per_lot = point_value
    
    # Calculate lot size
    # Risk = Lot_Size × Stop_Distance_Pips × Value_Per_Pip
    # Lot_Size = Risk / (Stop_Distance_Pips × Value_Per_Pip)
    
    if stop_distance_pips == 0:
        return min_lot
    
    lot_size = risk_amount_usd / (stop_distance_pips * value_per_pip_per_lot)
    
    # Clamp to min/max
    lot_size = max(min_lot, min(lot_size, max_lot))
    
    # Round to 2 decimals
    lot_size = round(lot_size, 2)
    
    return lot_size


def calculate_position_size_forex(
    risk_amount_usd,
    atr_value,
    atr_multiplier=2.0,
    pip_size=0.0001,
    min_lot=0.01,
    max_lot=100.0
):
    """
    Simplified position sizing for forex pairs.
    
    For standard forex pairs:
    - 1 standard lot = 100,000 units
    - 1 pip on 1 standard lot = $10 for xxx/USD pairs
    - For other pairs, adjust accordingly
    """
    
    stop_distance_pips = (atr_value / pip_size) * atr_multiplier
    
    if stop_distance_pips == 0:
        return min_lot
    
    # For forex, assume $10 per pip per standard lot
    value_per_pip = 10.0
    
    # Calculate in standard lots, then convert to mini lots
    lot_size = risk_amount_usd / (stop_distance_pips * value_per_pip)
    
    # Clamp
    lot_size = max(min_lot, min(lot_size, max_lot))
    
    return round(lot_size, 2)


def calculate_position_size_stocks(
    risk_amount_usd,
    current_price,
    atr_value,
    atr_multiplier=2.0,
    min_shares=1,
    max_shares=10000
):
    """
    Position sizing for stocks/ETFs.
    
    Args:
        risk_amount_usd: Fixed risk in USD
        current_price: Current stock price
        atr_value: ATR in price units
        atr_multiplier: Stop distance multiplier
    
    Returns:
        int: Number of shares
    """
    
    stop_distance = atr_value * atr_multiplier
    
    if stop_distance == 0:
        return min_shares
    
    # Risk = Shares × Stop_Distance
    shares = risk_amount_usd / stop_distance
    
    # Round to integer
    shares = int(max(min_shares, min(shares, max_shares)))
    
    return shares


def calculate_position_size_crypto(
    risk_amount_usd,
    current_price,
    atr_value,
    atr_multiplier=2.0,
    min_units=0.001,
    max_units=100.0
):
    """
    Position sizing for cryptocurrencies.
    
    Similar to stocks but allows fractional units.
    """
    
    stop_distance = atr_value * atr_multiplier
    
    if stop_distance == 0:
        return min_units
    
    # Risk = Units × Stop_Distance
    units = risk_amount_usd / stop_distance
    
    # Clamp and round to 3 decimals
    units = max(min_units, min(units, max_units))
    units = round(units, 3)
    
    return units


def calculate_position_size_auto(
    symbol,
    risk_amount_usd,
    current_price,
    atr_value,
    atr_multiplier=2.0,
    point_value=None
):
    """
    Auto-detect symbol type and calculate position size.
    
    Args:
        symbol: Symbol name (e.g., 'EURUSD', 'AAPL', 'BTCUSD')
        risk_amount_usd: Fixed risk per trade
        current_price: Current price
        atr_value: ATR value
        atr_multiplier: Stop multiplier
        point_value: Override point value if known
        
    Returns:
        dict: {'lots': float, 'type': str, 'stop_distance': float}
    """
    
    symbol_upper = symbol.upper()
    
    # Detect symbol type
    if 'BTC' in symbol_upper or 'ETH' in symbol_upper or 'LTC' in symbol_upper:
        # Crypto
        units = calculate_position_size_crypto(
            risk_amount_usd, current_price, atr_value, atr_multiplier
        )
        return {
            'lots': units,
            'type': 'crypto',
            'stop_distance': atr_value * atr_multiplier,
            'stop_price': current_price - (atr_value * atr_multiplier)
        }
    
    elif any(fx in symbol_upper for fx in ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF']):
        # Forex
        pip_size = 0.01 if 'JPY' in symbol_upper else 0.0001
        lots = calculate_position_size_forex(
            risk_amount_usd, atr_value, atr_multiplier, pip_size
        )
        return {
            'lots': lots,
            'type': 'forex',
            'stop_distance': atr_value * atr_multiplier,
            'stop_pips': (atr_value * atr_multiplier) / pip_size
        }
    
    else:
        # Stocks/Indices/Commodities
        shares = calculate_position_size_stocks(
            risk_amount_usd, current_price, atr_value, atr_multiplier
        )
        return {
            'lots': shares,
            'type': 'stock',
            'stop_distance': atr_value * atr_multiplier,
            'stop_price': current_price - (atr_value * atr_multiplier)
        }


# Example usage
if __name__ == "__main__":
    print("Position Sizing Examples:")
    print("-" * 60)
    
    # Example 1: EURUSD
    print("\n1. EURUSD Forex:")
    result = calculate_position_size_auto(
        symbol='EURUSD',
        risk_amount_usd=20.0,
        current_price=1.0850,
        atr_value=0.0015,
        atr_multiplier=2.0
    )
    print(f"   Risk: $20, ATR: 0.0015, Stop: {result['stop_pips']:.1f} pips")
    print(f"   Position: {result['lots']} lots")
    
    # Example 2: BTCUSD
    print("\n2. BTCUSD Crypto:")
    result = calculate_position_size_auto(
        symbol='BTCUSD',
        risk_amount_usd=20.0,
        current_price=45000,
        atr_value=1500,
        atr_multiplier=2.0
    )
    print(f"   Risk: $20, ATR: 1500, Stop: ${result['stop_distance']:.0f}")
    print(f"   Position: {result['lots']} BTC")
    
    # Example 3: AAPL
    print("\n3. AAPL Stock:")
    result = calculate_position_size_auto(
        symbol='AAPL',
        risk_amount_usd=20.0,
        current_price=180.0,
        atr_value=3.5,
        atr_multiplier=2.0
    )
    print(f"   Risk: $20, ATR: 3.5, Stop: ${result['stop_distance']:.2f}")
    print(f"   Position: {result['lots']} shares")
    
    # Example 4: XAUUSD (Gold)
    print("\n4. XAUUSD Gold:")
    result = calculate_position_size_auto(
        symbol='XAUUSD',
        risk_amount_usd=20.0,
        current_price=2050.0,
        atr_value=15.0,
        atr_multiplier=2.0
    )
    print(f"   Risk: $20, ATR: 15, Stop: ${result['stop_distance']:.2f}")
    print(f"   Position: {result['lots']} oz")
