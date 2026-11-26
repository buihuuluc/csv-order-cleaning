import pandas as pd
from pathlib import Path

pd.set_option('display.max_columns', None)   
pd.set_option('display.width', 200)          

#1) LOAD AND MERGE ============
files = sorted(Path('data').glob('T*-2026.csv'))
all_df = pd.concat(
    [pd.read_csv(f, dtype=str, encoding='utf-8-sig').assign(Source=f.stem) for f in files],
    ignore_index=True)
all_df.columns = all_df.columns.str.strip()          
print(f'Total rows: {len(all_df)}')                  

#2) MISSING VALUES ============
all_df = all_df.replace(r'^\s*$', pd.NA, regex=True)

print('\n--- Missing per column ---')
print(all_df.isna().sum())

rows_missing = all_df[all_df.isna().any(axis=1)]     
print(f'\nRows with at least one empty cell: {len(rows_missing)}')
print(rows_missing.head(10))

#3) STANDARDIZE ORDER ID ============
all_df['ID_Clean'] = all_df['Order ID'].str.replace(
    r'(?i)^\s*ORD\D*(\d{6})\D*(\d{4})\s*$', r'ORD-\1-\2', regex=True)

#4) DUPLICATES ============
dup_by_id = all_df.duplicated(subset=['ID_Clean']).sum()
print(f'\nDuplicates by ID_Clean: {dup_by_id}')     

group = (all_df[all_df.duplicated(subset=['ID_Clean'], keep=False)]    
         .sort_values(['ID_Clean', 'Source']))
print('\n--- Duplicate groups (first 20 rows) ---')
print(group[['ID_Clean', 'Customer Name', 'Email', 'Quantity',
             'Unit Price (USD)', 'Source']].head(20))
print(f'Rows involved: {len(group)} | Unique IDs involved: {group["ID_Clean"].nunique()}')

cols_check = [c for c in all_df.columns if c not in ['Source', 'Order ID']]
exact_dup = all_df.duplicated(subset=cols_check).sum()
print(f'\nExact duplicate rows (identical in all columns): {exact_dup}')    
print('All duplicates are exact copies:', exact_dup == dup_by_id)