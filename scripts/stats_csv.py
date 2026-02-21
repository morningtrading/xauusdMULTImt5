
import pandas as pd
import sys
import os

TARGET_CSV = "filtered_symbols_20260218_195101.csv"

def main():
    if not os.path.exists(TARGET_CSV):
        print(f"File {TARGET_CSV} not found.")
        return

    df = pd.read_csv(TARGET_CSV)
    
    total = len(df)
    print(f"Total Symbols: {total}")
    print("-" * 30)
    
    counts = df['Type'].value_counts()
    
    print(f"{'Type':<15} | {'Count':<5} | {'%':<5}")
    print("-" * 30)
    
    for type_name, count in counts.items():
        percent = (count / total) * 100
        print(f"{type_name:<15} | {count:<5} | {percent:.1f}%")
        
if __name__ == "__main__":
    main()
