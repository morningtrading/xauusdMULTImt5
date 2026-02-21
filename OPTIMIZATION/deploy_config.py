
import shutil
import sys
from pathlib import Path

def main():
    # Source: The config inside the OPTIMIZATION folder
    src_config = Path("config/trading_config.json")
    
    # Destination: The live bot's config folder (parent of OPTIMIZATION/config/..)
    # Assuming this script is run from inside OPTIMIZATION/
    # .. which means start_EMAXSTF/OPTIMIZATION/
    # So live config is ../config/trading_config.json
    
    # However, let's be robust about where we are running from.
    # If running from start_EMAXSTF/:
    #   src = OPTIMIZATION/config/trading_config.json
    #   dst = config/trading_config.json
    
    cwd = Path.cwd()
    
    if (cwd / "OPTIMIZATION").exists():
        # Running from Root
        src = cwd / "OPTIMIZATION" / "config" / "trading_config.json"
        dst = cwd / "config" / "trading_config.json"
    elif (cwd / "config").exists() and (cwd / "optimize.py").exists():
        # Running from Inside OPTIMIZATION
        src = cwd / "config" / "trading_config.json"
        dst = cwd.parent / "config" / "trading_config.json"
    else:
        print("Error: Could not determine context. Run from 'start_EMAXSTF' or 'start_EMAXSTF/OPTIMIZATION'.")
        return

    if not src.exists():
        print(f"Error: Source config not found at {src}")
        return
        
    print(f"Deploying Configuration...")
    print(f"  Source:      {src}")
    print(f"  Destination: {dst}")
    
    confirm = input("Are you sure you want to overwrite the LIVE bot configuration? (y/n): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return
        
    shutil.copy2(src, dst)
    print("Success! Live configuration updated.")
    print("Please restart the bot for changes to take effect.")

if __name__ == "__main__":
    main()
