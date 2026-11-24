"""Rolling-origin backtest for factory electricity forecasts, compared against naive baselines.

A model is any function `predict(history, future) -> array of len(future)`:
  - history: pd.Series of hourly kWh before the forecast origin (index = timestamp, name = factory).
    Choose your own training data by slicing it, e.g. history["2022-05-15":] or history.iloc[-8 * 168:].
  - future:  pd.DatetimeIndex of the hours to forecast. Look up weather/calendar features for it yourself.
The model is called once per origin, so it retrains on all data up to that point.

Usage from a notebook or another script:
    from src.forecasting.evaluate import backtest, summary
    results = backtest({"my_model": my_predict}, horizon=48)
    print(summary(results))
    results.groupby(["model", "lead"]).abs_err.mean()   # error by hours ahead
"""
import numpy as np
import pandas as pd

from src.preprocessing.load_data import PROJECT_ROOT

DATA_PATH = PROJECT_ROOT / "data" / "processed" / "hourly_filled.parquet"
HORIZONS = {"48h": 48, "2w": 14 * 24}
REFERENCE = "naive_week"


def naive(period_hours):
    """Repeat the last `period_hours` of history over the forecast window."""
    def predict(history, future):
        return np.resize(history.iloc[-period_hours:].to_numpy(), len(future))
    return predict


BASELINES = {"naive_day": naive(24), REFERENCE: naive(168)}


def load():
    df = pd.read_parquet(DATA_PATH)
    return (df.pivot(index="timestamp", columns="factory", values="kwh"),
            df.pivot(index="timestamp", columns="factory", values="is_imputed"))


def backtest(models, horizon, factories="ABCD", start="2022-06-01", step=None):
    """Forecast `horizon` hours from each origin and return one row per (model, factory, origin, lead).

    Origins run from `start` every `step` (default: daily for <= 48 h, weekly otherwise).
    The naive baselines are always included.
    """
    kwh, imputed = load()
    step = step or ("1D" if horizon <= 48 else "7D")
    last_origin = kwh.index[-1] - pd.Timedelta(hours=horizon - 1)
    origins = pd.date_range(start, last_origin, freq=step)
    models = {**BASELINES, **models}

    rows = []
    for factory in factories:
        series = kwh[factory].dropna()
        for origin in origins:
            history = series[series.index < origin]
            future = pd.date_range(origin, periods=horizon, freq="h")
            for name, predict in models.items():
                pred = np.asarray(predict(history, future), dtype=float)
                if pred.shape != (horizon,) or not np.isfinite(pred).all():
                    raise ValueError(f"{name} returned bad predictions for {factory} at {origin}")
                rows.append(pd.DataFrame({
                    "model": name, "factory": factory, "origin": origin,
                    "lead": np.arange(1, horizon + 1), "timestamp": future, "pred": pred,
                    "actual": kwh.loc[future, factory].to_numpy(),
                    "is_imputed": imputed.loc[future, factory].to_numpy(),
                }))
    results = pd.concat(rows, ignore_index=True)
    results["abs_err"] = (results.pred - results.actual).abs()
    return results


def summary(results):
    """MAE, RMSE, nMAE and MAE relative to naive_week (< 1 = better than naive), on measured hours only."""
    scored = results[~results.is_imputed.astype(bool) & results.actual.notna()]
    g = scored.groupby(["factory", "model"])
    table = pd.DataFrame({
        "MAE": g.abs_err.mean(),
        "RMSE": g.abs_err.apply(lambda e: np.sqrt((e ** 2).mean())),
        "nMAE": g.abs_err.mean() / g.actual.mean(),
        "n_hours": g.size(),
    })
    table["rel_MAE"] = table.MAE / table.MAE.xs(REFERENCE, level="model").reindex(table.index, level="factory")
    return table.round(3)


def _self_check():
    # a perfectly weekly series must be forecast exactly by naive_week
    idx = pd.date_range("2022-01-01", periods=3 * 168, freq="h")
    weekly = pd.Series(np.tile(np.arange(168.0), 3), index=idx)
    future = pd.date_range(idx[-1] + pd.Timedelta(hours=1), periods=336, freq="h")
    assert np.array_equal(BASELINES[REFERENCE](weekly, future), np.tile(np.arange(168.0), 2))


if __name__ == "__main__":
    _self_check()
    for label, horizon in HORIZONS.items():
        print(f"\n=== {label} horizon ===")
        print(summary(backtest({}, horizon)).to_string())
