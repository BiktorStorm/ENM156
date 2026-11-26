"""Holiday flag: Swedish public + de facto holidays (Midsummer/Christmas/New Year's Eve) plus factory shutdowns."""
import holidays
import pandas as pd

# found in the 2022 data as weekday usage far below normal; C's Christmas is imputed data (weekend profile)
# shortcut: 2022 dates only, add each new year's shutdown dates here when they are known
SHUTDOWNS = {
    "A": [("2022-07-13", "2022-08-04"), ("2022-12-23", "2022-12-31")],
    "C": [("2022-07-13", "2022-07-29"), ("2022-12-23", "2022-12-31")],
}


def is_holiday(index, factory):
    """Boolean array: True for every timestamp in `index` that falls on a holiday or a shutdown day of `factory`."""
    days = index.normalize()
    calendar = holidays.Sweden(years=sorted(set(index.year)), categories=("public", "de_facto"))
    flag = days.isin(pd.to_datetime(list(calendar)))
    for start, end in SHUTDOWNS.get(factory, []):
        flag |= (days >= start) & (days <= end)
    return flag


if __name__ == "__main__":
    idx = pd.to_datetime(["2022-06-24 10:15", "2022-06-27 10:15", "2022-07-20 03:00", "2022-12-24 23:45", "2023-01-06 12:00"])
    assert list(is_holiday(idx, "A")) == [True, False, True, True, True]
    assert list(is_holiday(idx, "B")) == [True, False, False, True, True]
    print("ok")
