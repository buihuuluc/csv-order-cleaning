import pandas as pd

old = pd.read_excel('output/Cleaned_old.xlsx', sheet_name=None)
new = pd.read_excel('output/Cleaned.xlsx', sheet_name=None)

for name in new:
    same = name in old and old[name].shape == new[name].shape
    print(f'{name:<20} old={old[name].shape if name in old else None} new={new[name].shape} {"OK" if same else "DIFFERENT"}')