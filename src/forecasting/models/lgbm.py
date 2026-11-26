"""LightGBM forecast on calendar features, a holiday/shutdown flag and the load at the same time 1-3 weeks earlier."""
import json

import lightgbm as lgb
import pandas as pd

from src.forecasting.evaluate import HORIZONS, backtest, summary
from src.forecasting.shutdowns import is_holiday
from src.preprocessing.load_data import PROJECT_ROOT

WEEK = pd.Timedelta("7D")
RESULTS_PATH = PROJECT_ROOT / "src" / "forecasting" / "evaluation_results" / "lgbm.json"


def features(kwh, index, lags):
    # kwh holds history only; a lag is usable only if it is longer than the forecast window
    X = pd.DataFrame({"hour": index.hour, "minute": index.minute, "weekday": index.day_of_week,
                      "is_holiday": is_holiday(index, kwh.name)}, index=index)
    for lag in lags:
        X[f"lag_{lag.days}d"] = kwh.shift(freq=lag).reindex(index).to_numpy()
    return X


def predict(history, future):
    lags = [lag for lag in (WEEK, 2 * WEEK, 3 * WEEK) if lag > future[-1] - future[0]]
    X = features(history, history.index, lags)
    model = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.05, num_leaves=31, verbose=-1,
                              n_jobs=1)  # threads only add overhead on ~30k rows
    model.fit(X, history.to_numpy(), categorical_feature=["weekday"])
    return model.predict(features(history, future, lags))


def evaluate(path=RESULTS_PATH):
    """Backtest against the naive baselines on both horizons and write the summary tables to JSON."""
    output = {"model": "lgbm", "created": pd.Timestamp.now().isoformat(timespec="seconds")}
    for label, horizon in HORIZONS.items():
        table = summary(backtest({"lgbm": predict}, horizon))
        print(f"\n=== {label} horizon ===\n{table.to_string()}")
        output[label] = table.reset_index().to_dict("records")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    evaluate()
