from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw_data"
OUTPUT_PATH = PROJECT_ROOT / "data" / "interim" / "hourly.csv"

START_DATE = "2022-01-01"
HEADER_MARKER = "Månad"
HOUR_COLUMNS = [f"{h:02d}-{h + 1:02d}" for h in range(24)]


def _detect_format(path: Path) -> tuple[str, str, int]:
    with open(path, encoding="utf-8-sig") as f:
        lines = f.read().splitlines()

    sep = ";" if lines[0].count(";") > lines[0].count(",") else ","
    decimal = "," if sep == ";" else "."
    header_row = next(i for i, line in enumerate(lines) if line.startswith(HEADER_MARKER))
    return sep, decimal, header_row


def read_raw(path: Path) -> pd.DataFrame:
    sep, decimal, header_row = _detect_format(path)
    df = pd.read_csv(
        path,
        sep=sep,
        decimal=decimal,
        skiprows=header_row,
        encoding="utf-8-sig",  # strips the BOM
    )

    # Keep only day rows (drops blank trailing lines) and named columns (drops the empty ones).
    df = df[df[HEADER_MARKER].notna()].reset_index(drop=True)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    missing = set(HOUR_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: missing hour columns {sorted(missing)}")
    df[HOUR_COLUMNS] = df[HOUR_COLUMNS].apply(pd.to_numeric, errors="coerce")
    return df


def read_stated_year(path: Path) -> int:
    sep, _, _ = _detect_format(path)
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            if line.startswith("År"):
                return int(line.split(sep)[1])
    raise ValueError(f"{path.name}: no År row in header")


def parse_file(path: Path) -> pd.DataFrame:
    return read_raw(path)[HOUR_COLUMNS]


def _assign_dates(wide: pd.DataFrame) -> pd.DataFrame:
    wide = wide.copy()
    wide.index = pd.date_range(START_DATE, periods=len(wide), freq="D", name="date")

    # Only trim empty rows at the end (template padding); an empty day in the
    # middle is real missing data and must keep its place so later dates stay correct.
    has_data = wide.notna().any(axis=1)
    last_valid = has_data[has_data].index.max()
    return wide.loc[:last_valid]


def _to_long(wide: pd.DataFrame, factory: str) -> pd.DataFrame:
    long = wide.reset_index().melt(id_vars="date", var_name="hour", value_name="kwh")
    hour = long["hour"].str[:2].astype(int)
    long["timestamp"] = long["date"] + pd.to_timedelta(hour, unit="h")
    long["factory"] = factory
    return long[["timestamp", "factory", "kwh"]].sort_values("timestamp").reset_index(drop=True)


def load_factory(path: Path) -> pd.DataFrame:
    factory = path.stem.split("_")[-1]
    wide = parse_file(path)
    wide = _assign_dates(wide)
    return _to_long(wide, factory)


def load_all(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    paths = sorted(raw_dir.glob("Data_*.csv"))
    if not paths:
        raise FileNotFoundError(f"No Data_*.csv files found in {raw_dir}")
    return pd.concat([load_factory(p) for p in paths], ignore_index=True)


def main() -> None:
    df = load_all()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(df)} rows to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    summary = df.groupby("factory").agg(
        rows=("kwh", "size"),
        start=("timestamp", "min"),
        end=("timestamp", "max"),
        missing=("kwh", lambda s: s.isna().sum()),
        zeros=("kwh", lambda s: (s == 0).sum()),
    )
    print(summary.to_string())


if __name__ == "__main__":
    main()
