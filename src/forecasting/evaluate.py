"""Rolling-origin backtest for factory electricity forecasts, compared against naive baselines.

A model is any function `predict(history, future) -> array of len(future)`:
  - history: pd.Series of 15-min kWh before the forecast origin (index = timestamp, name = factory).
    Choose your own training data by slicing it, e.g. history["2022-05-15":].
  - future:  pd.DatetimeIndex of the 15-min intervals to forecast. Look up weather/calendar features for it yourself.
The model is called once per origin, so it retrains on all data up to that point.
Time spans (horizons, lags, naive periods) are pd.Timedelta, so nothing depends on the data's step size.

Usage from a notebook or another script:
    from src.forecasting.evaluate import backtest, summary
    results = backtest({"my_model": my_predict}, horizon=pd.Timedelta("48h"))
    print(summary(results))
    results.groupby(["model", "lead"]).abs_err.mean()   # error by steps ahead
"""
import numpy as np
import pandas as pd

from src.preprocessing.load_data import PROJECT_ROOT

DATA_PATH = PROJECT_ROOT / "data" / "15_min_interval" / "15_min_filled.parquet"
HORIZONS = {"48h": pd.Timedelta("48h"), "2w": pd.Timedelta("14D")}
REFERENCE = "naive_week"


def naive(period):
    """Repeat the last `period` (a Timedelta) of history over the forecast window."""
    def predict(history, future):
        last = history[history.index > history.index[-1] - period]
        return np.resize(last.to_numpy(), len(future))
    return predict


BASELINES = {"naive_day": naive(pd.Timedelta("1D")), REFERENCE: naive(pd.Timedelta("7D"))}


def load():
    return pd.read_parquet(DATA_PATH).set_index("timestamp")


def backtest(models, horizon, factories="ABCD", start="2022-06-01", step=None):
    """Forecast `horizon` (a Timedelta) from each origin and return one row per (model, factory, origin, lead).

    Origins run from `start` every `step` (default: daily for <= 48 h, weekly otherwise).
    The naive baselines are always included.
    """
    kwh = load()
    freq = kwh.index[1] - kwh.index[0]
    step = step or ("1D" if horizon <= pd.Timedelta("48h") else "7D")
    origins = pd.date_range(start, kwh.index[-1] - horizon + freq, freq=step)
    models = {**BASELINES, **models}

    rows = []
    for factory in factories:
        series = kwh[factory].dropna()
        for origin in origins:
            history = series[series.index < origin]
            future = pd.date_range(origin, origin + horizon, freq=freq, inclusive="left")
            for name, predict in models.items():
                pred = np.asarray(predict(history, future), dtype=float)
                if pred.shape != (len(future),) or not np.isfinite(pred).all():
                    raise ValueError(f"{name} returned bad predictions for {factory} at {origin}")
                rows.append(pd.DataFrame({
                    "model": name, "factory": factory, "origin": origin,
                    "lead": np.arange(1, len(future) + 1), "timestamp": future, "pred": pred,
                    "actual": kwh.loc[future, factory].to_numpy(),
                }))
    results = pd.concat(rows, ignore_index=True)
    results["abs_err"] = (results.pred - results.actual).abs()
    return results


def summary(results):
    """MAE, RMSE, nMAE and MAE relative to naive_week (< 1 = better than naive), on all points."""
    scored = results[results.actual.notna()]
    g = scored.groupby(["factory", "model"])
    table = pd.DataFrame({
        "MAE": g.abs_err.mean(),
        "RMSE": g.abs_err.apply(lambda e: np.sqrt((e ** 2).mean())),
        "nMAE": g.abs_err.mean() / g.actual.mean(),
        "n_points": g.size(),
    })
    table["rel_MAE"] = table.MAE / table.MAE.xs(REFERENCE, level="model").reindex(table.index, level="factory")
    return table.round(3)


def _self_check():
    # a perfectly weekly 15-min series must be forecast exactly by naive_week
    week = np.arange(7 * 96.0)
    idx = pd.date_range("2022-01-01", periods=3 * len(week), freq="15min")
    weekly = pd.Series(np.tile(week, 3), index=idx)
    future = pd.date_range(idx[-1] + pd.Timedelta("15min"), periods=2 * len(week), freq="15min")
    assert np.array_equal(BASELINES[REFERENCE](weekly, future), np.tile(week, 2))


if __name__ == "__main__":
    _self_check()
    for label, horizon in HORIZONS.items():
        print(f"\n=== {label} horizon ===")
        print(summary(backtest({}, horizon)).to_string())
