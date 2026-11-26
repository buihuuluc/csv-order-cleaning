import pandas as pd
from pathlib import Path

pd.set_option('display.max_columns', None)   # show all columns
pd.set_option('display.width', 200)          # wider terminal output
pd.set_option('display.max_rows', 200)       # show up to 200 rows

# ============ FUNCTION TYPES USED IN THIS FILE ============
# READ   : bring files into pandas       (Path.iterdir, read_csv, read_excel)
# CHECK  : compare / count, change nothing (list compare, isna, nunique, notna)
# MERGE  : stack tables into one         (assign, pd.concat)
# EXPORT : write a file to disk          (to_csv)
# REPORT : print results to the terminal (print)

# ============ SETTINGS (the only part you edit for a new folder) ============
FOLDER = 'data'                          # folder that holds the raw files
CATALOG_WORD = 'catalog'                 # file name containing this word = lookup file (not raw)
OUTPUT = 'output/Raw_Grouped.csv'        # merged raw file (saved OUTSIDE the data folder)
LIMIT = 30                               # list every value of columns with <= this many unique values


# ============ 1) RECEIVE THE FILES ============
def read_one(path):
    """READ: one file -> {table name: DataFrame}. A CSV is one table; an Excel file gives one table per sheet."""
    if path.suffix.lower() == '.csv':
        # dtype=str: read everything as text (keeps leading zeros, no surprise number conversion)
        # encoding='utf-8-sig': removes the hidden BOM character and keeps Vietnamese text correct
        return {path.stem: pd.read_csv(path, dtype=str, encoding='utf-8-sig')}
    sheets = pd.read_excel(path, sheet_name=None, dtype=str)    # sheet_name=None: read ALL sheets
    return {f'{path.stem}::{name}': d for name, d in sheets.items()}


def load_folder(folder):
    """READ: scan a folder -> (raw tables, lookup tables). Raw and lookup are separated by the file name."""
    paths = sorted(p for p in Path(folder).iterdir()                     # iterdir: list everything in the folder
                   if p.suffix.lower() in ('.csv', '.xlsx')              # suffix: file extension
                   and not p.name.startswith('~$'))                      # skip Excel temp files
    raw, lookup = {}, {}
    for p in paths:
        target = lookup if CATALOG_WORD in p.stem.lower() else raw       # stem: file name without extension
        for name, d in read_one(p).items():
            d.columns = d.columns.str.strip()                            # trim spaces around column names
            target[name] = d
    return raw, lookup


def show_received(raw, lookup):
    """REPORT: list every table that was read, with (rows, columns)."""
    print(f'Raw tables: {len(raw)} | total rows: {sum(len(d) for d in raw.values())}')
    for name, d in raw.items():
        print(f'  {name:<28} {d.shape}')                                 # .shape = (rows, columns)
    print(f'\nLookup tables (not merged): {len(lookup)}')
    for name, d in lookup.items():
        print(f'  {name:<28} {d.shape} | columns: {d.columns.tolist()}')


# ============ 2) CHECK COLUMN NAMES ============
def check_columns(tables):
    """CHECK: compare the column names of every raw table with the first one. Returns True if all match."""
    names = list(tables)
    base = list(tables[names[0]].columns)
    print(f'Reference ({names[0]}): {base}\n')
    all_ok = True
    for name in names:
        cols = list(tables[name].columns)
        missing = [c for c in base if c not in cols]                     # in the reference but not here
        extra = [c for c in cols if c not in base]                       # here but not in the reference
        if cols == base:
            print(f'[OK]        {name}')
        elif not missing and not extra:
            all_ok = False
            print(f'[ORDER]     {name}: same columns, different order (merge still works, matches by name)')
        else:
            all_ok = False
            print(f'[DIFFERENT] {name}: missing {missing} | extra {extra}')
    print('\nAll raw tables have the same columns:', all_ok)
    return all_ok


# ============ 3) MERGE INTO ONE FILE ============
def merge_raw(raw):
    """MERGE: stack all raw tables into one and tag each row with the table it came from."""
    frames = [d.assign(Source=name) for name, d in raw.items()]          # assign: add the Source column
    return pd.concat(frames, ignore_index=True)                          # concat: stack rows; ignore_index: renumber 0..n


def export_csv(df, path):
    """EXPORT: save a table to CSV (creates the folder if needed)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)                 # mkdir: create the output folder
    df.to_csv(path, index=False, encoding='utf-8-sig')                   # index=False: no extra number column; utf-8-sig: Excel reads Vietnamese


def check_merge(raw, merged):
    """CHECK: rows in = rows out, and no new columns were created by mismatched names."""
    rows_in = sum(len(d) for d in raw.values())
    first_cols = len(next(iter(raw.values())).columns)
    print(f'Rows in all raw tables: {rows_in} | rows in merged file: {len(merged)} | match: {rows_in == len(merged)}')
    print(f'Columns: {merged.shape[1]} (first table has {first_cols} + Source) | match: {merged.shape[1] == first_cols + 1}')


# ============ 4) CHECK UNIQUE OF EVERY COLUMN ============
def blank_to_na(df):
    """CHECK helper: turn cells with only spaces into real missing values, so they count as empty."""
    return df.replace(r'^\s*$', pd.NA, regex=True)


def unique_summary(df):
    """CHECK: one row per column: how many filled, empty, unique; and whether every filled value is unique."""
    data = blank_to_na(df).drop(columns=['Source'], errors='ignore')
    summary = pd.DataFrame({
        'Non_Empty': data.notna().sum(),                                 # cells that have data
        'Empty': data.isna().sum(),                                      # empty cells
        'Unique': data.nunique(),                                        # distinct values (empty not counted)
    })
    summary['Unique_%'] = (summary['Unique'] / summary['Non_Empty'] * 100).round(1)
    summary['All_Unique'] = summary['Unique'] == summary['Non_Empty']    # True = no value repeats (key candidate)
    return summary


def show_values(df, limit):
    """REPORT: print the distinct values of each column on one line (first 10 if the column has too many)."""
    data = blank_to_na(df).drop(columns=['Source'], errors='ignore')
    for col in data.columns:
        values = sorted(data[col].dropna().unique())                     # unique: distinct values; sorted: A-Z
        shown = [f"'{v}'" for v in values]                               # quotes make hidden spaces visible: 'Hanoi ' vs 'Hanoi'
        if len(values) <= limit:
            print(f'\n{col} ({len(values)}): ' + ', '.join(shown))
        else:
            print(f'\n{col}: {len(values)} unique (more than {limit}), first 10: ' + ', '.join(shown[:10]))


# ============ RUN ============
def main():
    raw, lookup = load_folder(FOLDER)
    if not raw:
        raise SystemExit(f'No .csv or .xlsx raw files found in {FOLDER!r}')

    print('=== 1) FILES RECEIVED ===')
    show_received(raw, lookup)

    print('\n=== 2) COLUMN NAMES ===')
    columns_ok = check_columns(raw)
    if not columns_ok:
        print('WARNING: fix the differences above before trusting the merge.')

    print('\n=== 3) MERGE ===')
    merged = merge_raw(raw)
    export_csv(merged, OUTPUT)
    print(f'Saved: {OUTPUT}')
    check_merge(raw, merged)

    print('\n=== 4) UNIQUE PER COLUMN (Raw_Grouped) ===')
    print(unique_summary(merged))
    show_values(merged, LIMIT)

    for name, d in lookup.items():
        print(f'\n=== 4) UNIQUE PER COLUMN ({name}) ===')
        print(unique_summary(d))
        show_values(d, LIMIT)


if __name__ == '__main__':
    main()