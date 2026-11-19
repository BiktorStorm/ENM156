import math
import requests

VARGARDA_LAT = 58.023
VARGARDA_LON = 12.854

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def get_closest_stations(p, limit=30):
    url = f"https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/{p}.json"
    stations = requests.get(url).json()["station"]

    stations_with_dist = []
    for s in stations:
        dist = haversine_km(VARGARDA_LAT, VARGARDA_LON, s["latitude"], s["longitude"])
        stations_with_dist.append((dist, s["name"]))

    stations_with_dist.sort(key=lambda x: x[0])

    return [name for _, name in stations_with_dist[:limit]]