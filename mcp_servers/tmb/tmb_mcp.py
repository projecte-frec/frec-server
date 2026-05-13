from datetime import datetime
import json
import os
import pandas as pd
import pytz
import requests
import sys
import unicodedata
from dotenv import load_dotenv
from fastmcp import FastMCP
import rapidfuzz
from typing import Any, Dict, Literal
from copy import deepcopy

# ========================================================
#
#  MCP server to access TMB WMS API (GetFeatureInfo)
#
# ========================================================

# ========================================================
#  Global params

_stop_info: "TMB_Stop_info | None" = None
_normalized_lookup: dict[str, str] | None = None

# ========================================================
#  Auxiliary classes
# TMB API connection


class TMB_API:
    # ----------------------------------------------------
    # Prepare connection to API to retrieve data
    def __init__(self, app_id: str, app_key: str):
        self.base_url = "https://api.tmb.cat/v1/"
        self.app_id = app_id
        self.app_key = app_key

    # send request to server
    def call_server(self, endpoint, request_data=None):
        request_data = request_data or {}
        request_data["app_id"] = self.app_id
        request_data["app_key"] = self.app_key
        response = requests.get(self.base_url + endpoint, params=request_data)
        response.raise_for_status()
        return response.json()

    # ----------------------------------------------------
    # Generic GetFeatureInfo request
    # ----------------------------------------------------

    def get_route_plan(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        currenttime: datetime,
        arriveBy: bool,
        showIntermediateStops: bool,
        mode: set[Literal["TRANSIT"] | Literal["WALK"]] | None = None
    ):
        mode = mode or {"TRANSIT"}
        endpoint = "planner/plan"
        request_data = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "fromPlace": f'{origin[0]},{origin[1]}',
            "toPlace": f'{destination[0]},{destination[1]}',
            "date":currenttime.strftime("%m-%d-%Y"),
            "time":currenttime.strftime("%I:%M%p").lower(),
            "arriveBy":arriveBy,
            "showIntermediateStops": showIntermediateStops,
            "mode":",".join(mode),
        }
        response = requests.get(self.base_url + endpoint, params=request_data)
        response.raise_for_status()
        return response.json()


def get_stop_info() -> "TMB_Stop_info":
    global _stop_info
    if _stop_info is None:
        _stop_info = TMB_Stop_info()
    return _stop_info

def get_time_barcelona()-> datetime:
    return datetime.now().astimezone(pytz.timezone("Europe/Madrid"))

class TMB_Stop_info:
    def __init__(self) -> None:
        self.df = pd.read_csv("./mcp_servers/tmb/resources/stops.txt")
        self.df['normalized_stop_name'] = [self.normalize_stop_name(stop_name) for stop_name in self.df['stop_name']]

    def normalize_stop_name(self, text: str) -> str:
        text = text.lower().strip()
        text = unicodedata.normalize("NFD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        return text

    def get_stop_by_id(self, stop_id: str) -> dict:
        d = self.df[self.df['stop_id'] == stop_id].iloc[0].to_dict()
        d = {k: None if pd.isna(v) else v for k,v in d.items()}
        return d

    def locate_stop_by_name_fuzzy(self, stop_name: str, threshold: int = 80) -> dict | None:
        result = rapidfuzz.process.extractOne(
            self.normalize_stop_name(stop_name),
            self.df['normalized_stop_name'],
            scorer=rapidfuzz.fuzz.WRatio
        )
        if result is not None:
            _, confidence, stop_idx = result
            if confidence < threshold:
                return None

            found_stop = self.df.iloc[stop_idx]
            fuel = 5
            while found_stop['parent_station']:
                found_stop = self.get_stop_by_id(found_stop['parent_station'])
                fuel -= 1
                if fuel <= 0:
                    break
            return found_stop
        else:
            return None

# ========================================================
# Auxiliary functions

def remove_keys(d: dict, keys: list[Any]):
    for key in keys:
        if key in d:
            del d[key]

def keep_keys(d: dict, keys_to_keep: list[Any]):
    keys_in_dict = d.keys()
    keys_to_remove = [k for k in keys_in_dict if k not in keys_to_keep]
    remove_keys(d, keys_to_remove)

def convert_to_hms(seconds):
    seconds = seconds % (24 * 3600)
    hour = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60
    if hour >0:
        time=f"{hour}h i {minutes:02} minuts [{hour}:{minutes:02}]"
    elif minutes >0:
        time=f"{minutes:02} minuts"
    return time

def cleanup_plan(plan: dict) -> dict:
    clean_plan = deepcopy(plan)
    itineraries = clean_plan["itineraries"]
    itineraries.sort(key = lambda it: it['duration'])
    for itinerary in itineraries:
        keep_keys(itinerary,[
            "duration",
            "walkTime",
            "walkDistance",
            "transfers",
            "legs",
            "tooSloped"
        ])

        itinerary['duration'] = convert_to_hms(itinerary['duration'])
        itinerary['walkTime'] = convert_to_hms(itinerary['walkTime'])

        for leg in itinerary["legs"]:
            keep_keys(leg,[
                "distance",
                "mode",
                "to",
                "steps"
            ])
            keep_keys(leg["to"],[
                "name",
            ])
            for step in leg["steps"]:
                keep_keys(step,[
                    "distance",
                    "relativeDirection",
                    "streetName"
                ])
    return clean_plan

# ========================================================
# Instantiate MCP server

mcp = FastMCP("TMB")
load_dotenv(".env")
api_id = os.getenv("TMB_API_APP_ID")
api_key = os.getenv("TMB_API_APP_KEY")
if api_id is None or api_key is None:
    raise RuntimeError(
        "TMB_API_APP_ID or TMB_API_APP_KEY missing from your .env file. Get them from https://developer.tmb.cat/"
    )

api = TMB_API(api_id, api_key)


# MCP Tools
@mcp.tool()
def get_station_info(name: str) -> dict:
    """
    Find a station's data. Return the data in a clear way
    """
    stop_data = get_stop_info().locate_stop_by_name_fuzzy(name)
    if stop_data is None:
        return {"error": "No trobo aquesta parada"}
    lat = stop_data["stop_lat"]
    lon = stop_data["stop_lon"]
    numeroparada = stop_data["stop_code"]
    return {"coordinates": [lat, lon], "stop_code": numeroparada}


@mcp.tool()
def get_route(origin: str, destination: str) -> dict:
    """
    Given a phrase that can be interpreted as a route between two points, gind a route between the two stations.
    """
    origenlat, origenlon = get_station_info.fn(origin)["coordinates"]

    destilat, destilon = get_station_info.fn(destination)["coordinates"]

    api_response = api.get_route_plan(
        origin = (origenlat,origenlon),
        destination = (destilat,destilon),
        currenttime = get_time_barcelona(),
        arriveBy = False,
        showIntermediateStops = False,
        mode = None
    )
    return cleanup_plan(api_response["plan"])

# ========================================================
# Run server

if __name__ == "__main__":
    if "--test" in sys.argv:
        start = str(input("Des de quina parada? "))
        stop = str(input("Fins on? "))
        print(json.dumps(get_route.fn(start,stop)))
    else:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
