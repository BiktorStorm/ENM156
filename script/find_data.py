from datetime import datetime, timezone
import io
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import requests
from close_stations import get_closest_stations

def find_dataa(p):

    closest_30 = get_closest_stations(p)
    dt_2024_min = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    dt_smhi_min = int(dt_2024_min.timestamp() * 1000)
    dt_2024_max = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    dt_smhi_max = int(dt_2024_max.timestamp() * 1000)


    stations_close_by = []
    base_url = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/{p}.json"

    response1 = requests.get(base_url)
    data1 = response1.json()

    city = "Station not found"
    id = "ID not found"
    stations = data1["station"]

    done = False

    for s in closest_30:
        if done == False:
            city = None
            id = None
            # print("Checking: " + s)
            for station in stations:
                if station["name"] == s:
                    city = station["name"]
                    id = station["id"]

                    url2 = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/{p}/station/{id}.json"
                    response2 = requests.get(url2)
                    data2 = response2.json()

                    from_ = datetime.fromtimestamp(data2["from"]/1000)
                    to_ = datetime.fromtimestamp(data2["to"]/1000)

                    # print(from_)
                    # print(to_)

                    if (int(from_.timestamp()*1000) <= dt_smhi_min and
                        int(to_.timestamp()*1000) >= dt_smhi_max):
                        print(f"The closest weatherstaion is {city}!")
                        done = True

            if city == None:
                print("Couldn't find the station")
            print("")

    url3 = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/{p}/station/{id}/period/corrected-archive.json"
    response3 = requests.get(url3)
    data3 = response3.json()

    url4 = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/{p}/station/{id}/period/corrected-archive/data.csv"
    lines = requests.get(url4).text.splitlines()

    header_idx = next(
        i for i, line in enumerate(lines)
        if line.startswith(("Datum;", "Från Datum Tid (UTC);"))
    )

    clean_csv = "\n".join(lines[header_idx:])
    df = pd.read_csv(io.StringIO(clean_csv), sep=";", usecols=[0, 1, 2])

    print(df)


    # Efter att ha kört detta så är det Gendalen som är närmsta väderstation.