from pathlib import Path
import numpy as np
import pandas as pd

from src.preprocessing.load_data import PROJECT_ROOT

INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "hourly_filled.parquet"
OUTPUT_DIR = PROJECT_ROOT / "data" / "15_min_interval"
OUTPUT_PARQUET = OUTPUT_DIR / "15_min_interval.parquet"
OUTPUT_CSV = OUTPUT_DIR / "15_min_interval.csv"


def transform_to_15min(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot factories into individual columns, split hourly timestamps into
    15-minute intervals, and divide kWh by 4 so each 15-minute interval
    shares equal consumption across the hour.
    """
    # 1. Pivot factories into columns
    pivoted = df.pivot(index="timestamp", columns="factory", values="kwh")
    pivoted.columns.name = None

    # 2. Divide hourly kWh values by 4
    pivoted_15min = pivoted / 4.0

    # 3. Create full 15-minute index (starts at the first hour, ends 45 mins after the last hour)
    start_ts = pivoted_15min.index.min()
    end_ts = pivoted_15min.index.max() + pd.Timedelta(minutes=45)
    full_idx = pd.date_range(start=start_ts, end=end_ts, freq="15min", name="timestamp")

    # 4. Forward fill across each hour's 4 quarters (:00, :15, :30, :45)
    df_15min = pivoted_15min.reindex(full_idx, method="ffill").reset_index()

    # Validation checks
    assert len(df_15min) == len(pivoted) * 4, f"Expected {len(pivoted) * 4} rows, got {len(df_15min)}"
    assert np.allclose(
        df.groupby("factory")["kwh"].sum().values,
        df_15min[["A", "B", "C", "D"]].sum().values,
    ), "Yearly totals per factory do not match original!"

    return df_15min


def main() -> None:
    df = pd.read_parquet(INPUT_PATH)
    df_15min = transform_to_15min(df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save primary files
    df_15min.to_parquet(OUTPUT_PARQUET, index=False)
    df_15min.to_csv(OUTPUT_CSV, index=False)
    print(f"Wrote {len(df_15min)} rows to {OUTPUT_PARQUET.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {len(df_15min)} rows to {OUTPUT_CSV.relative_to(PROJECT_ROOT)}")

    # Also create symlinks for convenience (e.g. 15_min_filled and 15_min)
    for alias_stem in ["15_min_filled", "15_min"]:
        alias_p = OUTPUT_DIR / f"{alias_stem}.parquet"
        alias_c = OUTPUT_DIR / f"{alias_stem}.csv"
        if not alias_p.exists():
            alias_p.symlink_to(OUTPUT_PARQUET.name)
        if not alias_c.exists():
            alias_c.symlink_to(OUTPUT_CSV.name)


if __name__ == "__main__":
    main()
