"""Write a 2-week forecast of combined A+B+C+D usage to JSON: {"2023-01-01T00:00:00": 512.3, ...}, kWh per 15 min.

The first 48 h come from the 48 h model, the rest from the 2-week model.

Run from the project folder:
    .venv/bin/python -m src.forecasting.forecast data/forecast.json
    .venv/bin/python -m src.forecasting.forecast data/forecast.json -pd 2022-10-03
"""
import argparse
import json

import pandas as pd
from src.forecasting.evaluate import HORIZONS, load
from src.forecasting.models import lgbm
from src.preprocessing.load_data import PROJECT_ROOT

MODELS = {"lgbm": lgbm.predict}


def parse_args():
    parser = argparse.ArgumentParser(description="Script to get a prediction of power usage for the next 2 weeks")
    parser.add_argument(
        "destination",
        help = "destination of the forecast.json relative to the project root"
    )
    parser.add_argument(
        "-m",
        "--model",
        choices=list(MODELS),
        default="lgbm",
        help="What model to use, default: LGBM"
    )
    parser.add_argument(
        "-pd",
        "--predictiondate",
        type=pd.Timestamp,
        help="Start of the forecast, e.g. 2022-10-03 or '2022-10-03 06:15'. "
             "The model trains only on data before it. Default: right after the last data point"
    )
    return parser.parse_args()


def forecast(predict, start=None):
    """Stitched 2-week forecast of the total of all factories, as {iso timestamp: kWh}."""
    kwh = load()
    freq = kwh.index[1] - kwh.index[0]
    first, end = kwh.index[0] + 3 * lgbm.WEEK, kwh.index[-1] + freq
    start = end if start is None else start
    if not first <= start <= end or start != start.floor(freq):
        raise ValueError(f"prediction date must be a multiple of {freq} between {first} and {end}")

    future = pd.date_range(start, start + HORIZONS["2w"], freq=freq, inclusive="left")
    n_short = int(HORIZONS["48h"] / freq)
    total = 0
    for factory in kwh.columns:
        history = kwh.loc[kwh.index < start, factory]
        pred = predict(history, future)
        pred[:n_short] = predict(history, future[:n_short])  # stitch: the 48 h model is better early on
        total = total + pred
    return {t.isoformat(): round(float(v), 2) for t, v in zip(future, total)}


if __name__ == "__main__":
    args = parse_args()
    path = PROJECT_ROOT / args.destination
    result = forecast(MODELS[args.model], args.predictiondate)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    print(f"Wrote {len(result)} values from {next(iter(result))} to {path.relative_to(PROJECT_ROOT)}")
