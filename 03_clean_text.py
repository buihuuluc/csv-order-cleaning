import re
import unicodedata
import pandas as pd
from pathlib import Path

from lookups import CITY_ALIASES             

pd.set_option('display.max_columns', None)   
pd.set_option('display.width', 200)         

def city_key(text):
    """'Cần Thơ' -> 'cantho' | 'Tp.Hcm' -> 'tphcm' | missing -> None"""
    if pd.isna(text):
        return None
    t = str(text).lower().replace('đ', 'd')
    t = unicodedata.normalize('NFD', t)
    t = ''.join(ch for ch in t if not unicodedata.combining(ch))  
    return re.sub(r'[^a-z0-9]', '', t)

def squash(series):
    """Collapse any run of whitespace into one space, then trim."""
    return series.str.replace(r'\s+', ' ', regex=True).str.strip()

def sku_clean(series):
    """'sku1001', 'SKU 1001', 'SKU-1001' -> 'SKU-1001'"""
    return (series.str.strip().str.upper()
                  .str.replace(r'^SKU\D*(\d+)$', r'SKU-\1', regex=True))

#1) LOAD AND MERGE ============
files = sorted(Path('data').glob('T*-2026.csv'))
all_df = pd.concat(
    [pd.read_csv(f, dtype=str, encoding='utf-8-sig').assign(Source=f.stem) for f in files],
    ignore_index=True)
all_df.columns = all_df.columns.str.strip()        
all_df = all_df.replace(r'^\s*$', pd.NA, regex=True) 
print(f'Total rows: {len(all_df)}')               

raw = all_df.copy()                              

#2) SKU SHAPES ============
print('\n--- SKU shapes before (digits replaced by 9) ---')
print(raw['SKU'].str.replace(r'\d+', '9', regex=True).value_counts(dropna=False))

#3) CLEAN TEXT COLUMNS ============
all_df['Customer Name'] = squash(all_df['Customer Name']).str.title()
all_df['Company Name']  = squash(all_df['Company Name'])          
all_df['Email']         = (all_df['Email']
                           .str.replace(r'\s+', '', regex=True)    
                           .str.lower())

all_df['City'] = squash(all_df['City']).str.title()
keys = all_df['City'].map(city_key)
auto_name = all_df.groupby(keys)['City'].agg(lambda s: s.mode().iat[0])    
all_df['City'] = keys.map(CITY_ALIASES).fillna(keys.map(auto_name))       

# SKU
all_df['SKU_Clean'] = sku_clean(all_df['SKU'])

#4) Cells Change ============
pairs = [('Customer Name', 'Customer Name'), ('Company Name', 'Company Name'),
         ('City', 'City'), ('Email', 'Email'), ('SKU', 'SKU_Clean')]
print('\n--- Cells changed ---')
for before_col, after_col in pairs:
    changed = (raw[before_col].fillna('') != all_df[after_col].fillna('')).sum()
    print(f'{after_col:<15} {changed}')

print('\n--- City: before => after (only the ones that changed) ---')
review = (pd.DataFrame({'Before': raw['City'], 'After': all_df['City']})
          .dropna().value_counts().reset_index(name='Rows'))
print(review[review['Before'] != review['After']].sort_values('After').head(40))

print('\n--- SKU: before => after (first 10 that changed) ---')
sku_review = (pd.DataFrame({'Before': raw['SKU'], 'After': all_df['SKU_Clean']})
              .dropna().value_counts().reset_index(name='Rows'))
print(sku_review[sku_review['Before'] != sku_review['After']].head(10))

#5) SELF-CHECK ============
print('\n--- Self-check ---')
print('Names with extra spaces:    ', all_df['Customer Name'].str.contains(r'^\s|\s$|\s{2,}', na=False).sum())
print('Names not in Proper Case:   ', (all_df['Customer Name'].dropna() != all_df['Customer Name'].dropna().str.title()).sum())
print('Emails with uppercase:      ', (all_df['Email'].dropna() != all_df['Email'].dropna().str.lower()).sum())
print('Emails containing spaces:   ', all_df['Email'].str.contains(r'\s', na=False).sum())
print('SKU not matching SKU-digits:', (~all_df['SKU_Clean'].dropna().str.match(r'^SKU-\d+$')).sum())
print(f'Distinct cities: {raw["City"].nunique()} => {all_df["City"].nunique()}')
print(f'Distinct SKUs:   {raw["SKU"].nunique()} => {all_df["SKU_Clean"].nunique()}')

#6) Check it again ============
print('\n--- Final city list (look for names that still look like duplicates) ---')
print(all_df['City'].value_counts(dropna=False))

counts = all_df['City'].value_counts()
print('\n--- Rare city names (fewer than 10 rows): likely leftover variants ---')
print(counts[counts < 10])

email_pattern = r'^[\w.+-]+@[\w-]+\.[\w.-]+$'
bad_email = all_df['Email'].notna() & ~all_df['Email'].str.match(email_pattern, na=False)
print(f'\nEmails with invalid format (flagged in step 5): {bad_email.sum()}')
print(all_df.loc[bad_email, ['Email', 'Source']].head(10))