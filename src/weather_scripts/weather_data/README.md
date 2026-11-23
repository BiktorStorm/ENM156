# Weather Data (15-minute intervals)

Historical SMHI weather observations for the Vårgårda region resampled and linearly interpolated into 15-minute intervals.

## Files

| File | Range | Rows | Description |
|---|---|---|---|
| `weather_2022_2023.csv` | 2022-01-01 to 2023-12-31 | 70,080 | Matches the factory electricity dataset timestamps directly through 2023. |
| `weather_2022_2025.csv` | 2022-01-01 to 2025-12-31 | 140,256 | Extended 4-year period for forecasting and analysis. |

*(Convenience symlinks `weather_15min_2022_2023.csv` and `weather_15min_2022_2025.csv` point to these files).*

## Columns

| Column | Type | Unit | Description | Station Source |
|---|---|---|---|---|
| `timestamp` | Datetime (`YYYY-MM-DD HH:MM:SS`) | - | 15-minute timestamp aligned directly with `data/15_min_interval/15_min_interval.csv`. | - |
| `Lufttemperatur` | Float | °C | Air temperature (momentanvärde) | Gendalen (station 82110, 19.4 km from Vårgårda) |
| `Vindhastighet` | Float | m/s | Wind speed (10-min mean) | Rångedala A (station 73480, 32.2 km from Vårgårda) |
| `Total molnmängd` | Float | % | Total cloud cover (0–100%) | Rångedala A (station 73480, 32.2 km from Vårgårda) |

## Transformations Applied

1. **Station Selection:** Automatically selected the closest SMHI meteorological station covering the desired period for each parameter.
2. **Timestamp Alignment:** Reindexed to match the 15-minute intervals (`:00`, `:15`, `:30`, `:45`) directly matching `data/15_min_interval/15_min_interval.csv`.
3. **Linear Time Interpolation:** Missing hours and intermediate 15-minute timestamps are smoothly interpolated using time-based linear interpolation (`method="time"`).
4. **Boundary Bracketing:** Included historical records immediately before 2022 and after 2025 to avoid any `NaN` values at the beginning or end of the series.

## How the files are made

Run from the project root:

```bash
script/.venv/bin/python -m src.weather_scripts.main
```
