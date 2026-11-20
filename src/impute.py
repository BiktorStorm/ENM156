import numpy as np
import pandas as pd

from src.load_data import PROJECT_ROOT

INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "hourly.parquet"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "hourly_filled.parquet"
# A and D both drop to holiday level from this date, so B and C are assumed to as well
CHRISTMAS_START = pd.Timestamp("2022-12-23")
WEEK = pd.Timedelta(weeks=1)


def fill_trailing_block(kwh):
    """Fill a trailing NaN block: copy the weeks just before it, then a weekend profile from Christmas."""
    missing = kwh.index[kwh.isna()]
    if missing.empty:
        return kwh
    start = missing[0]
    assert kwh[start:].isna().all(), "only a trailing NaN block can be filled"

    # shift by enough whole weeks that every source hour lies before the block
    weeks_back = int(np.ceil((kwh.index[-1] - start + pd.Timedelta(hours=1)) / WEEK))
    filled = kwh.copy()
    filled[missing] = kwh.reindex(missing - weeks_back * WEEK).to_numpy()

    last_month = kwh[start - 4 * WEEK : start - pd.Timedelta(hours=1)]
    weekend_profile = last_month[last_month.index.day_of_week >= 5].groupby(lambda t: t.hour).mean()
    holiday = missing[missing >= CHRISTMAS_START]
    filled[holiday] = weekend_profile.reindex(holiday.hour).to_numpy()
    return filled


def main():
    df = pd.read_parquet(INPUT_PATH)
    df["is_imputed"] = df["kwh"].isna()
    df["kwh"] = df.groupby("factory")["kwh"].transform(
        lambda s: fill_trailing_block(s.set_axis(df.loc[s.index, "timestamp"])).to_numpy()
    )
    assert df["kwh"].notna().all()
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print("Imputed hours per factory:", df.groupby("factory")["is_imputed"].sum().to_dict())


if __name__ == "__main__":
    main()
