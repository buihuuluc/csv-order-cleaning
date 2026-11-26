import pandas as pd
from pathlib import Path

pd.set_option('display.max_columns', None)   
pd.set_option('display.width', 200)         
pd.options.display.float_format = '{:,.2f}'.format

CATALOG_KEY = 'SKU'     

def sku_clean(series):
    """'sku1001', 'SKU 1001', 'SKU-1001' -> 'SKU-1001'"""
    return (series.str.strip().str.upper()
                  .str.replace(r'^SKU\D*(\d+)$', r'SKU-\1', regex=True))

#1) LOAD THE STEP 5 CHECKPOINT ============
df = pd.read_csv('output/05_flagged.csv', encoding='utf-8-sig',
                 dtype={'Order ID': str, 'ID_Clean': str}, parse_dates=['Date_Clean'])
print(f'Rows in checkpoint: {len(df)}')              

#2) KEEP ONE ROW / ORDER ============
orders = df[~df['Is_Extra_Copy']].copy()              
print(f'Unique orders: {len(orders)}')                

#3) CATALOG ============
catalog = pd.read_csv('data/Catalog.csv', dtype=str, encoding='utf-8-sig')
catalog.columns = catalog.columns.str.strip()
print('\nCatalog columns:', catalog.columns.tolist())
print(catalog.head())

if CATALOG_KEY not in catalog.columns:
    raise SystemExit(f'Column {CATALOG_KEY!r} not found in Catalog.csv, fix CATALOG_KEY above')

catalog[CATALOG_KEY] = sku_clean(catalog[CATALOG_KEY])         
catalog = catalog.rename(columns={CATALOG_KEY: 'SKU_Clean'})

dup_keys = catalog['SKU_Clean'].duplicated().sum()
print(f'\nDuplicate SKUs inside Catalog (after cleaning): {dup_keys}')   
if dup_keys > 0:
    print(catalog[catalog['SKU_Clean'].duplicated(keep=False)])
    raise SystemExit('Catalog has duplicate keys: merge would duplicate order rows')

#4) MERGE ORDERS WITH CATALOG ============
orders['SKU_Clean'] = sku_clean(orders['SKU'])                 

rows_before_merge = len(orders)
orders = orders.merge(catalog, on='SKU_Clean', how='left',
                      validate='m:1',                          
                      suffixes=('', '_Catalog'),
                      indicator=True)                          
print(f'\nRows before merge: {rows_before_merge} | after: {len(orders)}')   

print('\n--- SKU match result ---')
print(orders['_merge'].value_counts())
unmatched = orders[orders['_merge'] == 'left_only']
print('\nSKUs not found in Catalog (top 10):')
print(unmatched.groupby(['SKU', 'SKU_Clean'], dropna=False).size().sort_values(ascending=False).head(10))

#5) REVENUE ============
valid = orders['Qty_Clean'].gt(0) & orders['Price_Clean'].gt(0)    
orders['Revenue'] = (orders['Qty_Clean'] * orders['Price_Clean']).where(valid)

usable = orders[orders['Revenue'].notna()].copy()
print(f'\nOrders with usable revenue: {len(usable)} | excluded: {len(orders) - len(usable)}')
print(f'Total revenue: {usable["Revenue"].sum():,.2f}')

print('\n--- Top 10 orders by revenue (check for typos like extra zeros) ---')
print(usable.nlargest(10, 'Revenue')[['ID_Clean', 'City', 'Qty_Clean',
                                      'Price_Clean', 'Revenue', 'Source']])

print('\n--- Status Check values (decide with the client if some should be excluded) ---')
print(orders['Status Check'].value_counts(dropna=False))

#6) SAVE A CHECKPOINT ============
Path('output').mkdir(exist_ok=True)
orders.to_csv('output/06_orders.csv', index=False, encoding='utf-8-sig')
print('\nSaved: output/06_orders.csv')

#7) SUMMARIES ============
usable['Month'] = usable['Date_Clean'].dt.to_period('M').astype(str)    

def summarize_by(frame, key):
    return (frame.groupby(key, dropna=False)
                 .agg(Orders=('ID_Clean', 'count'),
                      Qty=('Qty_Clean', 'sum'),
                      Revenue=('Revenue', 'sum'))
                 .reset_index()
                 .sort_values('Revenue', ascending=False))

by_month = summarize_by(usable, 'Month').sort_values('Month')
by_city  = summarize_by(usable, 'City')
by_sku   = summarize_by(usable, 'SKU_Clean')

print('\n--- Revenue by month ---')
print(by_month)
print('\n--- Revenue by city ---')
print(by_city)
print('\n--- Revenue by SKU (top 5) ---')
print(by_sku.head(5))

print('\n--- Top 10 customers by revenue ---')
print(usable.groupby('Customer Name')['Revenue'].sum().nlargest(10))

pivot = usable.pivot_table(index='City', columns='Month', values='Revenue',
                           aggfunc='sum', fill_value=0)

#8) SELF-CHECK ============
total = usable['Revenue'].sum()
print('\n--- Self-check ---')
print('Merge did not change row count:', len(orders) == rows_before_merge)               
print('by_month adds up to total:     ', abs(by_month['Revenue'].sum() - total) < 0.01)  
print('by_city adds up to total:      ', abs(by_city['Revenue'].sum() - total) < 0.01)   
print('pivot adds up to total:        ', abs(pivot.to_numpy().sum() - total) < 0.01)     