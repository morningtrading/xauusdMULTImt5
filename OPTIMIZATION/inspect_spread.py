import pandas as pd

try:
    df = pd.read_csv('volatility_scan_20260216_175304.csv')
    print("Unique Spread values:", df['Spread'].unique())
    print("Count of symbols with Spread < 0.15:", len(df[df['Spread'] < 0.15]))
    print("Mean Spread:", df['Spread'].mean())
    
    # Also check if there is a 'Spread%' column or similar if I missed it
    print("Columns:", df.columns)
except Exception as e:
    print(e)
