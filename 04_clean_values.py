import pandas as pd
from pathlib import Path
from word_number import words_to_number

pd.set_option('display.max_columns', None)   
pd.set_option('display.width', 200)         

#1) LOAD AND MERGE ============
files = sorted(Path('data').glob('T*-2026.csv'))
all_df = pd.concat(
    [pd.read_csv(f, dtype=str, encoding='utf-8-sig').assign(Source=f.stem) for f in files],
    ignore_index=True)
all_df.columns = all_df.columns.str.strip()        
all_df = all_df.replace(r'^\s*$', pd.NA, regex=True) 
print(f'Total rows: {len(all_df)}')                  

#2) FORMAT FINGERPRINTS  ============
def fingerprint(series):
    return series.str.replace(r'\d+', '9', regex=True).value_counts(dropna=False)

print('\n--- Quantity shapes ---')
print(fingerprint(all_df['Quantity']))
print('\n--- Unit Price shapes ---')
print(fingerprint(all_df['Unit Price (USD)']))
print('\n--- Order Date shapes ---')
print(fingerprint(all_df['Order Date']))

#3) ORDER ID ============
all_df['ID_Clean'] = all_df['Order ID'].str.replace(
    r'(?i)^\s*ORD\D*(\d{6})\D*(\d{4})\s*$', r'ORD-\1-\2', regex=True)

bad_id = ~all_df['ID_Clean'].str.match(r'^ORD-\d{6}-\d{4}$', na=False)   
print(f'\nInvalid IDs after cleaning: {bad_id.sum()}')                  

#4) QUANTITY ============
qty_text = all_df['Quantity'].str.lower().str.strip()
qty_num  = pd.to_numeric(qty_text.str.extract(r'(-?\d+(?:\.\d+)?)')[0], errors='coerce')

still_empty = qty_num.isna() & qty_text.notna()                 # only try words where digits failed
qty_word = qty_text[still_empty].map(words_to_number)

all_df['Qty_Clean'] = qty_num.fillna(qty_word) 

#5) UNIT PRICE ============
print('\nPrices containing a comma:', all_df['Unit Price (USD)'].str.contains(',', na=False).sum())
all_df['Price_Clean'] = pd.to_numeric(
    all_df['Unit Price (USD)'].str.replace(r'[^\d.\-]', '', regex=True), errors='coerce')

#6) ORDER DATE ============
all_df['Date_Clean'] = pd.to_datetime(
    all_df['Order Date'], errors='coerce', format='mixed', dayfirst=True)

#7) WHAT FAILED?  ============
print('\n--- Cells that could not be converted ---')
for raw_col, new_col in [('Quantity', 'Qty_Clean'),
                         ('Unit Price (USD)', 'Price_Clean'),
                         ('Order Date', 'Date_Clean')]:
    failed = all_df[raw_col].notna() & all_df[new_col].isna()
    print(f'{raw_col:<18} failed: {failed.sum():<4} | originally empty: {all_df[raw_col].isna().sum()}')
    if failed.sum() > 0:
        print(all_df.loc[failed, ['Order ID', raw_col, 'Source']].head(5))

#8) SANITY CHECKS ============
print('\n--- Qty_Clean / Price_Clean summary ---')
print(all_df[['Qty_Clean', 'Price_Clean']].describe())

print('\nQuantity <= 0:        ', (all_df['Qty_Clean'] <= 0).sum())
print('Quantity not integer: ', (all_df['Qty_Clean'] % 1 != 0).sum())
print('Price <= 0:           ', (all_df['Price_Clean'] <= 0).sum())

id_month = all_df['ID_Clean'].str[4:10]                   
date_month = all_df['Date_Clean'].dt.strftime('%Y%m')
mismatch = id_month.notna() & date_month.notna() & (id_month != date_month)
print(f'\nID month != date month: {mismatch.sum()}')
print(all_df.loc[mismatch, ['ID_Clean', 'Order Date', 'Date_Clean', 'Source']].head(10))

print('\n--- Before => After (first 8 rows) ---')
print(all_df[['Quantity', 'Qty_Clean', 'Unit Price (USD)', 'Price_Clean',
              'Order Date', 'Date_Clean']].head(8))