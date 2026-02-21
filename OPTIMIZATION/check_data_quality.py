"""
Script: check_data_quality.py
Description:
    Scans CSV files in 'dataticks/' and reports on data quality:
    - Time coverage (Start/End dates, Total Days)
    - Row counts
    - Data gaps (missing bars)

Usage:
    python3 check_data_quality.py

Outputs:
    - Console summary table
    - filtered_symbols_quality.csv (Detailed report)
"""

import os
import pandas as pd
import glob
from datetime import datetime, timedelta
import numpy as np

# Configuration
DATA_DIR = "dataticks"
GAP_THRESHOLD_MULTIPLIER = 5  # Flag gap if > 5x timeframe duration
MIN_DAYS_REQUIRED = 150 # Warn if less than 5 months (approx) for M1/M5? Or just report.

TIMEFRAME_MINUTES = {
    '1m': 1,
    '5m': 5,
    '15m': 15,
    '1h': 60,
    '4h': 240,
    'M5': 5 # Legacy from old filenames if any
}

def analyze_file(filepath):
    """Analyzes a single CSV file for quality metrics."""
    filename = os.path.basename(filepath)
    parts = filename.replace('.csv', '').split('_')
    
    if len(parts) < 2:
        return None
        
    symbol = parts[0]
    tf_str = parts[-1]
    
    # Handle filename variations (e.g. Symbol_1m.csv vs Symbol_TF_1m.csv)
    # The current download script uses {Symbol}_{Timeframe}.csv
    # But some symbols might have underscores in name?
    # Let's assume last part is timeframe.
    
    if tf_str not in TIMEFRAME_MINUTES:
        # Try second to last if exists?
        # For now, stick to known suffix
        return {'Symbol': symbol, 'Timeframe': tf_str, 'Status': 'Unknown TF'}

    tf_minutes = TIMEFRAME_MINUTES[tf_str]
    
    try:
        df = pd.read_csv(filepath)
        if 'time' not in df.columns:
            return {'Symbol': symbol, 'Timeframe': tf_str, 'Status': 'No time col'}
            
        if len(df) == 0:
            return {'Symbol': symbol, 'Timeframe': tf_str, 'Status': 'Empty'}
            
        # Convert time
        df['time'] = pd.to_datetime(df['time'])
        df = df.sort_values('time')
        
        start_date = df['time'].iloc[0]
        end_date = df['time'].iloc[-1]
        duration = end_date - start_date
        total_days = duration.total_seconds() / 86400
        
        # Gap Detection
        # Calculate time difference between rows
        time_diffs = df['time'].diff().dropna()
        
        # Expected diff is tf_minutes in timedelta
        expected_diff = timedelta(minutes=tf_minutes)
        threshold = expected_diff * GAP_THRESHOLD_MULTIPLIER
        
        # Find gaps larger than threshold
        gaps = time_diffs[time_diffs > threshold]
        gap_count = len(gaps)
        max_gap = gaps.max() if gap_count > 0 else timedelta(0)
        
        # Format max gap nicely
        def format_td(td):
            days = td.days
            hours, remainder = divmod(td.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            if days > 0: return f"{days}d {hours}h"
            if hours > 0: return f"{hours}h {minutes}m"
            return f"{minutes}m"

        max_gap_str = format_td(max_gap)
        
        return {
            'Symbol': symbol,
            'Timeframe': tf_str,
            'Rows': len(df),
            'Start_Date': start_date.strftime('%Y-%m-%d'),
            'End_Date': end_date.strftime('%Y-%m-%d'),
            'Total_Days': round(total_days, 1),
            'Gaps': gap_count,
            'Max_Gap': max_gap_str if gap_count > 0 else "None",
            'Status': 'OK'
        }

    except Exception as e:
        return {'Symbol': symbol, 'Timeframe': tf_str, 'Status': f"Error: {str(e)}"}

def main():
    print(f"Scanning '{DATA_DIR}' for CSV files...")
    
    all_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    if not all_files:
        print("No files found.")
        return
        
    print(f"Found {len(all_files)} files. Analyzing data quality...")
    
    results = []
    
    for i, filepath in enumerate(all_files):
        if i % 10 == 0:
            print(f"Processing {i}/{len(all_files)}...", end='\r')
            
        res = analyze_file(filepath)
        if res:
            results.append(res)
            
    print(f"Processing complete.                 ")
    
    df_res = pd.DataFrame(results)
    
    # Display Summary
    # Group by timeframe to show average health
    print("\n--- Summary by Timeframe ---")
    if not df_res.empty:
        summary = df_res.groupby('Timeframe').agg({
            'Rows': 'mean',
            'Total_Days': 'mean',
            'Gaps': 'mean',
            'Symbol': 'count'
        }).round(1)
        print(summary)
    
    # Identify Issues
    print("\n--- Potential Issues ---")
    
    # 1. Very short duration
    short_data = df_res[df_res['Total_Days'] < 30]
    if not short_data.empty:
        print(f"\n[WARNING] Symbols with < 30 days of data ({len(short_data)}):")
        print(short_data[['Symbol', 'Timeframe', 'Rows', 'Total_Days', 'Start_Date']].head(10).to_string(index=False))
        if len(short_data) > 10: print("...")

    # 2. Large gaps
    # Filter out normal weekend gaps (approx 2 days)
    # 2 days = 48 hours. Let's flag gaps > 3 days just to catch major missing blocks.
    # But Max_Gap is string. We need accurate check.
    # Re-process? No, let's just use Gaps count for now or look at raw data if needed.
    # Or just list top gap offenders.
    
    print("\n[INFO] Top 10 Files with most gaps:")
    top_gaps = df_res.sort_values('Gaps', ascending=False).head(10)
    print(top_gaps[['Symbol', 'Timeframe', 'Gaps', 'Max_Gap', 'Total_Days']].to_string(index=False))

    # Save details
    output_file = "data_quality_report.csv"
    df_res.to_csv(output_file, index=False)
    print(f"\nDetailed report saved to: {output_file}")

if __name__ == "__main__":
    main()
