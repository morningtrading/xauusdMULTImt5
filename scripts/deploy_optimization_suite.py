
import os
import shutil
from pathlib import Path

def main():
    # 1. Create Target Directory
    target_dir = Path("OPTIMIZATION")
    if not target_dir.exists():
        target_dir.mkdir()
        print(f"Created {target_dir}")
        
    # 2. List of Files to Copy
    # (Source Path, Destination Relative Path)
    files_to_copy = [
        ("scripts/optimize_5m_walkforward.py", "optimize.py"),
        ("scripts/optimization_stats.py", "stats.py"),
        ("scripts/filter_symbols.py", "filter_symbols.py"),
        ("scripts/select_robust_core.py", "select_robust.py"),
        ("scripts/remove_losers.py", "remove_losers.py"),
        ("scripts/add_manual_symbols.py", "add_symbols.py"),
        ("scripts/download_market_data.py", "download_data.py"),
        ("config/trading_config.json", "trading_config.json"),
        ("inspect_spread.py", "inspect_spread.py"),
        ("menu.sh", "menu.sh") # useful reference
    ]
    
    # 3. Copy Files
    for src, dst_rel in files_to_copy:
        src_path = Path(src)
        dst_path = target_dir / dst_rel
        
        if src_path.exists():
            shutil.copy2(src_path, dst_path)
            print(f"Copied {src} -> {dst_path}")
        else:
            print(f"Warning: {src} not found!")

    # 4. Handle Directories (Core & Data)
    # We need 'core' for the scripts to work as they import from it
    core_src = Path("core")
    core_dst = target_dir / "core"
    if core_src.exists():
        if core_dst.exists():
            shutil.rmtree(core_dst)
        shutil.copytree(core_src, core_dst)
        print(f"Copied core/ -> {core_dst}")
        
    # We need 'dataticks' for local data
    data_src = Path("dataticks")
    data_dst = target_dir / "dataticks"
    if data_src.exists():
        if not data_dst.exists():
            # Use symlink to save space/time if possible, else copy
            try:
                os.symlink(os.path.abspath(data_src), data_dst)
                print(f"Symlinked dataticks/ -> {data_dst}")
            except OSError:
                shutil.copytree(data_src, data_dst)
                print(f"Copied dataticks/ -> {data_dst}")
    
    # 5. Create a README
    readme_content = """
# Optimization Suite

This directory contains a self-contained environment for optimizing the EMAX strategy.

## Usage

1. **Download Data:**
   `python download_data.py` (Downloads M5 history to dataticks/)

2. **Run Optimization:**
   `python optimize.py` (Walk-Forward Optimization on enabled symbols)

3. **Analyze Results:**
   `python stats.py` (View PnL, Win Rate, Drawdown)

4. **Refine Portfolio:**
   - `python remove_losers.py` (Remove worst performers)
   - `python select_robust.py` (Keep only symbols robust across splits)
   - `python add_symbols.py` (Manually add specific symbols)

## Configuration
Edit `trading_config.json` to change the list of enabled symbols or optimization parameters.
"""
    with open(target_dir / "README.md", "w") as f:
        f.write(readme_content)
    print(f"Created README.md")
    
    print("\nOptimization Suite Deployment Complete!")
    print(f"Location: {os.path.abspath(target_dir)}")

if __name__ == "__main__":
    main()
