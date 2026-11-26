import re
import unicodedata
import pandas as pd
from pathlib import Path

from lookups import CITY_ALIASES             

pd.set_option('display.max_columns', None)   
pd.set_option('display.width', 200)          

#0) LOOKUP TABLES AND HELPERS ============
UNITS = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
         'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12,
         'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
         'seventeen': 17, 'eighteen': 18, 'nineteen': 19}
TENS = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
        'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90}
SCALES = {'thousand': 1_000, 'million': 1_000_000}

def words_to_number(text):
    """'twenty-five' -> 25 | 'two thousand five hundred' -> 2500 | 'abc' -> None"""
    if pd.isna(text):
        return None
    tokens = re.sub(r'[-,]', ' ', str(text).lower()).split()
    tokens = [t for t in tokens if t != 'and']
    total, current, found = 0, 0, False
    for t in tokens:
        if t in UNITS:
            current += UNITS[t]
        elif t in TENS:
            current += TENS[t]
        elif t == 'hundred':
            current = max(current, 1) * 100
        elif t in SCALES:
            total += max(current, 1) * SCALES[t]
            current = 0
        elif found:
            break
        else:
            return None
        found = True
    return total + current if found else None

def city_key(text):
    """'Cần Thơ' -> 'cantho' | 'Tp.Hcm' -> 'tphcm' | missing -> None"""
    if pd.isna(text):
        return None
    t = str(text).lower().replace('đ', 'd')
    t = unicodedata.normalize('NFD', t)
    t = ''.join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]', '', t)

def squash(series):
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

#2) CLEAN TEXT ============
all_df['Customer Name'] = squash(all_df['Customer Name']).str.title()
all_df['Company Name']  = squash(all_df['Company Name'])
all_df['Email']         = all_df['Email'].str.replace(r'\s+', '', regex=True).str.lower()

all_df['City'] = squash(all_df['City']).str.title()
keys = all_df['City'].map(city_key)
auto_name = all_df.groupby(keys)['City'].agg(lambda s: s.mode().iat[0])
all_df['City'] = keys.map(CITY_ALIASES).fillna(keys.map(auto_name))      

all_df['SKU_Clean'] = sku_clean(all_df['SKU'])

#3) CLEAN VALUES  ============
all_df['ID_Clean'] = all_df['Order ID'].str.replace(
    r'(?i)^\s*ORD\D*(\d{6})\D*(\d{4})\s*$', r'ORD-\1-\2', regex=True)

qty_text = all_df['Quantity'].str.lower().str.strip()
qty_num  = pd.to_numeric(qty_text.str.extract(r'(-?\d+(?:\.\d+)?)')[0], errors='coerce')
still_empty = qty_num.isna() & qty_text.notna()
qty_word = qty_text[still_empty].map(words_to_number)
all_df['Qty_Clean'] = qty_num.fillna(qty_word)

all_df['Price_Clean'] = pd.to_numeric(
    all_df['Unit Price (USD)'].str.replace(r'[^\d.\-]', '', regex=True), errors='coerce')

all_df['Date_Clean'] = pd.to_datetime(
    all_df['Order Date'], errors='coerce', format='mixed', dayfirst=True)

#4) BUILD THE FLAGS ============
EMAIL = r'^[\w.+-]+@[\w-]+\.[\w.-]+$'

id_month   = all_df['ID_Clean'].str[4:10]                  
date_month = all_df['Date_Clean'].dt.strftime('%Y%m')

flags = pd.DataFrame({
    'Bad_ID':        ~all_df['ID_Clean'].str.match(r'^ORD-\d{6}-\d{4}$', na=False),
    'Bad_SKU':       ~all_df['SKU_Clean'].str.match(r'^SKU-\d+$', na=False),
    'Missing_Name':  all_df['Customer Name'].isna(),
    'Missing_Email': all_df['Email'].isna(),
    'Invalid_Email': all_df['Email'].notna() & ~all_df['Email'].str.match(EMAIL, na=False),
    'Bad_Qty':       all_df['Qty_Clean'].isna() | (all_df['Qty_Clean'] <= 0)
                     | (all_df['Qty_Clean'] % 1 != 0),
    'Bad_Price':     all_df['Price_Clean'].isna() | (all_df['Price_Clean'] <= 0),
    'Bad_Date':      all_df['Date_Clean'].isna(),
    'Date_Mismatch': id_month.notna() & date_month.notna() & (id_month != date_month),
    'Duplicate_ID':  all_df.duplicated(subset=['ID_Clean'], keep=False),   
})

all_df['Issues']    = flags.apply(lambda r: ', '.join(r.index[r]), axis=1)
all_df['Has_Issue'] = all_df['Issues'] != ''

all_df['Is_Extra_Copy'] = all_df.duplicated(subset=['ID_Clean'], keep='first')

#5) REPORT ============
print('\n--- Rows per flag ---')
print(flags.sum().sort_values(ascending=False))

print('\n--- How many flags per row ---')
print(flags.sum(axis=1).value_counts().sort_index())

print(f'\nRows with at least one issue: {all_df["Has_Issue"].sum()} of {len(all_df)}')
print(f'Extra copies (duplicates to remove): {all_df["Is_Extra_Copy"].sum()}')   
print(f'Distinct cities: {all_df["City"].nunique()} | Distinct SKUs: {all_df["SKU_Clean"].nunique()}')

print('\n--- City list in this checkpoint ---')
print(all_df['City'].value_counts(dropna=False))

#6) EXAMPLES PER FLAG ============
show_cols = ['Order ID', 'Customer Name', 'Email', 'SKU', 'Quantity',
             'Unit Price (USD)', 'Order Date', 'Source']
for name in flags.columns:
    if flags[name].any():
        print(f'\n--- {name} (first 3 rows) ---')
        print(all_df.loc[flags[name], show_cols].head(3))

#7) SELF-CHECK ============
print('\n--- Self-check ---')
print('Has_Issue matches flags.any:', (all_df['Has_Issue'] == flags.any(axis=1)).all())  
print('Rows in report == rows read: ', len(all_df) == 912)                                

#8) SAVE A CHECKPOINT ============
Path('output').mkdir(exist_ok=True)
all_df.to_csv('output/05_flagged.csv', index=False, encoding='utf-8-sig')
print('\nSaved: output/05_flagged.csv')