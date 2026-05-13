import json
from fastmcp import FastMCP
import requests

from dataclasses import dataclass

mcp = FastMCP("Weather Tool")


@dataclass
class LatLon:
    latitude: str
    longitude: str


def geocode_city(city: str) -> LatLon:
    geocode_url = f"https://nominatim.openstreetmap.org/search?city={city}&format=json"
    geo_response = requests.get(
        geocode_url,
        headers={
            "User-Agent": "Process Talks development platform (hello@processtalks.com)"
        },
    )
    geo_response.raise_for_status()
    geo_data = geo_response.json()

    print(geo_data)

    lat = geo_data[0]["lat"]
    lon = geo_data[0]["lon"]

    return LatLon(latitude=lat, longitude=lon)


def get_weather_data(location: LatLon):
    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={location.latitude}&longitude={location.longitude}&current_weather=true"
    weather_response = requests.get(weather_url)
    weather_data = weather_response.json()

    return weather_data


@mcp.tool()
def get_weather_city(city: str) -> str:
    """Gets the weather in the provided human-readable city name"""

    location = geocode_city(city)
    weather = get_weather_data(location)

    return f"Weather in {city} (provided by open-meteo.com): {json.dumps(weather)}"


@mcp.tool()
def get_weather_coords(latitude: str, longitude: str):
    """Gets the weather in the provided coordinates"""

    location = LatLon(latitude=latitude, longitude=longitude)
    weather = get_weather_data(location)

    return f"Weather in {latitude}, {longitude}: {json.dumps(weather)}"


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
