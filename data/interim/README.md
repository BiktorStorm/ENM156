# Interim data

Electricity use for four factories (A, B, C, D), one value per hour, for the whole year 2022.
This is the raw data put into one tidy table. **Nothing has been cleaned yet**.

## Files

| File | What it is | Use it for |
|---|---|---|
| `hourly.csv` | All four raw files combined into one table, with correct dates. Values are exactly as in the raw files. | Checking the original numbers, or redoing the cleaning differently. |

CSV is a plain text table. It opens in Excel or in Python with `pandas.read_csv("hourly.csv")`.

## Columns

| Column | Meaning |
|---|---|
| `timestamp` | Start of the hour, Swedish local time (e.g. `2022-03-01 08:00` = 08:00–09:00). |
| `factory` | Which factory: A, B, C or D. |
| `kwh` | Electricity used during that hour, in kWh (assumed unit; the raw files do not say). |

## What was changed from the raw files

1. **One table instead of four.** The raw files have one row per day and 24 hour columns. Here every hour is its own row (8,760 rows per factory).
2. **File formats unified.** The raw files use different separators and decimal marks (`;` and `12,5` vs `,` and `12.5`). This file uses one format.
3. **Dates fixed.** Factories A, B and D were labelled 2024 by mistake. All data is from 2022, so the days are numbered from 1 January 2022.

## Good to know

- **Zeros are still in the data.** A value of 0 means the meter stopped, not that the factory used no power. Factory A has 5 zero hours; B and C have about five weeks of zeros at the end of the year (B from Nov 28, C from Nov 22).
- **Factory C changes in mid-May.** Its usage is much lower before then (around 40–75 kWh per hour on weekdays, compared with 250–320 after).
- **Clock changes.** Every day has 24 hours, even on the days in March and October when the clocks change.

## How the file is made

Run from the project folder:

```
.venv/bin/python -m src.preprocessing.load_data   # creates hourly.csv
```
