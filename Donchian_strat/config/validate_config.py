"""
================================================================================
CONFIG VALIDATOR - Donchian Trading Engine
================================================================================

PURPOSE:
    Validates the 'trading_config.json' file against a strict schema to prevent
    runtime errors caused by missing or invalid configuration parameters.
    Ensures critical safety settings (like demo_only) are present.

INPUTS:
    - Path to trading_config.json

OUTPUTS:
    - Boolean: True if valid, False if invalid
    - Prints validation errors to console/log

CONTEXT:
    This module should be run:
    1. On engine startup (by main.py)
    2. Before reloading config (live reload)
    3. As a CI/CD check

INSTALLATION:
    No external dependencies required (uses standard json and typing).

USAGE:
    from config.validate_config import validate_config
    if validate_config('config/trading_config.json'):
        print("Config matches schema")

VERSION HISTORY:
    1.0.0 (2026-01-28) - Initial creation

AUTHOR: Donchian Trading Engine
================================================================================
"""

import json
import logging
import os
import sys

# Add parent directory to path to import constants
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.constants import LIMITS, DEFAULTS

# Configure logging
logger = logging.getLogger('ConfigValidator')
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

def validate_config(config_path: str) -> bool:
    """
    Validates the trading configuration file.
    
    Args:
        config_path: Path to the JSON configuration file.
        
    Returns:
        True if valid, False otherwise.
    """
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        return False

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format: {e}")
        return False
    except Exception as e:
        logger.error(f"Error reading config: {e}")
        return False

    is_valid = True
    
    # 1. Validate Account Section
    if 'account' not in config:
        logger.error("Missing required section: 'account'")
        is_valid = False
    else:
        account = config['account']
        if 'demo_only' not in account:
            logger.error("Missing 'account.demo_only' - CRITICAL SAFETY SETTING")
            is_valid = False
        
        # Check limits
        if account.get('max_daily_loss_percent', 0) > LIMITS['MAX_DAILY_LOSS_PERCENT']:
             logger.warning(f"max_daily_loss_percent exceeds safety limit ({LIMITS['MAX_DAILY_LOSS_PERCENT']}%)")

    # 2. Validate Symbols Section
    if 'symbols' not in config:
        logger.error("Missing required section: 'symbols'")
        is_valid = False
    else:
        symbols = config['symbols']
        if 'enabled' not in symbols or not isinstance(symbols['enabled'], list):
            logger.error("'symbols.enabled' must be a list")
            is_valid = False
        
        if 'settings' not in symbols:
            logger.error("'symbols.settings' section missing")
            is_valid = False
        else:
            # Validate individual symbol settings if they exist
            for sym, settings in symbols['settings'].items():
                if 'volume' in settings:
                    vol = settings['volume']
                    if vol < LIMITS['MIN_LOT_SIZE'] or vol > LIMITS['MAX_LOT_SIZE']:
                         logger.error(f"Symbol {sym} volume {vol} out of bounds ({LIMITS['MIN_LOT_SIZE']}-{LIMITS['MAX_LOT_SIZE']})")
                         is_valid = False

    # 3. Validate Strategy Section
    if 'strategy' not in config:
        logger.error("Missing required section: 'strategy'")
        is_valid = False
    
    # 4. Validate Dashboard Section (Optional but recommended)
    if 'dashboard' in config:
        port = config['dashboard'].get('web_port')
        if port and not isinstance(port, int):
             logger.error("'dashboard.web_port' must be an integer")
             is_valid = False

    if is_valid:
        logger.info(f"Configuration {config_path} is VALID.")
    else:
        logger.error(f"Configuration {config_path} is INVALID.")

    return is_valid

if __name__ == "__main__":
    # Test run
    path = os.path.join(os.path.dirname(__file__), 'trading_config.json')
    if validate_config(path):
        sys.exit(0)
    else:
        sys.exit(1)
