# CSV Order Data Cleaning Pipeline

A Python pipeline that merges 11 monthly CSV order exports, validates their structure, cleans messy values, flags unresolved issues, and exports a client-ready Excel report with revenue summaries.

## The problem

Monthly order exports (`T01-2026.csv` through `T11-2026.csv`, 912 rows total) had inconsistent formatting typical of manual data entry:

- Order IDs with extra spaces, inconsistent casing, or missing dashes (`ORD -202606 -0072`, `ord-202601-0010`)
- Quantities written as text instead of numbers (`6 pcs`, `2pc`, `two`)
- Prices mixed with currency symbols and text (`$26.24`, `150.00 USD`)
- City names with spelling and capitalization variants (`Saigon`, `Tp.Hcm`, `HCM`, `Ho Chi Minh City`)
- SKU codes in inconsistent formats (`SKU1001` vs `SKU-1001`)
- 26 duplicate orders across files, one of which appeared 3 times
- Missing values in emails and other fields

## The approach

1. **Inspect first, change nothing.** Read all files, compare column names across them, count rows, check for missing values and duplicates before touching any data.
2. **Clean into new columns.** Original columns are never overwritten; cleaned values live in `_Clean` columns so before/after can always be compared.
3. **Standardize with rebuild logic, not blind stripping.** Order IDs and SKUs are rebuilt from their digits using regex rather than just removing stray characters, which avoids corrupting values like `ORD 202601-0048`.
4. **Flag, don't delete.** Rows with unreadable quantities, prices, or dates are flagged in an `Issues` column with their original values preserved, so a human makes the final call — nothing is silently dropped or guessed.
5. **Resolve duplicates safely.** Duplicate IDs are checked against every other column before removal, to confirm they are exact copies and not different orders that happen to share an ID.
6. **Validate every merge.** Catalog lookups are checked for duplicate keys before merging, and row counts are compared before/after every merge to catch silent data duplication.
7. **Self-check at every step.** Each script ends by verifying its own output (row counts match, grouped totals sum back to the overall total, re-opening the exported Excel file matches the in-memory data) instead of assuming the code worked.

## Result

- 912 raw rows → 886 unique orders (26 duplicate copies identified and removed, with the originals kept in a separate sheet for audit)
- All unresolved data issues flagged in an `Issues` column with original values retained, instead of being corrected by assumption
- Final deliverable: a multi-sheet Excel file (`Cleaned`, `Issues`, `Issue_Counts`, `Removed_Duplicates`, `By_Month`, `By_City`, `By_SKU`, `Report`, `Rules`) ready for client review
- A `Rules` sheet documents every cleaning decision in plain language, so the client can verify what was done without reading code

## Tech stack

Python, pandas, openpyxl, regex

## Project structure

```
├── main.py              # full pipeline: load -> inspect -> clean -> flag -> summarize -> export
├── lookups.py           # editable alias table for merging spelling variants (e.g. city names)
├── check.py             # generic folder auditor: column-match check + merge + unique-value report
│                          (reusable on any new folder of CSV/Excel files, not specific to this dataset)
├── sample_data/         # anonymized sample input files
└── output/              # generated reports (not tracked in git)
```

## How to run

```bash
pip install pandas openpyxl
python main.py
```

Outputs `output/Cleaned.xlsx`, `output/Cleaned.csv`, and prints a verification report confirming row counts, revenue totals, and sheet contents match between the in-memory data and the saved file.
