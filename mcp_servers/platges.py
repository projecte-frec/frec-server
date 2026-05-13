import sys
import requests
from fastmcp import FastMCP
from bs4 import BeautifulSoup

# ========================================================
#
#  MCP server to access open data from AMB (Area Metropolitana de Bcn)
#
# ========================================================

# ========================================================
#  Auxiliary classes


class AMB_opendata_API:
    # ----------------------------------------------------
    # Prepare connection to API to retrieve data
    def __init__(self):
        self.url = "https://opendata.amb.cat"

    # ----------------------------------------------------
    # send request to server
    def call_server(self, endpoint, request_data=None):
        request_headers = {"Content-Type": "application/json; charset=utf-8"}
        response = requests.get(
            self.url + endpoint, headers=request_headers, data=request_data
        )
        response.raise_for_status()
        return response.json()


# ========================================================
# instantiate an MCP server

mcp = FastMCP("platgesAMB")

# auxiliary
api = AMB_opendata_API()

# l'API dona els ids, pero no els noms complerts.
beach_towns = {
    "badalona": "Badalona",
    "barcelona": "Barcelona",
    "castelldefels": "Castelldefels",
    "gava": "Gavà",
    "montgat": "Montgat",
    "prat": "El Prat de Llobregat",
    "sadria": "Sant Adrià del Besós",
    "viladecans": "Viladecans",
}


# ---------------------------------------------------------
@mcp.tool()
def get_beach_towns_ids() -> dict:
    """
    Gets a dictionary relating town identifiers and full town names, for towns with available beach status information.
    Args:

    Results: A dictionary of town identifiers, each related to the full town name
    """
    return beach_towns


# ---------------------------------------------------------
@mcp.tool()
def get_beach_status(town: str) -> list:
    """
    Gets the status of beaches in the given town.
    Args:
       town: a town identifier.
    Results: A list of objects, each corresponing to the status of one beach in given town.
    """
    response = api.call_server("/dades_estat_platja/search")
    return [it for it in response["items"] if it["municipi"] == town]


# ---------------------------------------------------------
if __name__ == "__main__":
    if "--test" in sys.argv:
        pass
    # t = input(f"town? ({','.join(get_beach_towns.fn().keys())}): ")
    # print(get_beach_status.fn(t))
    else:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
