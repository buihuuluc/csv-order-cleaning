import re   
import pandas as pd

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