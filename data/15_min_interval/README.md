# 15-minute interval data

Electricity consumption for four factories (A, B, C, D) resampled into 15-minute intervals for the whole year 2022.

Derived from `data/processed/hourly_filled.parquet`.

## Files

| File | Format | Description |
|---|---|---|
| `15_min_interval.parquet` | Parquet | 15-minute consumption with factories as separate columns. Compact format. |
| `15_min_interval.csv` | CSV | Corresponding plain-text CSV file. |

(Aliases `15_min_filled.parquet` / `.csv` and `15_min.parquet` / `.csv` are symlinked to these files for convenience).

## Columns

| Column | Type | Meaning |
|---|---|---|
| `timestamp` | Datetime | Start of the 15-minute interval, Swedish local time (e.g. `2022-01-01 00:00:00`, `2022-01-01 00:15:00`). |
| `A` | Float | Electricity used during the 15-minute interval for Factory A (kWh). |
| `B` | Float | Electricity used during the 15-minute interval for Factory B (kWh). |
| `C` | Float | Electricity used during the 15-minute interval for Factory C (kWh). |
| `D` | Float | Electricity used during the 15-minute interval for Factory D (kWh). |

## Transformations Applied

1. **Wide format (separate factory columns):** Each factory (A, B, C, D) has its own column instead of being stacked in a single `factory` column.
2. **15-minute intervals:** Each hour is divided into four 15-minute intervals (`:00`, `:15`, `:30`, `:45`).
3. **Consumption division:** Hourly `kwh` values are divided by 4 so each 15-minute quarter carries equal consumption ($1/4$ of the hour's total).
4. **Hour switching:** Within each hour, all four 15-minute intervals share the same value, switching to a new value at the start of each hour.
5. **Conservation of energy:** The sum of the four 15-minute intervals equals the original hourly consumption. Total yearly consumption per factory is identical.

## How the files are made

Run from the project root:

```bash
script/.venv/bin/python -m src.preprocessing.to_15min
```
