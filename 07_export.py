import pandas as pd
from pathlib import Path
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 200)

XLSX = 'output/Cleaned.xlsx'
CSV = 'output/Cleaned.csv'

#1) LOAD THE CHECKPOINTS ============
def load(path):
    d = pd.read_csv(path, dtype=str, encoding='utf-8-sig')        
    for c in ['Qty_Clean', 'Price_Clean', 'Revenue']:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors='coerce')
    for c in ['Has_Issue', 'Is_Extra_Copy']:
        if c in d.columns:
            d[c] = d[c].eq('True')
    d['Date_Clean'] = pd.to_datetime(d['Date_Clean'], errors='coerce')
    return d

flagged = load('output/05_flagged.csv')      
orders = load('output/06_orders.csv')        
print(f'Flagged rows: {len(flagged)} | Unique orders: {len(orders)}')     

#2) FINAL ISSUES COLUMN ============
orders['Issues'] = orders['Issues'].fillna('')         

def drop_dup_flag(text):
    parts = [p for p in text.split(', ') if p and p != 'Duplicate_ID']   
    return ', '.join(parts)

orders['Issues'] = orders['Issues'].map(drop_dup_flag)

not_in_catalog = orders['_merge'].eq('left_only')        
orders.loc[not_in_catalog, 'Issues'] = orders.loc[not_in_catalog, 'Issues'].map(
    lambda t: (t + ', ' if t else '') + 'SKU_Not_In_Catalog')
orders['Has_Issue'] = orders['Issues'] != ''

#3) BUILD EACH SHEET ============
base = ['ID_Clean', 'Date_Clean', 'Customer Name', 'Email', 'Company Name', 'City',
        'SKU_Clean', 'Qty_Clean', 'Price_Clean', 'Revenue']
extras = [c for c in orders.columns
          if c not in flagged.columns and c not in ('SKU_Clean', '_merge', 'Revenue')]   
cleaned = (orders.sort_values('ID_Clean')[base + extras + ['Issues']]
                 .rename(columns={'ID_Clean': 'Order ID', 'Date_Clean': 'Order Date',
                                  'SKU_Clean': 'SKU', 'Qty_Clean': 'Quantity',
                                  'Price_Clean': 'Unit Price (USD)', 'Revenue': 'Revenue (USD)'}))

issues = (orders[orders['Has_Issue']]
          .sort_values('ID_Clean')
          [['Order ID', 'ID_Clean', 'Customer Name', 'Email', 'Quantity',
            'Unit Price (USD)', 'Order Date', 'Issues', 'Source']]
          .rename(columns={'Order ID': 'Original Order ID', 'ID_Clean': 'Order ID',
                           'Quantity': 'Original Quantity', 'Unit Price (USD)': 'Original Price',
                           'Order Date': 'Original Date'}))

issue_counts = (orders.loc[orders['Has_Issue'], 'Issues'].str.split(', ').explode()
                      .value_counts().rename_axis('Issue').reset_index(name='Rows'))

# --- Removed_Duplicates: the extra copies that were taken out ---
removed = (flagged[flagged['Is_Extra_Copy']]
           .sort_values('ID_Clean')
           [['Order ID', 'ID_Clean', 'Customer Name', 'Email', 'Quantity',
             'Unit Price (USD)', 'Order Date', 'Source']])

# --- Summaries: only orders with usable revenue ---
usable = orders[orders['Revenue'].notna()].copy()
usable['Month'] = usable['Date_Clean'].dt.to_period('M').astype(str).replace('NaT', 'Unknown')

def summarize_by(frame, key):
    return (frame.groupby(key, dropna=False)
                 .agg(Orders=('ID_Clean', 'count'),
                      Quantity=('Qty_Clean', 'sum'),
                      Revenue=('Revenue', 'sum'))
                 .reset_index()
                 .sort_values('Revenue', ascending=False))

by_month = summarize_by(usable, 'Month').sort_values('Month')
by_city = summarize_by(usable, 'City')
by_sku = summarize_by(usable, 'SKU_Clean').rename(columns={'SKU_Clean': 'SKU'})

total_revenue = round(usable['Revenue'].sum(), 2)
report = pd.DataFrame({
    'Metric': ['Source files read', 'Rows read', 'Extra copies removed', 'Unique orders',
               'Orders with issues (flagged, not deleted)', 'Orders excluded from revenue',
               'Orders with usable revenue', 'SKUs not found in Catalog (orders)',
               'Total revenue (USD)'],
    'Value': [flagged['Source'].nunique(), len(flagged), len(removed), len(orders),
              int(orders['Has_Issue'].sum()), len(orders) - len(usable),
              len(usable), int(not_in_catalog.sum()), total_revenue],
})

rules = pd.DataFrame([
    ('Original data', 'Source files are never modified. All work is done on copies.'),
    ('Order ID', 'Rebuilt as ORD-YYYYMM-NNNN from the digits in the raw ID (fixes spaces, lowercase, missing dashes).'),
    ('Duplicates', 'Rows with the same cleaned Order ID: first row kept, extra copies listed in Removed_Duplicates.'),
    ('Text', 'Extra spaces trimmed; names and cities in Proper Case; emails lowercase without spaces.'),
        ('City', 'Spelling variants merged (case, spacing, accents, punctuation). Aliases such as Saigon / Tp.Hcm / Ho Chi Minh merged into Ho Chi Minh City.'),
    ('SKU', 'Standardized to SKU-NNNN (fixes SKU1001 vs SKU-1001, spaces, lowercase). Same rule applied to Catalog.csv before matching.'),
    ('Quantity', 'Digits extracted from text such as "6 pcs"; English number words such as "two" converted; unreadable values flagged.'),
    ('Unit Price', 'Currency symbols and text removed; unreadable values flagged.'),
    ('Order Date', 'Parsed day-first; mixed formats accepted; unreadable dates flagged.'),
    ('Revenue', 'Quantity x Unit Price, only when both are greater than 0.'),
    ('Flags', 'Rows are never deleted for bad values. They are flagged in the Issues column for review.'),
], columns=['Topic', 'Rule'])

#4) STYLE HELPER ============
def style_sheet(ws, money_cols=()):
    fill = PatternFill('solid', fgColor='DDF4F0')
    for cell in ws[1]:                                   
        cell.font = Font(bold=True)
        cell.fill = fill
    ws.freeze_panes = 'A2'                              
    ws.auto_filter.ref = ws.dimensions                  
    for i, col in enumerate(ws.columns, start=1):       
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 2, 10), 45)
    for cell in ws[1]:                                   
        if cell.value in money_cols:
            for c in ws[get_column_letter(cell.column)][1:]:
                c.number_format = '#,##0.00'

#5) WRITE THE FILES ============
Path('output').mkdir(exist_ok=True)
cleaned.to_csv(CSV, index=False, encoding='utf-8-sig')         

sheets = {
    'Report': (report, ()),
    'Cleaned': (cleaned, ('Unit Price (USD)', 'Revenue (USD)')),
    'Issues': (issues, ()),
    'Issue_Counts': (issue_counts, ()),
    'Removed_Duplicates': (removed, ()),
    'By_Month': (by_month, ('Revenue',)),
    'By_City': (by_city, ('Revenue',)),
    'By_SKU': (by_sku, ('Revenue',)),
    'Rules': (rules, ()),
}

with pd.ExcelWriter(XLSX, engine='openpyxl', datetime_format='yyyy-mm-dd') as xw:
    for name, (frame, money) in sheets.items():
        frame.to_excel(xw, sheet_name=name, index=False)
        style_sheet(xw.sheets[name], money)

print(f'\nSaved: {XLSX} and {CSV}')

#6) SELF-CHECK: reopen the file and compare ============
check = pd.read_excel(XLSX, sheet_name=None)
print('\n--- Sheets in the file ---')
for name, d in check.items():
    print(f'{name:<20} {d.shape}')

print('\n--- Self-check ---')
print('Cleaned rows == unique orders:       ', len(check['Cleaned']) == len(orders))             
print('Removed_Duplicates == extra copies:  ', len(check['Removed_Duplicates']) == len(removed)) 
print('Cleaned revenue == Report total:     ',
      abs(check['Cleaned']['Revenue (USD)'].sum() - total_revenue) < 0.01)                       
print('By_Month adds up to total:           ',
      abs(check['By_Month']['Revenue'].sum() - total_revenue) < 0.01)                            
print('By_City adds up to total:            ',
      abs(check['By_City']['Revenue'].sum() - total_revenue) < 0.01)                             

print('\n--- Report ---')
print(check['Report'].to_string(index=False))