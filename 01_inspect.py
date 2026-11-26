import pandas as pd
from pathlib import Path
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)

FOLDER = 'data' 
XLSX = None 
if XLSX:
    sheets = pd.read_excel(XLSX, sheet_name=None, dtype=str)
else:
    sheets = {f.stem: pd.read_csv(f, dtype=str, encoding='utf-8-sig')
for f in sorted(Path(FOLDER).glob('*.csv'))}
    print('=== ROWS / COLUMNS PER TABLE ===')
for name, d in sheets.items():
    print(name, d.shape)

all_df = pd.concat([d.assign(Source=n) for n, d in sheets.items()], ignore_index=True)
all_df.columns = all_df.columns.str.strip()

print('\n=== COLUMNS ===', all_df.columns.tolist())

print('\n=== FIRST 5 / LAST 5 ===')
print(all_df.head())
print(all_df.tail())

print('\n=== MISSING PER COLUMN ===')
print(all_df.isna().sum())
cols = [c for c in all_df.columns if c != 'Source']

print('\n=== EXACT DUPLICATES ===', all_df.duplicated(subset=cols).sum())
print(all_df[all_df.duplicated(subset=cols, keep=False)].head(20))