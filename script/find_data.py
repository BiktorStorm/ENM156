from datetime import datetime, timezone
import io
import pandas as pd
import requests
from close_stations import get_closest_stations

def find_dataa(p):
    closest_30 = get_closest_stations(p)
    dt_2024_min = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    dt_smhi_min = int(dt_2024_min.timestamp() * 1000)
    dt_2024_max = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    dt_smhi_max = int(dt_2024_max.timestamp() * 1000)

    base_url = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/{p}.json"
    stations = requests.get(base_url).json()["station"]

    station_id = None

    for station_name, dist_km in closest_30:
        for station in stations:
            if station["name"] == station_name:
                cand_id = station["id"]

                url2 = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/{p}/station/{cand_id}.json"
                data2 = requests.get(url2).json()

                if data2["from"] <= dt_smhi_min and data2["to"] >= dt_smhi_max:
                    station_id = cand_id
                    print(f"The closest weather station is {station_name} ({dist_km:.1f} km from Vårgårda)!")
                    break
        if station_id is not None:
            break

    if station_id is None:
        print("No station found covering the full 2024 period among the 30 closest stations.")
        return None

    url4 = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/{p}/station/{station_id}/period/corrected-archive/data.csv"
    lines = requests.get(url4).text.splitlines()

    header_idx = next(
        i for i, line in enumerate(lines)
        if line.startswith(("Datum;", "Från Datum Tid (UTC);", "Representativt dygn;"))
    )

    clean_csv = "\n".join(lines[header_idx:])
    df = pd.read_csv(io.StringIO(clean_csv), sep=";", usecols=[0, 1, 2])

    print(df)
    return df