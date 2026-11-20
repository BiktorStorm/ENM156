from src.load_data import PROJECT_ROOT, load_all

OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "hourly.parquet"
MAX_GAP_HOURS = 6


def fill_short_gaps(kwh):
    is_nan = kwh.isna()
    run_id = (is_nan != is_nan.shift()).cumsum()
    run_len = is_nan.groupby(run_id).transform("size")
    short = is_nan & (run_len <= MAX_GAP_HOURS)
    return kwh.where(~short, kwh.interpolate(limit_area="inside"))


def clean(df):
    df = df.copy()
    df["kwh"] = df["kwh"].mask(df["kwh"] == 0)
    df["kwh"] = df.groupby("factory")["kwh"].transform(fill_short_gaps)
    return df


def main():
    df = clean(load_all())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"Wrote {len(df)} rows to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print("NaN hours per factory:", df["kwh"].isna().groupby(df["factory"]).sum().to_dict())


if __name__ == "__main__":
    import pandas as pd

    # self-check: a 2-hour gap is filled, a 7-hour gap is not
    s = pd.Series([1.0, None, None, 4.0] + [None] * 7 + [5.0])
    out = fill_short_gaps(s)
    assert out[:4].tolist() == [1.0, 2.0, 3.0, 4.0] and out[4:11].isna().all()
    main()
