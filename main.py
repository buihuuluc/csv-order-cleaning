import re
import unicodedata
import pandas as pd
from pathlib import Path
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from lookups import CITY_ALIASES              # aliases live in lookups.py ONLY

pd.set_option('display.max_columns', None)   # show all columns
pd.set_option('display.width', 200)          # wider terminal output

# ============ SETTINGS ============
DATA_DIR = Path('data')
OUTPUT_DIR = Path('output')
CATALOG_FILE = DATA_DIR / 'Catalog.csv'
CATALOG_KEY = 'SKU'                  # CHANGE if Catalog.csv names its key column differently
XLSX_PATH = OUTPUT_DIR / 'Cleaned.xlsx'
CSV_PATH = OUTPUT_DIR / 'Cleaned.csv'

# Numbers checked on the practice dataset. Set to None for a new dataset.
EXPECTED_ROWS = 912
EXPECTED_EXTRA = 26
EXPECTED_UNIQUE = 886

EMAIL_PATTERN = r'^[\w.+-]+@[\w-]+\.[\w.-]+$'

UNITS = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
         'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12,
         'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
         'seventeen': 17, 'eighteen': 18, 'nineteen': 19}
TENS = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
        'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90}
SCALES = {'thousand': 1_000, 'million': 1_000_000}


# ============ HELPERS ============
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
    t = ''.join(ch for ch in t if not unicodedata.combining(ch))   # drop accents
    return re.sub(r'[^a-z0-9]', '', t)


def squash(series):
    """Collapse any run of whitespace into one space, then trim."""
    return series.str.replace(r'\s+', ' ', regex=True).str.strip()


def sku_clean(series):
    """'sku1001', 'SKU 1001', 'SKU-1001' -> 'SKU-1001'"""
    return (series.str.strip().str.upper()
                  .str.replace(r'^SKU\D*(\d+)$', r'SKU-\1', regex=True))


def check(label, ok):
    print(f'[{"PASS" if ok else "FAIL"}] {label}')
    return ok


# ============ STEP 1: LOAD ============
def load_folder(folder):
    """Read every T*-2026.csv, tag each row with its file, merge into one table."""
    files = sorted(Path(folder).glob('T*-2026.csv'))
    if not files:
        raise SystemExit(f'No T*-2026.csv files found in {folder}')
    frames = []
    for f in files:
        d = pd.read_csv(f, dtype=str, encoding='utf-8-sig')
        d.columns = d.columns.str.strip()                   # trim column names
        frames.append(d.assign(Source=f.stem))
    df = pd.concat(frames, ignore_index=True)
    return df.replace(r'^\s*$', pd.NA, regex=True)          # blank / space-only -> missing


# ============ STEP 2: FIRST LOOK ============
def inspect_raw(df):
    print(f'Files: {df["Source"].nunique()} | Rows: {len(df)} | Columns: {df.shape[1]}')
    print('Columns:', df.columns.tolist())
    print('\n--- Missing per column ---')
    print(df.isna().sum())
    cols = [c for c in df.columns if c != 'Source']
    print('\nExact duplicate rows (all columns except Source):', df.duplicated(subset=cols).sum())


# ============ STEPS 3 + 4: CLEAN ============
def clean(df):
    df = df.copy()

    # text
    df['Customer Name'] = squash(df['Customer Name']).str.title()
    df['Company Name'] = squash(df['Company Name'])                       # no title(): keeps 'IBM'
    df['Email'] = df['Email'].str.replace(r'\s+', '', regex=True).str.lower()

    # city: same key = same city; aliases from lookups.py win
    df['City'] = squash(df['City']).str.title()
    keys = df['City'].map(city_key)
    auto_name = df.groupby(keys)['City'].agg(lambda s: s.mode().iat[0])   # most common spelling
    df['City'] = keys.map(CITY_ALIASES).fillna(keys.map(auto_name))

    # sku
    df['SKU_Clean'] = sku_clean(df['SKU'])

    # order id: rebuild as ORD-YYYYMM-NNNN
    df['ID_Clean'] = df['Order ID'].str.replace(
        r'(?i)^\s*ORD\D*(\d{6})\D*(\d{4})\s*$', r'ORD-\1-\2', regex=True)

    # quantity: digits first ('6 pcs' -> 6), then English number words ('two' -> 2)
    qty_text = df['Quantity'].str.lower().str.strip()
    qty_num = pd.to_numeric(qty_text.str.extract(r'(-?\d+(?:\.\d+)?)')[0], errors='coerce')
    still_empty = qty_num.isna() & qty_text.notna()
    qty_word = qty_text[still_empty].map(words_to_number)
    df['Qty_Clean'] = qty_num.fillna(qty_word)

    # price and date
    df['Price_Clean'] = pd.to_numeric(
        df['Unit Price (USD)'].str.replace(r'[^\d.\-]', '', regex=True), errors='coerce')
    df['Date_Clean'] = pd.to_datetime(
        df['Order Date'], errors='coerce', format='mixed', dayfirst=True)
    return df


# ============ STEP 5: FLAGS ============
def add_flags(df):
    """Return the table with Issues / Has_Issue / Is_Extra_Copy, and the flag table itself."""
    df = df.copy()
    id_month = df['ID_Clean'].str[4:10]                      # 'ORD-202601-0034' -> '202601'
    date_month = df['Date_Clean'].dt.strftime('%Y%m')

    flags = pd.DataFrame({
        'Bad_ID':        ~df['ID_Clean'].str.match(r'^ORD-\d{6}-\d{4}$', na=False),
        'Bad_SKU':       ~df['SKU_Clean'].str.match(r'^SKU-\d+$', na=False),
        'Missing_Name':  df['Customer Name'].isna(),
        'Missing_Email': df['Email'].isna(),
        'Invalid_Email': df['Email'].notna() & ~df['Email'].str.match(EMAIL_PATTERN, na=False),
        'Bad_Qty':       df['Qty_Clean'].isna() | (df['Qty_Clean'] <= 0)
                         | (df['Qty_Clean'] % 1 != 0),
        'Bad_Price':     df['Price_Clean'].isna() | (df['Price_Clean'] <= 0),
        'Bad_Date':      df['Date_Clean'].isna(),
        'Date_Mismatch': id_month.notna() & date_month.notna() & (id_month != date_month),
        'Duplicate_ID':  df.duplicated(subset=['ID_Clean'], keep=False),   # whole groups
    })

    df['Issues'] = flags.apply(lambda r: ', '.join(r.index[r]), axis=1)    # names of True flags
    df['Has_Issue'] = df['Issues'] != ''
    df['Is_Extra_Copy'] = df.duplicated(subset=['ID_Clean'], keep='first') # rows step 6 drops
    return df, flags


# ============ STEP 6: ORDERS + CATALOG + REVENUE ============
def load_catalog(path, key):
    cat = pd.read_csv(path, dtype=str, encoding='utf-8-sig')
    cat.columns = cat.columns.str.strip()
    if key not in cat.columns:
        raise SystemExit(f'Column {key!r} not found in Catalog. Columns: {cat.columns.tolist()}')
    cat[key] = sku_clean(cat[key])                           # same rule as the orders
    cat = cat.rename(columns={key: 'SKU_Clean'})
    dups = cat['SKU_Clean'].duplicated().sum()
    if dups > 0:
        print(cat[cat['SKU_Clean'].duplicated(keep=False)])
        raise SystemExit(f'Catalog has {dups} duplicate SKU keys: merge would duplicate orders')
    return cat


def drop_dup_flag(text):
    """Duplicate_ID is resolved by dedup, so it is not an open issue any more."""
    return ', '.join(p for p in text.split(', ') if p and p != 'Duplicate_ID')


def build_orders(df):
    """Drop extra copies, attach catalog columns, compute revenue, finish the Issues column."""
    removed = df[df['Is_Extra_Copy']].copy()
    orders = df[~df['Is_Extra_Copy']].copy()

    catalog = load_catalog(CATALOG_FILE, CATALOG_KEY)
    rows_before = len(orders)
    orders = orders.merge(catalog, on='SKU_Clean', how='left',
                          validate='m:1', suffixes=('', '_Catalog'), indicator=True)
    if len(orders) != rows_before:
        raise SystemExit(f'Merge changed the row count: {rows_before} -> {len(orders)}')

    valid = orders['Qty_Clean'].gt(0) & orders['Price_Clean'].gt(0)       # NaN counts as False
    orders['Revenue'] = (orders['Qty_Clean'] * orders['Price_Clean']).where(valid)

    orders['Issues'] = orders['Issues'].fillna('').map(drop_dup_flag)
    not_in_catalog = orders['_merge'].eq('left_only')
    orders.loc[not_in_catalog, 'Issues'] = orders.loc[not_in_catalog, 'Issues'].map(
        lambda t: (t + ', ' if t else '') + 'SKU_Not_In_Catalog')
    orders['Has_Issue'] = orders['Issues'] != ''
    return orders, removed


# ============ STEP 7: SHEETS ============
def summarize_by(frame, key):
    return (frame.groupby(key, dropna=False)
                 .agg(Orders=('ID_Clean', 'count'),
                      Quantity=('Qty_Clean', 'sum'),
                      Revenue=('Revenue', 'sum'))
                 .reset_index()
                 .sort_values('Revenue', ascending=False))


def build_sheets(df, orders, removed):
    """Return ({sheet name: (table, money columns)}, total revenue)."""
    # Cleaned: one row per order; catalog columns are the ones df did not have
    base = ['ID_Clean', 'Date_Clean', 'Customer Name', 'Email', 'Company Name', 'City',
            'SKU_Clean', 'Qty_Clean', 'Price_Clean', 'Revenue']
    extras = [c for c in orders.columns
              if c not in df.columns and c not in ('_merge', 'Revenue')]
    cleaned = (orders.sort_values('ID_Clean')[base + extras + ['Issues']]
                     .rename(columns={'ID_Clean': 'Order ID', 'Date_Clean': 'Order Date',
                                      'SKU_Clean': 'SKU', 'Qty_Clean': 'Quantity',
                                      'Price_Clean': 'Unit Price (USD)',
                                      'Revenue': 'Revenue (USD)'}))

    # Issues: rows to review, with the ORIGINAL raw values next to the cleaned ID
    issues = (orders[orders['Has_Issue']].sort_values('ID_Clean')
              [['Order ID', 'ID_Clean', 'Customer Name', 'Email', 'Quantity',
                'Unit Price (USD)', 'Order Date', 'Issues', 'Source']]
              .rename(columns={'Order ID': 'Original Order ID', 'ID_Clean': 'Order ID',
                               'Quantity': 'Original Quantity',
                               'Unit Price (USD)': 'Original Price',
                               'Order Date': 'Original Date'}))
    issue_counts = (orders.loc[orders['Has_Issue'], 'Issues'].str.split(', ').explode()
                          .value_counts().rename_axis('Issue').reset_index(name='Rows'))

    # Removed_Duplicates: the extra copies taken out
    removed_sheet = (removed.sort_values('ID_Clean')
                     [['Order ID', 'ID_Clean', 'Customer Name', 'Email', 'Quantity',
                       'Unit Price (USD)', 'Order Date', 'Source']])

    # Summaries: only orders with usable revenue
    usable = orders[orders['Revenue'].notna()].copy()
    usable['Month'] = usable['Date_Clean'].dt.to_period('M').astype(str).replace('NaT', 'Unknown')
    by_month = summarize_by(usable, 'Month').sort_values('Month')
    by_city = summarize_by(usable, 'City')
    by_sku = summarize_by(usable, 'SKU_Clean').rename(columns={'SKU_Clean': 'SKU'})

    total = round(usable['Revenue'].sum(), 2)
    not_in_catalog = int(orders['_merge'].eq('left_only').sum())
    report = pd.DataFrame({
        'Metric': ['Source files read', 'Rows read', 'Extra copies removed', 'Unique orders',
                   'Orders with issues (flagged, not deleted)', 'Orders excluded from revenue',
                   'Orders with usable revenue', 'SKUs not found in Catalog (orders)',
                   'Total revenue (USD)'],
        'Value': [df['Source'].nunique(), len(df), len(removed), len(orders),
                  int(orders['Has_Issue'].sum()), len(orders) - len(usable),
                  len(usable), not_in_catalog, total],
    })

    rules = pd.DataFrame([
        ('Original data', 'Source files are never modified. All work is done on copies.'),
        ('Order ID', 'Rebuilt as ORD-YYYYMM-NNNN from the digits in the raw ID (fixes spaces, lowercase, missing dashes).'),
        ('Duplicates', 'Rows with the same cleaned Order ID: first row kept, extra copies listed in Removed_Duplicates.'),
        ('Text', 'Extra spaces trimmed; names in Proper Case; emails lowercase without spaces.'),
        ('City', 'Spelling variants merged (case, spacing, accents, punctuation). Aliases such as Saigon / Tp.Hcm / Hcm merged into Ho Chi Minh City, Hn into Hanoi.'),
        ('SKU', 'Standardized to SKU-NNNN (fixes SKU1001 vs SKU-1001, spaces, lowercase). Same rule applied to Catalog.csv before matching.'),
        ('Quantity', 'Digits extracted from text such as "6 pcs"; English number words such as "two" converted; unreadable values flagged.'),
        ('Unit Price', 'Currency symbols and text removed; unreadable values flagged.'),
        ('Order Date', 'Parsed day-first; mixed formats accepted; unreadable dates flagged.'),
        ('Revenue', 'Quantity x Unit Price, only when both are greater than 0.'),
        ('Flags', 'Rows are never deleted for bad values. They are flagged in the Issues column for review.'),
    ], columns=['Topic', 'Rule'])

    sheets = {
        'Report': (report, ()),
        'Cleaned': (cleaned, ('Unit Price (USD)', 'Revenue (USD)')),
        'Issues': (issues, ()),
        'Issue_Counts': (issue_counts, ()),
        'Removed_Duplicates': (removed_sheet, ()),
        'By_Month': (by_month, ('Revenue',)),
        'By_City': (by_city, ('Revenue',)),
        'By_SKU': (by_sku, ('Revenue',)),
        'Rules': (rules, ()),
    }
    return sheets, total


def style_sheet(ws, money_cols=()):
    fill = PatternFill('solid', fgColor='DDF4F0')
    for cell in ws[1]:                                       # header row
        cell.font = Font(bold=True)
        cell.fill = fill
    ws.freeze_panes = 'A2'                                   # keep header visible
    ws.auto_filter.ref = ws.dimensions                       # filter buttons
    for i, col in enumerate(ws.columns, start=1):            # widths from the longest cell
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 2, 10), 45)
    for cell in ws[1]:                                       # money format
        if cell.value in money_cols:
            for c in ws[get_column_letter(cell.column)][1:]:
                c.number_format = '#,##0.00'


def export(sheets):
    OUTPUT_DIR.mkdir(exist_ok=True)
    sheets['Cleaned'][0].to_csv(CSV_PATH, index=False, encoding='utf-8-sig')   # keeps Vietnamese
    with pd.ExcelWriter(XLSX_PATH, engine='openpyxl', datetime_format='yyyy-mm-dd') as xw:
        for name, (frame, money) in sheets.items():
            frame.to_excel(xw, sheet_name=name, index=False)
            style_sheet(xw.sheets[name], money)
    print(f'Saved: {XLSX_PATH} and {CSV_PATH}')


# ============ VERIFY ============
def verify(df, flags, orders, removed, total):
    print('\n=== CHECKS ===')
    results = []
    if EXPECTED_ROWS is not None:
        results.append(check(f'Rows read == {EXPECTED_ROWS}', len(df) == EXPECTED_ROWS))
    if EXPECTED_EXTRA is not None:
        results.append(check(f'Extra copies == {EXPECTED_EXTRA}', len(removed) == EXPECTED_EXTRA))
    if EXPECTED_UNIQUE is not None:
        results.append(check(f'Unique orders == {EXPECTED_UNIQUE}', len(orders) == EXPECTED_UNIQUE))
    results.append(check('Rows = unique orders + extra copies', len(df) == len(orders) + len(removed)))
    results.append(check('Bad_ID flag count == 0', flags['Bad_ID'].sum() == 0))
    results.append(check('Has_Issue matches flags (before dedup)',
                         (df['Has_Issue'] == flags.any(axis=1)).all()))

    sheets_back = pd.read_excel(XLSX_PATH, sheet_name=None)          # reopen the saved file
    results.append(check('Cleaned sheet rows == unique orders',
                         len(sheets_back['Cleaned']) == len(orders)))
    results.append(check('Removed_Duplicates rows == extra copies',
                         len(sheets_back['Removed_Duplicates']) == len(removed)))
    for name in ['Cleaned', 'By_Month', 'By_City', 'By_SKU']:
        col = 'Revenue (USD)' if name == 'Cleaned' else 'Revenue'
        ok = abs(sheets_back[name][col].sum() - total) < 0.01
        results.append(check(f'{name} revenue adds up to {total:,.2f}', ok))

    print(f'\n{sum(results)} of {len(results)} checks passed')
    print('\n--- Sheets in the file ---')
    for name, d in sheets_back.items():
        print(f'{name:<20} {d.shape}')
    print('\n--- Report ---')
    print(sheets_back['Report'].to_string(index=False))


# ============ MAIN ============
def main():
    print('=== 1) LOAD ===')
    raw = load_folder(DATA_DIR)

    print('\n=== 2) FIRST LOOK ===')
    inspect_raw(raw)

    print('\n=== 3) CLEAN ===')
    cleaned = clean(raw)
    print(f'Distinct cities: {raw["City"].nunique()} => {cleaned["City"].nunique()}')
    print(f'Distinct SKUs:   {raw["SKU"].nunique()} => {cleaned["SKU_Clean"].nunique()}')
    print('\nCities after cleaning:')
    print(cleaned['City'].value_counts(dropna=False))

    print('\n=== 4) FLAGS ===')
    flagged, flags = add_flags(cleaned)
    print(flags.sum().sort_values(ascending=False))
    print(f'Extra copies: {flagged["Is_Extra_Copy"].sum()}')

    print('\n=== 5) ORDERS + CATALOG + REVENUE ===')
    orders, removed = build_orders(flagged)
    print(f'Unique orders: {len(orders)}')
    print(orders['_merge'].value_counts())

    print('\n=== 6) EXPORT ===')
    sheets, total = build_sheets(flagged, orders, removed)
    export(sheets)

    verify(flagged, flags, orders, removed, total)


if __name__ == '__main__':
    main()