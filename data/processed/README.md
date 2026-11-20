# Processed data

Electricity use for four factories (A, B, C, D), one value per hour, for the whole year 2022.

## Files

| File | What it is | Use it for |
|---|---|---|
| `hourly.parquet` | Cleaned measurements. Some hours are empty where the meter recorded nothing. | Looking at what was really measured. |
| `hourly_filled.parquet` | Same data, but the empty hours are filled with estimates. | Training the forecasting model. |

Parquet is a compact table format. Open it in Python with `pandas.read_parquet("hourly_filled.parquet")`.

## Columns

| Column | Meaning |
|---|---|
| `timestamp` | Start of the hour, Swedish local time (e.g. `2022-03-01 08:00` = 08:00–09:00). |
| `factory` | Which factory: A, B, C or D. |
| `kwh` | Electricity used during that hour, in kWh (assumed unit; the raw files do not say). |
| `is_imputed` | Only in `hourly_filled`. `True` = estimated value, `False` = real measurement. |

## What was changed from the raw files

1. **Dates fixed.** Factories A, B and D were labelled 2024 by mistake. All data is from 2022.
2. **Zeros removed.** A value of 0 means the meter stopped, not that the factory used no power. Zeros became empty values.
3. **Short gaps filled.** A few missing hours (at most 3 in a row, only factory A) were filled by drawing a straight line between the values on either side.
4. **Long gaps estimated** (only in `hourly_filled`). B and C are missing about the last five weeks of the year (B from Nov 28, C from Nov 22).
   - Until Dec 22 they are filled by copying the same weekday and hour from the weeks just before the gap.
   - From Dec 23 they are filled with a typical weekend day, because factories A and D show a Christmas shutdown then.

## Good to know

- **Estimated values are guesses.** When checking how accurate a model is, only use rows where `is_imputed` is `False`.
- **Factory C changes in mid-May.** Its usage is much lower before then (around 40–75 kWh per hour on weekdays, compared with 250–320 after). The data is kept as measured; consider using only the part from mid-May onward for C.
- **Clock changes.** Every day has 24 hours, even on the days in March and October when the clocks change.

## How the files are made

Run from the project folder:

```
.venv/bin/python -m src.preprocessing.clean    # creates hourly.parquet
.venv/bin/python -m src.preprocessing.impute   # creates hourly_filled.parquet
```
